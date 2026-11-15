# -*- coding: utf-8 -*-
"""字符级重合率（8-gram 集合），用于判定两篇是否同一文本。

段级去重在「分段切法不同」时会失效（同文被切成不同段 → 前缀对不上），
字符级 8-gram 不受分段影响，是判「同文 / 异本」的稳定口径。

用法：python char_overlap.py <id1> <id2>
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"
PUNCT = re.compile(r"[\s，。！？；：、…—～·「」『』“”‘’（）【】]+")


def grams(text: str, n: int = 8) -> set[str]:
    t = PUNCT.sub("", text)
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    ids = [int(x) for x in sys.argv[1:3]]
    con = sqlite3.connect(DB)
    out = []
    for i in ids:
        row = con.execute("SELECT id,title FROM works WHERE id=?", (i,)).fetchone()
        body = "".join(r[0] for r in con.execute(
            "SELECT content FROM chapters WHERE work_id=? ORDER BY idx", (i,)))
        out.append((row[0], row[1], body, grams(body)))
    (a, ta, ba, ga), (b, tb, bb, gb) = out
    inter = len(ga & gb)
    cont_a = inter / max(1, len(ga))
    cont_b = inter / max(1, len(gb))
    jac = inter / max(1, len(ga | gb))
    print(f"#{a}《{ta}》 {len(ba)} 字 / {len(ga)} grams")
    print(f"#{b}《{tb}》 {len(bb)} 字 / {len(gb)} grams")
    print(f"交集 {inter}")
    print(f"A 被 B 覆盖 containment = {cont_a:.4f}")
    print(f"B 被 A 覆盖 containment = {cont_b:.4f}")
    print(f"Jaccard = {jac:.4f}")
    only_a = len(ga - gb)
    only_b = len(gb - ga)
    print(f"仅 A 有 {only_a} grams（约 {only_a * 0.5:.0f} 字）  仅 B 有 {only_b} grams（约 {only_b * 0.5:.0f} 字）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
