# -*- coding: utf-8 -*-
"""校验：chapters 拼接（去掉所有空白）是否等于校勘版原文（去掉所有空白）。

章节标题会被写进 chapters.title，正文里不再含标题行，
所以比对时要允许「原文去空白」包含「正文去空白」这一关系，
且差值应当只来自被吃掉的标题文本。
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


def flat(s: str) -> str:
    return WS.sub("", s or "")


def main() -> int:
    con = sqlite3.connect(DB)
    ids = [int(x) for x in sys.argv[1:]]
    if not ids:
        ids = [r[0] for r in con.execute(
            "SELECT id FROM works WHERE merged_into IS NULL ORDER BY char_count DESC LIMIT 8"
        )]
    for wid in ids:
        w = con.execute("SELECT title,path_canon FROM works WHERE id=?", (wid,)).fetchone()
        if not w:
            continue
        p = CANON / w[1]
        if not p.exists():
            print(f"#{wid} 文件缺失")
            continue
        src = flat(load_text(p))
        rows = con.execute(
            "SELECT title,content FROM chapters WHERE work_id=? ORDER BY idx", (wid,)
        ).fetchall()
        body = flat("".join(c or "" for _, c in rows))
        titles = flat("".join(t or "" for t, _ in rows))
        # 正文里若还残留被吃掉的标题文本，差额会体现出来
        lost = len(src) - len(body) - len(titles)
        print(f"#{wid} 《{w[0]}》 原文 {len(src)} 正文 {len(body)} 标题 {len(titles)} 差 {lost}")
        if lost != 0:
            # 找出正文里缺失的第一段，给出上下文
            i = 0
            while i < min(len(src), len(body)) and src[i] == body[i]:
                i += 1
            print(f"    首个差异位置 {i}: 原文 …{src[max(0,i-30):i+40]}…")
            print(f"                    正文 …{body[max(0,i-30):i+40]}…")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
