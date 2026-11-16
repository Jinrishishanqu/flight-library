# -*- coding: utf-8 -*-
"""定位正文缺失区间：用锚点滑动，找出原文里哪些片段没进 chapters。

用法：python locate_loss.py 220
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CANON = ROOT / "校勘版"
DB = HERE / "data" / "library.db"
sys.path.insert(0, str(HERE))
from build_db import load_text  # noqa: E402

WS = re.compile(r"\s+")
flat = lambda s: WS.sub("", s or "")  # noqa: E731


def main() -> int:
    wid = int(sys.argv[1])
    con = sqlite3.connect(DB)
    title, rel = con.execute("SELECT title,path_canon FROM works WHERE id=?", (wid,)).fetchone()
    src = flat(load_text(CANON / rel))
    rows = con.execute(
        "SELECT idx,title,content FROM chapters WHERE work_id=? ORDER BY idx", (wid,)
    ).fetchall()
    body = flat("".join(c or "" for _, _, c in rows))
    titles = flat("".join(t or "" for _, t, _ in rows))

    STEP, ANCHOR = 400, 16
    lost: list[tuple[int, int]] = []
    i = 0
    while i + ANCHOR <= len(src):
        probe = src[i : i + ANCHOR]
        if probe not in body and probe not in titles:
            lost.append((i, i + ANCHOR))
            i += ANCHOR
        else:
            i += STEP
    print(f"#{wid} 《{title}》 原文 {len(src)} 正文 {len(body)} 缺失锚点 {len(lost)} 个")
    for a, b in lost[:8]:
        print(f"  @{a}: …{src[max(0,a-40):a+60]}…")
        # 探针之后紧邻的正文位置，帮助确认跳到了哪里
        tail = src[b : b + 14]
        pos = body.find(tail)
        print(f"     探针后文「{tail}」在正文位置 {pos}")
    # 统计被丢弃的总字符：把 lost 区间合并
    merged: list[list[int]] = []
    for a, b in lost:
        if merged and a - merged[-1][1] <= ANCHOR * 2:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    print(f"  合并后缺失区间 {len(merged)} 个，约 {sum(b - a for a, b in merged)} 字符")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
