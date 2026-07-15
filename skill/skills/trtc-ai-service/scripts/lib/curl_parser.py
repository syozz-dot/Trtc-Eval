"""curl command parser (Phase 3 Stage 4).

Parses curl commands pasted by users in the chat into unified ``ParsedApi`` data structures,
consumed by ``contract_resolver`` and ``adapter_codegen``.

Supported:
- Multi-line (trailing ``\\``) / single-line
- ``-X / --request <METHOD>``
- ``-H / --header 'k: v'`` (accumulates on repeated appearances)
- ``-d / --data / --data-raw / --data-binary '<body>'``
- ``--url <url>`` or URL as a positional argument
- Single-quoted / double-quoted strings (including escapes)
- Auto-detect Authorization → ``bearer``; custom ``X-*-Token`` → ``api_key``
- Auto-detect if body is JSON and extract ``request_schema`` fields accordingly

Not supported (when protocol_mismatch=True, contract_resolver triggers L3 fallback):
- multipart / form-data uploads
- ``--cookie``
- Non-JSON body (XML / GraphQL string body)
"""
from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlsplit


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class AuthSpec:
    type: str = "none"          # bearer | api_key | basic | none
    location: str = "header"    # header | query
    name: str = ""              # header 名 / query 键名

    def to_dict(self) -> Dict:
        return {"type": self.type, "location": self.location, "name": self.name}


