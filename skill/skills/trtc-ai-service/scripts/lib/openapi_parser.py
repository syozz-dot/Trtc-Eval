"""OpenAPI (Swagger 2 / OpenAPI 3) → ``ParsedApi`` parser.

Only implements the minimal subset needed for capability contract adaptation:
- ``info.servers[0].url`` → ``base_url``
- ``paths.<path>.<method>`` → a set of ``ParsedApi``
- ``$ref`` references resolved via ``components.schemas`` / ``definitions`` into type maps
- No OpenAPI validation (no heavy dependencies like jsonschema)

Supported file formats: ``.yaml`` / ``.yml`` / ``.json``.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .curl_parser import AuthSpec, ParsedApi, _normalize_schema


class OpenApiParseError(ValueError):
    """OpenAPI 文件解析失败。"""


# ---------------------------------------------------------------------------
# 装载
# ---------------------------------------------------------------------------
def _load_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise OpenApiParseError(f"file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise OpenApiParseError("PyYAML required for .yaml input") from exc
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise OpenApiParseError(f"yaml parse failed: {exc}") from exc
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise OpenApiParseError(f"json parse failed: {exc}") from exc
    if not isinstance(data, dict):
        raise OpenApiParseError("OpenAPI root must be a mapping")
    return data


# ---------------------------------------------------------------------------
# $ref 解析
# ---------------------------------------------------------------------------
class _RefResolver:
    def __init__(self, doc: Dict[str, Any]) -> None:
        self.doc = doc
        self._cache: Dict[str, Any] = {}
        # OpenAPI 3 用 components.schemas；Swagger 2 用 definitions
        self.components = (
            doc.get("components", {}).get("schemas", {})
            if isinstance(doc.get("components"), dict)
            else {}
        )
        self.definitions = (
            doc.get("definitions", {}) if isinstance(doc.get("definitions"), dict) else {}
        )

    def resolve(self, node: Any, _depth: int = 0) -> Any:
        if _depth > 10:  # 防递归爆栈
            return {"$ref_too_deep": True}
        if isinstance(node, dict):
            if "$ref" in node:
                target = self._lookup(node["$ref"])
                return self.resolve(target, _depth + 1)
            return {k: self.resolve(v, _depth + 1) for k, v in node.items()}
        if isinstance(node, list):
            return [self.resolve(item, _depth + 1) for item in node]
        return node

    def _lookup(self, ref: str) -> Any:
        if ref in self._cache:
            return self._cache[ref]
        # 仅支持本文档引用 #/...
        if not ref.startswith("#/"):
            return {"$ref_external": ref}
        cur: Any = self.doc
        for seg in ref[2:].split("/"):
            if isinstance(cur, dict) and seg in cur:
                cur = cur[seg]
            else:
                return {"$ref_unresolved": ref}
        self._cache[ref] = cur
        return cur


# ---------------------------------------------------------------------------
# Schema → 简化类型字典
# ---------------------------------------------------------------------------
_PRIMITIVES = {
    "string": "string",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
}


def _schema_to_type(schema: Dict[str, Any], depth: int = 0) -> Any:
    """把 OpenAPI schema 转成内部类型表达。"""
    if depth > 10 or not isinstance(schema, dict):
        return "any"
    t = schema.get("type")
    if t in _PRIMITIVES:
        if "enum" in schema and isinstance(schema["enum"], list):
            vals = ", ".join(str(v) for v in schema["enum"])
            return f"enum[{vals}]"
        return _PRIMITIVES[t]
    if t == "array":
        item_t = _schema_to_type(schema.get("items", {}) or {}, depth + 1)
        return f"{item_t}[]" if isinstance(item_t, str) else [item_t]
    if t == "object" or "properties" in schema:
        out: Dict[str, Any] = {}
        for k, v in (schema.get("properties") or {}).items():
            out[k] = _schema_to_type(v or {}, depth + 1)
        return out
    # oneOf / anyOf / allOf 简化为 any
    if any(k in schema for k in ("oneOf", "anyOf", "allOf")):
        return "any"
    return "any"


# ---------------------------------------------------------------------------
# 单 operation → ParsedApi
# ---------------------------------------------------------------------------
def _extract_request_schema(op: Dict[str, Any], resolver: _RefResolver) -> Dict[str, Any]:
    schema: Dict[str, Any] = {}
    # OpenAPI 3: requestBody.content["application/json"].schema
    rb = op.get("requestBody")
    if isinstance(rb, dict):
        rb = resolver.resolve(rb)
        content = rb.get("content", {}) if isinstance(rb, dict) else {}
        for mime, mb in content.items():
            if "json" in mime.lower():
                s = mb.get("schema") if isinstance(mb, dict) else None
                if s is not None:
                    schema = _schema_to_type(resolver.resolve(s)) or {}
                    if isinstance(schema, dict):
                        return schema
                    break
    # Swagger 2: parameters[in=body].schema
    for p in op.get("parameters", []) or []:
        p = resolver.resolve(p) if isinstance(p, dict) else p
        if isinstance(p, dict) and p.get("in") == "body":
            s = p.get("schema")
            if s is not None:
                conv = _schema_to_type(resolver.resolve(s))
                if isinstance(conv, dict):
                    return conv
    # 兜底：把 query/path/header 参数也合并到 request_schema
    out: Dict[str, Any] = {}
    for p in op.get("parameters", []) or []:
        p = resolver.resolve(p) if isinstance(p, dict) else p
        if not isinstance(p, dict):
            continue
        if p.get("in") in ("query", "path", "header"):
            name = p.get("name")
            if name:
                out[name] = _schema_to_type(p.get("schema") or {"type": p.get("type", "string")})
    return out


def _extract_response_schema(op: Dict[str, Any], resolver: _RefResolver) -> Dict[str, Any]:
    responses = op.get("responses") or {}
    # 优先 200 / 201 / 2xx
    for code in ("200", "201", "default"):
        if code in responses:
            r = resolver.resolve(responses[code])
            if isinstance(r, dict):
                # OpenAPI 3
                content = r.get("content", {}) if isinstance(r.get("content"), dict) else {}
                for mime, mb in content.items():
                    if "json" in mime.lower() and isinstance(mb, dict):
                        s = resolver.resolve(mb.get("schema") or {})
                        conv = _schema_to_type(s)
                        if isinstance(conv, dict):
                            return conv
                # Swagger 2
                if "schema" in r:
                    s = resolver.resolve(r["schema"])
                    conv = _schema_to_type(s)
                    if isinstance(conv, dict):
                        return conv
            break
    return {}


def _detect_auth_from_security(op: Dict[str, Any], doc: Dict[str, Any]) -> AuthSpec:
    sec_defs = (
        doc.get("components", {}).get("securitySchemes", {})
        if isinstance(doc.get("components"), dict)
        else doc.get("securityDefinitions", {})
    ) or {}
    sec = op.get("security") or doc.get("security") or []
    for entry in sec:
        if not isinstance(entry, dict):
            continue
        for name in entry.keys():
            scheme = sec_defs.get(name) or {}
            t = scheme.get("type", "").lower()
            if t == "http" and scheme.get("scheme", "").lower() == "bearer":
                return AuthSpec(type="bearer", location="header", name="Authorization")
            if t == "apikey":
                return AuthSpec(
                    type="api_key",
                    location=scheme.get("in", "header"),
                    name=scheme.get("name", "X-API-Key"),
                )
            if t == "http" and scheme.get("scheme", "").lower() == "basic":
                return AuthSpec(type="basic", location="header", name="Authorization")
    return AuthSpec()


def _base_url(doc: Dict[str, Any]) -> str:
    servers = doc.get("servers") or []
    if servers and isinstance(servers, list) and isinstance(servers[0], dict):
        return str(servers[0].get("url", "")).rstrip("/")
    # Swagger 2
    host = doc.get("host", "")
    schemes = doc.get("schemes") or ["https"]
    base_path = doc.get("basePath", "")
    if host:
        return f"{schemes[0]}://{host}{base_path}".rstrip("/")
    return ""


# ---------------------------------------------------------------------------
# 公共入口
# ---------------------------------------------------------------------------
_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}


def parse_openapi(
    file_path: Path,
    *,
    select_path: Optional[str] = None,
    select_method: Optional[str] = None,
) -> List[ParsedApi]:
    """解析 OpenAPI 文件返回所有 operation 的 ParsedApi 列表。

    可用 ``select_path`` / ``select_method`` 过滤；为空时返回全部 operation。
    """
    doc = _load_file(Path(file_path))
    resolver = _RefResolver(doc)
    base = _base_url(doc)
    paths = doc.get("paths") or {}
    if not isinstance(paths, dict):
        raise OpenApiParseError("OpenAPI 'paths' must be a mapping")

    out: List[ParsedApi] = []
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        if select_path and select_path != path:
            continue
        for method, op in item.items():
            if method.lower() not in _HTTP_METHODS:
                continue
            if select_method and method.upper() != select_method.upper():
                continue
            if not isinstance(op, dict):
                continue
            api = ParsedApi(
                method=method.upper(),
                base_url=base,
                path=path,
                request_schema=_extract_request_schema(op, resolver),
                response_schema=_extract_response_schema(op, resolver),
                auth=_detect_auth_from_security(op, doc),
                source="openapi",
                body_format="json" if op.get("requestBody") or any(
                    p.get("in") == "body" for p in (op.get("parameters") or []) if isinstance(p, dict)
                ) else "none",
                raw=f"openapi://{path}#{method.upper()}",
            )
            out.append(api)
    if select_path and not out:
        raise OpenApiParseError(
            f"no operation matched: path={select_path!r}, method={select_method!r}"
        )
    return out
