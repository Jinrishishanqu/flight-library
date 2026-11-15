# -*- coding: utf-8 -*-
"""普查书名：找出数字开头、序号残留、分卷前缀等明显不对的标题。"""
import re, sqlite3, sys, io
from pathlib import Path

DB = Path(__file__).resolve().parent / "data" / "library.db"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DIGIT_HEAD = re.compile(r"^\s*[0-9０-９]")
RANGE_HEAD = re.compile(r"^\s*[0-9０-９]+\s*[-~～_—至]\s*[0-9０-９]*")
BRACKET_NUM = re.compile(r"[（(]\s*[0-9]+\s*[-~～]?\s*[0-9]*\s*[)）]")
TRAIL_VOL = re.compile(r"[\s\-_]*[0-9]+\s*卷\s*$")
PAREN_TAIL = re.compile(r"[（(][^（()）]{1,12}[)）]\s*$")


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id,title,slug,path_canon FROM works ORDER BY id"
    ).fetchall()

    digit, rng, brk, vol, other = [], [], [], [], []
    for w in rows:
        t = w["title"]
        if RANGE_HEAD.match(t):
            rng.append(w)
        elif DIGIT_HEAD.match(t):
            digit.append(w)
        elif BRACKET_NUM.search(t):
            brk.append(w)
        elif TRAIL_VOL.search(t):
            vol.append(w)

    def show(name, lst, limit=40):
        print(f"\n===== {name}（{len(lst)} 部）=====")
        for w in lst[:limit]:
            print(f'  {w["id"]:>4}  {w["title"]}')
            print(f'        slug={w["slug"]}')
        if len(lst) > limit:
            print(f"  …还有 {len(lst) - limit} 部")

    show("数字范围开头", rng)
    show("数字开头", digit)
    show("书名里带（数字）", brk)
    show("末尾带卷数", vol)
    print(f"\n总计 {len(rows)} 部；命中数字开头 {len(rng)+len(digit)} 部")
    con.close()


if __name__ == "__main__":
    main()
