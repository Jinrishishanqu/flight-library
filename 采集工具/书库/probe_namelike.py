# -*- coding: utf-8 -*-
"""量一下几个词在一个作品里的 head/strong 比率，用来定阈值。"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"

ACT_AFTER = ("道", "说", "笑", "问", "答", "怒", "叹", "点头", "摇头", "看", "听",
             "便", "也", "却", "又", "已", "正", "把", "被", "将", "向", "对",
             "和", "与", "给", "让", "低", "抬", "转", "站", "坐", "走", "跑",
             "伸", "心", "身", "眼", "脸", "手", "眉", "嘴", "头", "脚", "腰")
PUNCT = set("。！？…”’」』：；、，\n \t（《「『\"'—-~　")


def is_han(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def name_like(text: str, name: str) -> tuple[float, float, int]:
    n = text.count(name)
    if n == 0:
        return 0.0, 0.0, 0
    head_ok = strong = 0
    start = 0
    L = len(name)
    while True:
        i = text.find(name, start)
        if i < 0:
            break
        start = i + 1
        before = text[i - 1] if i else "\n"
        after = text[i + L: i + L + 2]
        h = (not is_han(before)) or before in PUNCT
        if h:
            head_ok += 1
        a = (after[:1] in PUNCT) or any(after.startswith(w) for w in ACT_AFTER)
        if h and a:
            strong += 1
    return head_ok / n, strong / n, n


def main() -> int:
    wid = int(sys.argv[1]) if len(sys.argv) > 1 else 303
    names = sys.argv[2:] or ["霍雨浩", "王秋儿", "江楠楠", "贝贝", "徐三石", "唐舞桐",
                             "暴露", "高贵", "冷冰冰", "花带雨", "双赤红", "朱露",
                             "巫风", "王言", "季绝尘", "碧姬", "蓝洛洛", "斗灵"]
    con = sqlite3.connect(DB)
    full = "\n".join(r[0] for r in con.execute(
        "SELECT content FROM chapters WHERE work_id=? ORDER BY idx", (wid,)))
    print(f"work {wid}  {len(full)} 字符")
    for w in names:
        h, s, n = name_like(full, w)
        print(f"{w:8s} n={n:6d} head={h:.2f} strong={s:.2f}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
