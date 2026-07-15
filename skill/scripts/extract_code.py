#!/usr/bin/env python3
"""extract_code.py — 抽取 markdown 中的代码块,供编译/lint 验证

针对 slice-spec.md「代码示例标准」三件套中的"抽取代码块编译"步骤:
    python scripts/extract_code.py {file} | xcodebuild build ...
    python scripts/extract_code.py {file} | tsc --noEmit ...

默认行为:把 markdown 里所有 ``` 代码块按出现顺序拼接,输出到 stdout。
带 --by-lang 时,按语言分文件输出到指定目录。

用法:
    # 全部代码 → stdout
    python3 scripts/extract_code.py knowledge-base/slices/live/ios/coguest-apply.md

    # 仅 swift 代码 → stdout
    python3 scripts/extract_code.py --lang=swift knowledge-base/slices/live/ios/coguest-apply.md

    # 按语言拆分到目录
    python3 scripts/extract_code.py --by-lang=/tmp/extracted/ knowledge-base/slices/live/ios/coguest-apply.md

    # 列出所有代码块的元信息(语言 + 行数)
    python3 scripts/extract_code.py --list knowledge-base/slices/live/ios/coguest-apply.md

注意:这是个工具脚本,不参与"通过/失败"判定,exit code 永远 0(除非参数错误)。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import iter_code_blocks, parse_doc


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="extract_code.py",
        description="Extract fenced code blocks from one or more markdown files.",
    )
    ap.add_argument("files", nargs="+", help="markdown file(s) to extract from")
    ap.add_argument("--lang", default=None,
                    help="只输出指定语言的代码块(如 swift / python / typescript)")
    ap.add_argument("--by-lang", metavar="DIR", default=None,
                    help="按语言拆分输出到目录,文件名 {stem}.{lang}.txt")
    ap.add_argument("--list", action="store_true",
                    help="只列出代码块元信息,不输出代码")
    ap.add_argument("--separator", default="\n// ---- next code block ----\n\n",
                    help="代码块之间的分隔符(默认含 // 注释)")
    args = ap.parse_args()

    if args.by_lang:
        out_dir = Path(args.by_lang)
        out_dir.mkdir(parents=True, exist_ok=True)

    total_blocks = 0
    listing: list[tuple[Path, int, str, int]] = []  # (file, idx, lang, lines)
    by_lang_buffers: dict[str, list[str]] = {}
    stdout_chunks: list[str] = []

    for fpath in args.files:
        path = Path(fpath)
        if not path.is_file():
            print(f"warning: not a file, skipping: {fpath}", file=sys.stderr)
            continue
        doc = parse_doc(path)
        for i, blk in enumerate(iter_code_blocks(doc.body)):
            total_blocks += 1
            lang_norm = (blk.lang or "").lower().strip() or "(none)"
            line_count = blk.content.count("\n")
            if args.lang and lang_norm != args.lang.lower():
                continue
            listing.append((path, i, lang_norm, line_count))

            if args.list:
                continue

            if args.by_lang:
                ext = lang_norm if lang_norm != "(none)" else "txt"
                key = f"{path.stem}.{ext}.txt"
                by_lang_buffers.setdefault(key, []).append(blk.content)
            else:
                stdout_chunks.append(blk.content)

    if args.list:
        for path, i, lang, n in listing:
            print(f"{path}\tblock#{i}\tlang={lang}\tlines={n}")
        print(f"\n=== {total_blocks} code block(s) total ===", file=sys.stderr)
        return 0

    if args.by_lang:
        for fname, parts in by_lang_buffers.items():
            (Path(args.by_lang) / fname).write_text(
                args.separator.join(parts), encoding="utf-8"
            )
        print(f"wrote {len(by_lang_buffers)} file(s) to {args.by_lang}", file=sys.stderr)
        return 0

    sys.stdout.write(args.separator.join(stdout_chunks))
    if stdout_chunks:
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