@dataclass
class ParsedApi:
    """curl / OpenAPI 解析后的统一表示。"""

    method: str = "GET"
    base_url: str = ""              # https://crm.example.com
    path: str = "/"                 # /api/v2/work_orders（不带 query）
    query: Dict[str, str] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    auth: AuthSpec = field(default_factory=AuthSpec)
    request_schema: Dict[str, Any] = field(default_factory=dict)
    response_schema: Dict[str, Any] = field(default_factory=dict)
    body_format: str = "none"       # json | form | raw | none
    body_sample: Any = None         # 原始 body（已解析为 dict / str）
    source: str = "curl"            # curl | openapi
    raw: str = ""                   # 原始输入（供 codegen 调试）

    def to_dict(self) -> Dict:
        return {
            "method": self.method,
            "base_url": self.base_url,
            "path": self.path,
            "query": dict(self.query),
            "auth": self.auth.to_dict(),
            # 注意：schema 已经在 parse 阶段标准化过；这里**不再**重复 normalize，
            # 否则像 "string[]" 这类已 normalized 的字面量会被二次降级为 "string"
            "request_schema": dict(self.request_schema),
            "response_schema": dict(self.response_schema),
            "body_format": self.body_format,
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _normalize_schema(node: Any) -> Any:
    """把任意 dict / list 标准化为"字段 → 类型字符串"递归视图。"""
    if isinstance(node, dict):
        out: Dict[str, Any] = {}
        for k, v in node.items():
            out[k] = _normalize_schema(v)
        return out
    if isinstance(node, list):
        if not node:
            return "array<any>"
        # 同质数组取第一个递归
        first = _normalize_schema(node[0])
        if isinstance(first, str):
            return f"{first}[]"
        return [first]
    if isinstance(node, str):
        return "string"
    if isinstance(node, bool):  # bool 必须在 int 之前判断
        return "bool"
    if isinstance(node, int):
        return "int"
    if isinstance(node, float):
        return "float"
    if node is None:
        return "null"
    return type(node).__name__


def _split_url(url: str) -> Tuple[str, str, Dict[str, str]]:
    """``https://a.com/b?c=1`` → (``https://a.com``, ``/b``, {c:'1'})"""
    parts = urlsplit(url)
    if not parts.scheme:
        # 用户可能贴了相对路径 /tickets
        return ("", url.split("?", 1)[0], _parse_query(url.split("?", 1)[1] if "?" in url else ""))
    base = f"{parts.scheme}://{parts.netloc}"
    path = parts.path or "/"
    return (base, path, _parse_query(parts.query))


def _parse_query(qs: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for pair in qs.split("&"):
        if not pair:
            continue
        if "=" in pair:
            k, _, v = pair.partition("=")
            out[k] = v
        else:
            out[pair] = ""
    return out


_BEARER_RE = re.compile(r"^\s*Bearer\s+\S+\s*$", re.IGNORECASE)
_BASIC_RE = re.compile(r"^\s*Basic\s+\S+\s*$", re.IGNORECASE)


def _detect_auth(headers: Dict[str, str]) -> AuthSpec:
    for k, v in headers.items():
        if k.lower() == "authorization":
            if _BEARER_RE.match(v):
                return AuthSpec(type="bearer", location="header", name=k)
            if _BASIC_RE.match(v):
                return AuthSpec(type="basic", location="header", name=k)
            return AuthSpec(type="bearer", location="header", name=k)
        # 常见自定义鉴权头
        if k.lower() in {"x-auth-token", "x-api-key", "x-access-token", "x-token"}:
            return AuthSpec(type="api_key", location="header", name=k)
    return AuthSpec(type="none", location="header", name="")


# ---------------------------------------------------------------------------
# 主解析逻辑
# ---------------------------------------------------------------------------
class CurlParseError(ValueError):
    """curl 解析失败。"""


def parse_curl(raw: str) -> ParsedApi:
    """主入口：解析任意 curl 字符串。

    Raises
    ------
    CurlParseError
        当输入不是 curl 命令、缺少 URL、或无法 tokenize。
    """
    if not raw or not raw.strip():
        raise CurlParseError("empty input")

    # 1) 行尾 \ 拼接 + 去掉首个 curl 命令名
    text = re.sub(r"\\\s*\n", " ", raw.strip())
    # 替换非 ASCII 全角空格
    text = text.replace("\u3000", " ")
    try:
        tokens = shlex.split(text, posix=True)
    except ValueError as exc:  # 不闭合引号
        raise CurlParseError(f"shell tokenize failed: {exc}") from exc
    if not tokens:
        raise CurlParseError("no tokens after split")

    # 跳过 curl 命令头（兼容用户漏贴的情况）
    if tokens[0].lower().endswith("curl"):
        tokens = tokens[1:]

    method: Optional[str] = None
    url: Optional[str] = None
    headers: Dict[str, str] = {}
    body_raw: Optional[str] = None
    body_format = "none"

    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in ("-X", "--request"):
            method = tokens[i + 1].upper()
            i += 2
            continue
        if t in ("-H", "--header"):
            kv = tokens[i + 1]
            if ":" in kv:
                k, _, v = kv.partition(":")
                headers[k.strip()] = v.strip()
            i += 2
            continue
        if t in ("-d", "--data", "--data-raw", "--data-binary", "--data-ascii", "--json"):
            body_raw = tokens[i + 1]
            body_format = "json" if t == "--json" else "raw"
            i += 2
            continue
        if t == "--url":
            url = tokens[i + 1]
            i += 2
            continue
        if t in ("-G", "--get"):
            method = method or "GET"
            i += 1
            continue
        if t in ("-u", "--user"):
            # basic auth: user:pass → 仅识别为 basic，不存原值
            headers.setdefault("Authorization", "Basic <redacted>")
            i += 2
            continue
        if t in ("-X", "--include", "-i", "-I", "--head", "-v", "--verbose",
                 "-s", "--silent", "-L", "--location", "-k", "--insecure",
                 "--compressed", "-f", "--fail"):
            # 控制类参数，跳过
            i += 1
            continue
        if t.startswith("--") or t.startswith("-"):
            # 不认识的选项，吃掉它（防御性：可能带值）
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                i += 2
            else:
                i += 1
            continue
        # 位置参数：第一个非选项 token 当作 URL
        if url is None:
            url = t
        i += 1

    if not url:
        raise CurlParseError("no URL found in curl command")

    # 推断 method
    if method is None:
        method = "POST" if body_raw is not None else "GET"

    base_url, path, query = _split_url(url)

    # 解析 body 为 JSON（best effort）
    request_schema: Dict[str, Any] = {}
    body_sample: Any = body_raw
    if body_raw:
        stripped = body_raw.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                body_sample = parsed
                body_format = "json"
                if isinstance(parsed, dict):
                    request_schema = _normalize_schema(parsed)  # type: ignore[assignment]
            except json.JSONDecodeError:
                body_format = "raw"
        elif "&" in stripped and "=" in stripped:
            # 简易 form-urlencoded
            body_format = "form"
            request_schema = {k: "string" for k in _parse_query(stripped).keys()}

    auth = _detect_auth(headers)

    return ParsedApi(
        method=method,
        base_url=base_url,
        path=path,
        query=query,
        headers=headers,
        auth=auth,
        request_schema=request_schema,
        response_schema={},   # curl 命令本身没有响应；用户可在第 2 步贴响应
        body_format=body_format,
        body_sample=body_sample,
        source="curl",
        raw=raw,
    )


# ---------------------------------------------------------------------------
# 可选：从 curl 注释或额外的"# response: {...}"块中提取响应样例
# ---------------------------------------------------------------------------
_RESPONSE_HINT_RE = re.compile(
    r"#\s*(?:resp|response)\s*[:=]\s*(\{.*?\}|\[.*?\])",
    re.IGNORECASE | re.DOTALL,
)


def parse_curl_with_response(raw: str) -> ParsedApi:
    """额外尝试从注释行中提取 ``# response: {...}`` 作为 response_schema。"""
    api = parse_curl(raw)
    m = _RESPONSE_HINT_RE.search(raw)
    if m:
        try:
            api.response_schema = _normalize_schema(json.loads(m.group(1)))  # type: ignore[assignment]
        except json.JSONDecodeError:
            pass
    return api
