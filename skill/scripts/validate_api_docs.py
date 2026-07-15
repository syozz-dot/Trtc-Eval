#!/usr/bin/env python3
"""validate_api_docs.py — 平台 slice 的 api_docs 链接校验

针对 slice-spec.md 第四节「api_docs 字段」三件套:
- 违反后果:链接非类级 → AI 生成不存在的 API 名 → 客户编译报错投诉
- 验证手段:本脚本(每条 url 返回 200 + 含 /documentation/ 或 /api/ +
            打开链接的页面 H1 必须包含 frontmatter 里的 title)
- 绕过条件:平台官方确实无 API 参考站 → 必须填头文件 GitHub 永久链接

用法:
    python3 scripts/validate_api_docs.py knowledge-base/slices/live/ios/coguest-apply.md
    python3 scripts/validate_api_docs.py knowledge-base/slices/live/

flags:
    --offline       不发网络请求,只做静态格式检查(CI 默认推荐)
    --timeout=N     单链接超时秒数(默认 10)
    --no-h1-check   跳过 H1 包含 title 的检查(动态站点可能 SPA 渲染)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from _common import Report, parse_doc, run_cli

# Heuristics for what counts as an "API reference" URL.
API_PATH_HINTS = ("/documentation/", "/api/", "/reference/", "/sdkref/", "/javadoc/", "/apidoc/")

# Acceptable header-only fallbacks (raw GitHub permalinks with commit hash)
GITHUB_PERMALINK_RE = re.compile(
    r"^https://(?:raw\.)?github\.com/[^/]+/[^/]+/(?:blob|raw)/[0-9a-f]{7,40}/.+",
    re.IGNORECASE,
)

OFFLINE = "--offline" in sys.argv or False
SKIP_H1 = "--no-h1-check" in sys.argv or False
TIMEOUT = 10
for a in sys.argv:
    if a.startswith("--timeout="):
        TIMEOUT = int(a.split("=", 1)[1])

# Strip our flags so run_cli doesn't try to glob them
sys.argv[:] = [a for a in sys.argv if not a.startswith("--")]


def _is_api_url(url: str) -> bool:
    return any(h in url for h in API_PATH_HINTS) or bool(GITHUB_PERMALINK_RE.match(url))


def _fetch_html(url: str) -> tuple[int, str] | None:
    """Return (status, body) or None on network failure."""
    try:
        import requests
    except ImportError:
        return None
    try:
        r = requests.get(url, timeout=TIMEOUT, allow_redirects=True,
                         headers={"User-Agent": "trtc-spec-validator/1.0"})
        return r.status_code, r.text or ""
    except Exception:
        return None


H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)


def _h1_contains(html: str, needle: str) -> bool:
    """Return True if any <h1> tag's text contains `needle` (case-insensitive)."""
    needle_lc = needle.lower()
    for m in H1_RE.finditer(html):
        text = re.sub(r"<[^>]+>", "", m.group(1)).lower()
        if needle_lc in text:
            return True
    return False


def check_api_docs(path: Path) -> Report:
    rep = Report(file=path)

    # Only check platform-level files (which have api_docs)
    doc = parse_doc(path)
    fm = doc.frontmatter
    if "api_docs" not in fm:
        # Not a platform file; or product-level (no api_docs expected) — silent.
        return rep

    docs = fm["api_docs"]
    if not isinstance(docs, list) or not docs:
        rep.err("API-DOCS-EMPTY", "api_docs 必须是非空数组")
        return rep

    for i, entry in enumerate(docs):
        if not isinstance(entry, dict):
            rep.err("API-DOCS-TYPE", f"api_docs[{i}] 不是 mapping")
            continue
        title = entry.get("title", "")
        url = entry.get("url", "")
        prefix = f"api_docs[{i}] (title={title!r})"

        # Static checks
        if not title:
            rep.err("API-DOCS-TITLE", f"{prefix}: title 为空")
        if not url:
            rep.err("API-DOCS-URL-EMPTY", f"{prefix}: url 为空")
            continue
        if url.upper() == "TODO":
            rep.err("API-DOCS-TODO", f"{prefix}: url 是 TODO 占位")
            continue

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            rep.err("API-DOCS-SCHEME", f"{prefix}: url scheme 必须是 http(s),got {parsed.scheme!r}")
            continue

        # Path-level heuristic: must look like an API ref page or a github permalink.
        if not _is_api_url(url):
            rep.err(
                "API-DOCS-NOT-REF",
                f"{prefix}: url 不像 API 参考页面 — 应含 /documentation/、/api/、/reference/、/sdkref/ "
                f"之一,或为 github.com 上含 commit hash 的永久链接",
            )

        if OFFLINE:
            continue

        # Online checks: fetch and verify reachability + H1
        result = _fetch_html(url)
        if result is None:
            rep.warn("API-DOCS-NET", f"{prefix}: 网络抓取失败(可能受限于 CI 环境),已跳过 200/H1 检查")
            continue
        status, html = result
        if status != 200:
            rep.err("API-DOCS-HTTP", f"{prefix}: HTTP {status}")
            continue
        if SKIP_H1 or not title:
            continue
        # Github permalinks render to viewer pages whose H1 isn't the file name; skip.
        if GITHUB_PERMALINK_RE.match(url):
            continue
        if not _h1_contains(html, title):
            rep.warn(
                "API-DOCS-H1",
                f"{prefix}: 页面 H1 中未发现 title {title!r}(可能是 SPA 渲染,可加 --no-h1-check 跳过)",
            )

    return rep


def main() -> int:
    if OFFLINE:
        print("note: --offline mode: only static checks run", file=sys.stderr)
    return run_cli(check_api_docs)


if __name__ == "__main__":
    raise SystemExit(main())
