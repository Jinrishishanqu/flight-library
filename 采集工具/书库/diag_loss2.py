# -*- coding: utf-8 -*-
"""定位 split_chapters 丢掉的原文区间。

做法：原文与输出的 8-gram 集合做差，缺失 gram 聚成区间，打印上下文与
它落在哪个 mark 区间内（好判断是哪个分支吃掉的）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_db import CHAPTER_RE, load_text, split_chapters  # noqa: E402

WS = re.compile(r"\s+")
N = 8


def flat(s: str) -> str:
    return WS.sub("", s or "")


def main() -> int:
    wid = sys.argv[1] if len(sys.argv) > 1 else "220"
    import sqlite3

    db = Path(__file__).resolve().parent / "data" / "library.db"
    con = sqlite3.connect(db)
    row = con.execute("SELECT title, path_canon FROM works WHERE id=?", (int(wid),)).fetchone()
    if not row:
        print("no such work")
        return 1
    title, rel = row
    root = Path(__file__).resolve().parents[2]
    p = root / "校勘版" / rel
    text = load_text(p)
    src = flat(text)
    ch = split_chapters(text)
    body = flat("".join(b for _, _, b in ch))
    print(f"#{wid} 《{title}》 原文 {len(src)} 正文 {len(body)} 差 {len(src)-len(body)}")

    have = {body[i : i + N] for i in range(len(body) - N + 1)}
    miss: list[int] = [i for i in range(len(src) - N + 1) if src[i : i + N] not in have]
    if not miss:
        print("无缺失")
        return 0

    # 聚成区间（相邻或间隔很近的算同一段）
    runs: list[list[int]] = []
    for i in miss:
        if runs and i - runs[-1][1] <= 2 * N:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    print(f"缺失 gram {len(miss)} 个，聚成 {len(runs)} 段")

    marks = list(CHAPTER_RE.finditer(text))
    # flat 偏移 → 原偏移 的近似映射（只用来判断落在哪个 mark 附近）
    def near_mark(pos: int) -> str:
        best, bd = None, 10**9
        for m in marks:
            d = abs(len(flat(text[: m.start()])) - pos)
            if d < bd:
                bd, best = d, m
        return f"{best.group(0).strip()[:26]}（距 {bd}）" if best else "—"

    for a, b in runs[:12]:
        seg = src[max(0, a - 10) : b + N + 10]
        print(f"\n[{len(src[max(0,a):b+N])} 字] @{a}")
        print(f"  原文: …{seg}…")
        print(f"  最近的 mark: {near_mark(a)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
