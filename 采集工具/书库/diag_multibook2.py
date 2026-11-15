# -*- coding: utf-8 -*-
"""诊断：直接扫校勘版原文，看章号序列在原文件里是否回退（=多部书拼接）。

DB 里已经排过序，看不出问题，必须回到文件。

用法：python diag_multibook2.py                  # 汇总
      python diag_multibook2.py 诛仙之青云淫徒    # 打印该文件的章标题顺序
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANON = ROOT / "校勘版"

CHAPTER_RE = re.compile(
    r"(?m)^[ \t]*(第[0-9零一二三四五六七八九十百千两]+[章节回卷]|序章|楔子|序言|前言|后记|尾声|终章|番外)"
    r"[^\r\n]{0,40}\r?$")

CN_DIGIT = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
            "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNIT = {"十": 10, "百": 100, "千": 1000}


def chap_no(title: str):
    m = re.search(r"第([0-9零一二三四五六七八九十百千两]+)[章节回卷]", title or "")
    if not m:
        return None
    s = m.group(1)
    if s.isdigit():
        return int(s)
    total = cur = 0
    for ch in s:
        if ch in CN_DIGIT:
            cur = CN_DIGIT[ch]
        elif ch in CN_UNIT:
            total += (cur or 1) * CN_UNIT[ch]
            cur = 0
        else:
            return None
    return total + cur


def read_any(fp: Path) -> str:
    for enc in ("utf-8", "gb18030", "utf-16"):
        try:
            return fp.open("r", encoding=enc, errors="strict", newline="").read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    return fp.open("r", encoding="utf-8", errors="replace", newline="").read()


def titles_of(text: str):
    return [m.group(0).strip() for m in CHAPTER_RE.finditer(text)]


def resets(nos):
    out = []
    for i in range(1, len(nos)):
        a, b = nos[i - 1], nos[i]
        if a is None or b is None:
            continue
        if b < a and len(nos) - i >= 3:
            out.append((i, a, b))
    return out


def main() -> int:
    kw = sys.argv[1] if len(sys.argv) > 1 else None
    if kw:
        hits = [p for p in CANON.rglob("*.txt") if kw in p.stem]
        for p in hits[:1]:
            text = read_any(p)
            ts = titles_of(text)
            print(f"==== {p.name}：章标题 {len(ts)} 个 ====")
            prev = None
            for i, t in enumerate(ts):
                n = chap_no(t)
                mark = ""
                if prev is not None and n is not None and prev is not None and n < prev:
                    mark = "  <<< 回退"
                print(f"{i:>4} 章号={str(n):>4}  {t[:50]}{mark}")
                prev = n
        return 0

    rows = []
    for p in sorted(CANON.rglob("*.txt")):
        text = read_any(p)
        ts = titles_of(text)
        nos = [chap_no(t) for t in ts]
        rs = resets(nos)
        if rs:
            rows.append((p.relative_to(CANON).as_posix(), len(ts), len(rs), rs[:3]))
    print(f"扫 {len(list(CANON.rglob('*.txt')))} 文件，章号回退（多部拼接）{len(rows)} 个")
    for name, n, k, rs in rows:
        print(f"{n:>4}章 {k:>2}回退  {name}")
        print(f"        前几处 {rs}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
