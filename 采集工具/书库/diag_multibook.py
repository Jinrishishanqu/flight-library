# -*- coding: utf-8 -*-
"""诊断：全库有多少作品的章号序列是「多套」（章号重新从 1 开始）。

判定：章号序列里出现回退（nos[i] < nos[i-1]）且此后还有 >=3 章，
      说明这个文件其实是多部书拼接，`order_by_chapter` 会把它们交错搅碎。

用法：python diag_multibook.py            # 只汇总
      python diag_multibook.py 443 168    # 打印指定作品的前 60 行
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"

CN_DIGIT = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
            "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNIT = {"十": 10, "百": 100, "千": 1000}


def chap_no(title: str):
    """从「第十二章xxx」取 12；取不到返回 None。"""
    import re
    m = re.search(r"第([0-9零一二三四五六七八九十百千两]+)[章节回卷]", title or "")
    if not m:
        return None
    s = m.group(1)
    if s.isdigit():
        return int(s)
    total = 0
    cur = 0
    for ch in s:
        if ch in CN_DIGIT:
            cur = CN_DIGIT[ch]
        elif ch in CN_UNIT:
            total += (cur or 1) * CN_UNIT[ch]
            cur = 0
        else:
            return None
    return total + cur


def resets(nos):
    """返回回退点列表 [(位置, 前一章号, 当前章号)]，只记后面还有 >=3 章的。"""
    out = []
    for i in range(1, len(nos)):
        a, b = nos[i - 1], nos[i]
        if a is None or b is None:
            continue
        if b < a and len(nos) - i >= 3:
            out.append((i, a, b))
    return out


def main() -> int:
    show = [int(x) for x in sys.argv[1:] if x.isdigit()]
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT id,title,chapter_count FROM works "
        "WHERE merged_into IS NULL ORDER BY id").fetchall()
    bad = []
    for wid, title, _n in rows:
        chs = con.execute(
            "SELECT idx,title FROM chapters WHERE work_id=? ORDER BY idx",
            (wid,)).fetchall()
        nos = [chap_no(t) for _, t in chs]
        rs = resets(nos)
        if rs:
            bad.append((wid, title, len(chs), len(rs), rs[:3]))
    print(f"可见作品 {len(rows)}，章号回退（疑似多部拼接）{len(bad)} 部")
    print(f"{'id':>5} {'节':>4} {'回退':>4}  标题 / 前几处回退")
    for wid, title, n, k, rs in bad:
        print(f"{wid:>5} {n:>4} {k:>4}  {title[:42]}  {rs}")
    for wid in show:
        print(f"\n==== #{wid} ====")
        chs = con.execute(
            "SELECT idx,title,is_real_title,char_count FROM chapters "
            "WHERE work_id=? ORDER BY idx", (wid,)).fetchall()
        for i, (idx, title, real, cc) in enumerate(chs[:60]):
            nos = chap_no(title)
            print(f"{idx:>4} 章号={str(nos):>4} real={real} {cc:>6}  {title[:46]}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
