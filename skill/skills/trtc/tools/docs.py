"""
tools/docs.py
==============

TRTC AI Integration —— 官方文档检索编排工具。

职责边界：
  - 输入已确定的 product / platform / query / intent
  - 先做 slice-first gate（仅 slice-lookup）
  - 读取 trtc.io llms index，做 heading scoring
  - 抓取目标 .md 文档并提取高相关 snippet
  - 返回结构化 source bundle

不负责：
  - 意图推断
  - session / interruption 状态写入
  - 最终面向用户的自然语言回答
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import yaml

try:
    from tools.search import InvalidInputError as SearchInvalidInputError
    from tools.search import Search
    from tools.search import SearchError
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from tools.search import InvalidInputError as SearchInvalidInputError  # type: ignore
    from tools.search import Search  # type: ignore
    from tools.search import SearchError  # type: ignore


THIS_FILE = Path(__file__).resolve()
DEFAULT_REPO_ROOT = THIS_FILE.parent.parent.parent.parent
ENV_REPO_ROOT = "TRTC_REPO_ROOT"
BASE_TRTC_URL = "https://trtc.io"
KNOWN_PRODUCTS = {"conference", "chat", "call", "live", "rtc-engine"}
KNOWN_PLATFORMS = {"web", "android", "ios", "flutter", "electron", "unity"}
KNOWN_INTENTS = {"fact-lookup", "decision-lookup", "path-lookup", "slice-lookup"}
# 第一版把 heading 进入 resolved/ambiguous 路径的门槛压在 5 分：
# - 单个明确 heading 命中（title_hit=5）即可继续
# - 仅有很弱的 CJK 重叠/噪声匹配则仍留在 low_score_candidates
HEADING_RESOLVE_MIN_SCORE = 5
HIGH_VALUE_QUERY_KEYWORDS = {
    "pricing", "bill", "quota", "usersig", "secretkey", "migration", "upgrade", "compatibility",
    "计费", "配额", "鉴权", "密钥", "迁移", "升级", "兼容",
}
PLATFORM_SENSITIVE_KEYWORDS = {
    "api", "参数", "callback", "sdk", "migration", "升级", "ios", "android", "web",
}
WORD_RE = re.compile(r"[A-Za-z0-9_]+|[一-鿿]+")
ERROR_CODE_RE = re.compile(r"(?<![A-Za-z0-9])(?:ERR[_-]?)?-?(\d{4,6})(?![A-Za-z0-9])", re.IGNORECASE)
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


class DocsError(Exception):
    """docs.py 异常基类。"""


class InvalidInputError(DocsError):
    """CLI 或 API 输入不合法。"""


class DependencyError(DocsError):
    """本地依赖或解析依赖异常。"""


@dataclass(frozen=True)
class HeadingDoc:
    title: str
    url: str
    description: str


@dataclass(frozen=True)
class HeadingCandidate:
    heading: str
    description: str
    docs: tuple[HeadingDoc, ...]


@dataclass(frozen=True)
class ScoredHeading:
    candidate: HeadingCandidate
    score: int


@dataclass(frozen=True)
class DocChunk:
    title: str
    body: str
    score: int


def _repo_root() -> Path:
    env = os.environ.get(ENV_REPO_ROOT)
    return Path(env).resolve() if env else DEFAULT_REPO_ROOT


def _kb_root() -> Path:
    return _repo_root() / "knowledge-base"


def _products_yaml() -> Path:
    return _kb_root() / "products.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _normalize_basic(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    parts = WORD_RE.findall(text)
    return " ".join(part.strip() for part in parts if part.strip())


def _tokenize(text: str) -> set[str]:
    tokens: set[str] = set()
    for part in WORD_RE.findall(text or ""):
        if re.fullmatch(r"[A-Za-z0-9_]+", part):
            tokens.add(part.lower())
            continue
        if len(part) == 1:
            tokens.add(part)
            continue
        for i in range(len(part) - 1):
            tokens.add(part[i : i + 2])
    return tokens


def _iter_cjk_chars(text: str) -> set[str]:
    return {ch for ch in text if "一" <= ch <= "鿿"}


def _cjk_overlap(a: str, b: str) -> int:
    return len(_iter_cjk_chars(a) & _iter_cjk_chars(b))


def _extract_error_code(query: str) -> Optional[int]:
    match = ERROR_CODE_RE.search(query or "")
    if not match:
        return None
    return int(match.group(1))


def _product_llms_url(product: str) -> str:
    index = _load_yaml(_products_yaml())
    for raw in index.get("products") or []:
        if str(raw.get("id") or "") == product:
            llms_file = str(raw.get("llms_file") or "").strip()
            if not llms_file:
                break
            if llms_file.startswith(("http://", "https://")):
                return llms_file
            return f"{BASE_TRTC_URL}/{llms_file.lstrip('/')}"
    raise DependencyError(f"knowledge-base/products.yaml 缺少 product={product} 的 llms_file")


def _platform_llms_url(product: str, platform: str) -> str:
    return f"{BASE_TRTC_URL}/llms/{product}/{platform}.txt"


def _conference_llms_url() -> str:
    return f"{BASE_TRTC_URL}/llms/conference.txt"


def _fetch_text(url: str, timeout: float = 10.0) -> str:
    with urlopen(url, timeout=timeout) as resp:
        content_type = str(resp.headers.get("Content-Type") or "")
        charset_match = re.search(r"charset=([\w-]+)", content_type)
        encoding = charset_match.group(1) if charset_match else "utf-8"
        return resp.read().decode(encoding, errors="replace")


def _looks_like_missing_platform_index(text: str) -> bool:
    normalized = _normalize_basic(text)
    return "404" in normalized or "not found" in normalized or "html" in normalized[:80]


def _needs_platform_index(query: str, platform: Optional[str], intent: str) -> bool:
    if not platform:
        return False
    if intent == "path-lookup":
        return True
    normalized = _normalize_basic(query)
    return any(keyword in normalized for keyword in PLATFORM_SENSITIVE_KEYWORDS)


def _parse_llms_index(text: str) -> list[HeadingCandidate]:
    candidates: list[HeadingCandidate] = []
    current_heading: Optional[str] = None
    current_desc = ""
    current_docs: list[HeadingDoc] = []

    def flush() -> None:
        nonlocal current_heading, current_desc, current_docs
        if current_heading:
            candidates.append(
                HeadingCandidate(
                    heading=current_heading,
                    description=current_desc.strip(),
                    docs=tuple(current_docs),
                )
            )
        current_heading = None
        current_desc = ""
        current_docs = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            flush()
            current_heading = line[3:].strip()
            continue
        if current_heading is None:
            continue
        link_match = LINK_RE.search(line)
        if link_match:
            title = link_match.group(1).strip()
            url = link_match.group(2).strip()
            description = line[link_match.end() :].lstrip(" :-|\t")
            if url and not url.startswith("http"):
                url = f"{BASE_TRTC_URL}/{url.lstrip('/')}"
            current_docs.append(HeadingDoc(title=title, url=url, description=description))
            if not current_desc and description:
                current_desc = description
            continue
        if not current_desc:
            current_desc = line
    flush()
    return candidates


def _query_keyword_overlap(query: str, text: str) -> int:
    normalized_query = _normalize_basic(query)
    normalized_text = _normalize_basic(text)
    return sum(1 for keyword in HIGH_VALUE_QUERY_KEYWORDS if keyword in normalized_query and keyword in normalized_text)


def _score_heading(query: str, candidate: HeadingCandidate, intent: str) -> int:
    normalized_query = _normalize_basic(query)
    query_tokens = _tokenize(normalized_query)
    heading_text = _normalize_basic(candidate.heading)
    desc_text = _normalize_basic(candidate.description)
    heading_hits = len(query_tokens & _tokenize(heading_text))
    desc_hits = len(query_tokens & _tokenize(desc_text))
    combined = " ".join(part for part in [heading_text, desc_text] if part)
    path_boost = 0
    if intent == "path-lookup" and any(token in combined for token in ("migration", "upgrade", "compatibility", "迁移", "升级", "兼容")):
        path_boost = 8
    return (
        heading_hits * 5
        + desc_hits * 3
        + _query_keyword_overlap(query, combined) * 2
        + _cjk_overlap(normalized_query, combined)
        + path_boost
    )


def _score_chunk(query: str, title: str, body: str) -> int:
    normalized_query = _normalize_basic(query)
    query_tokens = _tokenize(normalized_query)
    title_text = _normalize_basic(title)
    body_text = _normalize_basic(body)
    title_hits = len(query_tokens & _tokenize(title_text))
    body_hits = len(query_tokens & _tokenize(body_text))
    combined = " ".join(part for part in [title_text, body_text] if part)
    return (
        title_hits * 5
        + body_hits * 3
        + _query_keyword_overlap(query, combined) * 2
        + _cjk_overlap(normalized_query, combined)
    )


def _md_chunks(text: str, query: str) -> list[DocChunk]:
    matches = list(MD_HEADING_RE.finditer(text))
    if not matches:
        body = text.strip()
        score = _score_chunk(query, "document", body)
        return [DocChunk(title="document", body=body[:800], score=score)] if score > 0 else []

    chunks: list[DocChunk] = []
    for idx, match in enumerate(matches):
        title = match.group(2).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if not body:
            continue
        score = _score_chunk(query, title, body)
        if score <= 0:
            continue
        chunks.append(DocChunk(title=title, body=body[:800], score=score))
    chunks.sort(key=lambda item: item.score, reverse=True)
    return chunks[:3]


def _ensure_md_url(url: str) -> str:
    return url if url.endswith(".md") else f"{url}.md"


def _low_score_candidate(item: ScoredHeading) -> dict[str, str]:
    first_doc = item.candidate.docs[0]
    return {
        "heading": item.candidate.heading,
        "url": _ensure_md_url(first_doc.url),
    }


def _score_heading_candidates(query: str, candidates: list[HeadingCandidate], intent: str) -> list[ScoredHeading]:
    scored: list[ScoredHeading] = []
    for candidate in candidates:
        score = _score_heading(query, candidate, intent)
        if score > 0 and candidate.docs:
            scored.append(ScoredHeading(candidate=candidate, score=score))
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored


def _build_source(kind: str, title: str, *, url: Optional[str], path: Optional[str], snippet: str, confidence: float, source_rank: int) -> dict[str, Any]:
    return {
        "kind": kind,
        "title": title,
        "url": url,
        "path": path,
        "snippet": snippet,
        "confidence": max(0.0, min(1.0, confidence)),
        "source_rank": source_rank,
    }


def _empty_result(status: str, *, reason: str, ask_user: Optional[str] = None, retryable: bool = False) -> dict[str, Any]:
    return {
        "status": status,
        "mode": "none" if status in {"need_product", "not_found"} else "docs",
        "reason": reason,
        "retryable": retryable,
        "ask_user": ask_user,
        "sources": [],
        "debug": {
            "used_product_index": None,
            "used_platform_index": None,
            "used_fallback_indexes": [],
            "matched_headings": [],
            "search_status": "skipped",
            "docs_fetched": [],
            "low_score_candidates": [],
        },
    }


class Docs:
    """官方文档检索编排工具。"""

    @classmethod
    def resolve(
        cls,
        *,
        product: Optional[str],
        query: str,
        intent: str,
        platform: Optional[str] = None,
    ) -> dict[str, Any]:
        if intent not in KNOWN_INTENTS:
            raise InvalidInputError(f"未知 intent：{intent}")
        if not query or not query.strip():
            raise InvalidInputError("query 不能为空")
        if product is None:
            return _empty_result(
                "need_product",
                reason="need_product",
                ask_user="你想查哪个产品？conference / chat / call / live / rtc-engine",
            )
        if product not in KNOWN_PRODUCTS:
            raise InvalidInputError(f"未知 product：{product}")
        if platform is not None and platform not in KNOWN_PLATFORMS:
            raise InvalidInputError(f"未知 platform：{platform}")

        normalized_query = _normalize_basic(query)
        if sum(1 for p in KNOWN_PRODUCTS if _normalize_basic(p) in normalized_query) >= 2:
            return {
                **_empty_result(
                    "need_product",
                    reason="cross_product_not_supported",
                    ask_user="当前 docs 查询只支持单产品。请先拆成一个产品的问题再查。",
                ),
                "mode": "none",
            }

        error_code = _extract_error_code(query) if intent == "slice-lookup" else None

        debug = {
            "used_product_index": None,
            "used_platform_index": None,
            "used_fallback_indexes": [],
            "matched_headings": [],
            "search_status": "skipped",
            "docs_fetched": [],
            "low_score_candidates": [],
        }

        slice_sources: list[dict[str, Any]] = []
        if intent == "slice-lookup":
            try:
                if error_code is not None:
                    search_result = Search.slices(product=product, error_code=error_code, platform=platform)
                else:
                    search_result = Search.slices(product=product, query=query, platform=platform)
                debug["search_status"] = search_result.get("status") or "failed"
                candidates = search_result.get("candidates") or []
                if candidates:
                    top = candidates[0]
                    confidence = float(top.get("confidence") or 0.0)
                    slice_sources.append(
                        _build_source(
                            "slice",
                            top.get("title") or top.get("slice_id") or "slice",
                            url=None,
                            path=top.get("path"),
                            # mode=slice 时调用方应直接 Read slice 原文；这里不返回占位摘要，避免和真实 source of truth 冲突。
                            snippet="",
                            confidence=confidence,
                            source_rank=1,
                        )
                    )
                    if search_result.get("status") == "exact" and confidence >= 0.80:
                        return {
                            "status": "resolved",
                            "mode": "slice",
                            "reason": "slice_exact",
                            "retryable": False,
                            "ask_user": None,
                            "sources": slice_sources,
                            "debug": debug,
                        }
            except (SearchError, SearchInvalidInputError):
                debug["search_status"] = "failed"

        product_index_url = _product_llms_url(product)
        debug["used_product_index"] = product_index_url
        try:
            product_index_text = _fetch_text(product_index_url)
        except (HTTPError, URLError) as exc:
            retryable = not isinstance(exc, HTTPError) or exc.code >= 500
            reason = "docs_fetch_timeout" if retryable else "docs_fetch_not_found"
            return {
                **_empty_result("fetch_failed", reason=reason, retryable=retryable),
                "debug": debug,
            }

        heading_candidates = _parse_llms_index(product_index_text)

        if _needs_platform_index(query, platform, intent):
            platform_index_url = _platform_llms_url(product, platform or "")
            try:
                platform_index_text = _fetch_text(platform_index_url)
                if not _looks_like_missing_platform_index(platform_index_text):
                    debug["used_platform_index"] = platform_index_url
                    heading_candidates.extend(_parse_llms_index(platform_index_text))
            except (HTTPError, URLError):
                pass

        scored = _score_heading_candidates(query, heading_candidates, intent)
        qualified = [item for item in scored if item.score >= HEADING_RESOLVE_MIN_SCORE]

        # 这是第一版对“共享错误码落在公共索引”的兼容兜底，不是长期理想形态。
        # 只有 numeric error code 且主产品 index 没形成可用 heading 命中时，才额外补抓 conference.txt。
        if error_code is not None and not qualified:
            try:
                fallback_url = _conference_llms_url()
                fallback_text = _fetch_text(fallback_url)
                debug["used_fallback_indexes"].append(fallback_url)
                heading_candidates.extend(_parse_llms_index(fallback_text))
                scored = _score_heading_candidates(query, heading_candidates, intent)
                qualified = [item for item in scored if item.score >= HEADING_RESOLVE_MIN_SCORE]
            except (HTTPError, URLError):
                pass

        if not scored:
            # 即使没有任何 heading 打上分，也尽量返回少量索引内真实存在的 heading，
            # 让调用方把它们当作“可能相关、未验证”的候选给用户确认。
            debug["low_score_candidates"] = [
                {
                    "heading": candidate.heading,
                    "url": _ensure_md_url(candidate.docs[0].url),
                }
                for candidate in heading_candidates
                if candidate.docs
            ][:3]
            reason = "slice_not_found" if intent == "slice-lookup" else "docs_no_heading"
            return {
                **_empty_result("not_found", reason=reason),
                "debug": debug,
            }

        if not qualified:
            debug["low_score_candidates"] = [_low_score_candidate(item) for item in scored[:3]]
            reason = "slice_not_found" if intent == "slice-lookup" else "docs_no_heading"
            return {
                **_empty_result("not_found", reason=reason),
                "debug": debug,
            }

        top_score = scored[0].score
        selected: list[ScoredHeading]
        ambiguous = False
        if intent == "decision-lookup":
            # decision-lookup 天然允许多个候选并列展示，不走 ambiguous ask-user 分支。
            selected = [item for item in qualified if item.score >= top_score * 0.7][:3]
        else:
            selected = [qualified[0]]
            if len(qualified) >= 2 and qualified[1].score >= top_score * 0.85:
                ambiguous = True
                selected = qualified[:2]

        debug["matched_headings"] = [item.candidate.heading for item in selected]

        if ambiguous and intent != "decision-lookup":
            sources = []
            for rank, item in enumerate(selected, start=1):
                first_doc = item.candidate.docs[0]
                sources.append(
                    _build_source(
                        "trtc_doc",
                        item.candidate.heading,
                        url=_ensure_md_url(first_doc.url),
                        path=None,
                        snippet=item.candidate.description,
                        confidence=min(0.95, 0.30 + item.score * 0.02),
                        source_rank=rank,
                    )
                )
            return {
                "status": "ambiguous",
                "mode": "docs",
                "reason": "docs_heading_ambiguous",
                "retryable": False,
                "ask_user": "我找到了多个可能相关的官方文档方向，你想看哪一个？",
                "sources": sources,
                "debug": debug,
            }

        fetched_sources: list[dict[str, Any]] = []
        fetch_errors: list[tuple[str, bool]] = []
        docs_fetched = 0
        for item in selected:
            for doc in item.candidate.docs:
                if docs_fetched >= 2:
                    break
                md_url = _ensure_md_url(doc.url)
                try:
                    md_text = _fetch_text(md_url)
                except HTTPError as exc:
                    fetch_errors.append(("docs_fetch_not_found", False if exc.code == 404 else exc.code >= 500))
                    continue
                except URLError:
                    fetch_errors.append(("docs_fetch_timeout", True))
                    continue

                chunks = _md_chunks(md_text, query)
                if not chunks:
                    continue
                debug["docs_fetched"].append(md_url)
                docs_fetched += 1
                snippet = "\n\n".join(f"## {chunk.title}\n{chunk.body}" for chunk in chunks)
                fetched_sources.append(
                    _build_source(
                        "trtc_doc",
                        doc.title or item.candidate.heading,
                        url=md_url,
                        path=None,
                        snippet=snippet,
                        confidence=min(0.95, 0.30 + item.score * 0.02),
                        source_rank=0,
                    )
                )
            if docs_fetched >= 2:
                break

        if slice_sources and fetched_sources:
            sources = []
            for rank, source in enumerate(slice_sources + fetched_sources, start=1):
                source["source_rank"] = rank
                sources.append(source)
            return {
                "status": "resolved",
                "mode": "mixed",
                "reason": "slice_mixed",
                "retryable": False,
                "ask_user": None,
                "sources": sources,
                "debug": debug,
            }

        if fetched_sources:
            for rank, source in enumerate(fetched_sources, start=1):
                source["source_rank"] = rank
            return {
                "status": "resolved",
                "mode": "docs",
                "reason": "docs_heading_exact",
                "retryable": False,
                "ask_user": None,
                "sources": fetched_sources,
                "debug": debug,
            }

        if fetch_errors:
            reason, retryable = fetch_errors[0]
            return {
                **_empty_result("fetch_failed", reason=reason, retryable=retryable),
                "debug": debug,
            }

        reason = "slice_not_found" if intent == "slice-lookup" else "docs_no_heading"
        debug["low_score_candidates"] = [_low_score_candidate(item) for item in selected]
        return {
            **_empty_result("not_found", reason=reason),
            "debug": debug,
        }


def _parse_args(argv: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg.startswith("--"):
            key = arg[2:]
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                out[key] = argv[i + 1]
                i += 2
            else:
                out[key] = True
                i += 1
        else:
            i += 1
    return out


def _cli_resolve(args: list[str]) -> int:
    kv = _parse_args(args)
    query = kv.get("query")
    intent = kv.get("intent")
    product = kv.get("product")
    platform = kv.get("platform")
    if not query or isinstance(query, bool):
        print("ERROR: --query 必须提供", file=sys.stderr)
        return 1
    if not intent or isinstance(intent, bool):
        print("ERROR: --intent 必须提供", file=sys.stderr)
        return 1
    if isinstance(product, bool):
        print("ERROR: --product 值非法", file=sys.stderr)
        return 1
    if isinstance(platform, bool):
        print("ERROR: --platform 值非法", file=sys.stderr)
        return 1
    try:
        result = Docs.resolve(
            product=str(product) if product else None,
            platform=str(platform) if platform else None,
            query=str(query),
            intent=str(intent),
        )
    except InvalidInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except DependencyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd != "resolve":
        print(f"ERROR: 未知子命令 {cmd}", file=sys.stderr)
        return 1
    return _cli_resolve(rest)


if __name__ == "__main__":
    raise SystemExit(main())
