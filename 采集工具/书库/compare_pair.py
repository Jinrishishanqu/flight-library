# -*- coding: utf-8 -*-
"""并排看两篇作品的开头与重合情况，用于人工确认是否同一篇。

用法：python compare_pair.py 367 388
"""
import io
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def flat(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def keys(text: str) -> list[str]:
    out = []
    for p in re.split(r"[\r\n]+", text):
        k = flat(p)[:24]
        if len(k) >= 12:
            out.append(k)
    return out


def main():
    if len(sys.argv) < 3:
        print("用法：python compare_pair.py <id1> <id2>")
        return
    a, b = int(sys.argv[1]), int(sys.argv[2])
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    data = {}
    for wid in (a, b):
        w = con.execute("SELECT id,title,char_count,chapter_count,path_canon FROM works WHERE id=?", (wid,)).fetchone()
        chs = con.execute("SELECT idx,title,content FROM chapters WHERE work_id=? ORDER BY idx", (wid,)).fetchall()
        body = "\n".join(c["content"] for c in chs)
        data[wid] = {"w": w, "chs": chs, "body": body, "keys": keys(body)}
        print(f"#{wid} 《{w['title']}》  {w['char_count']} 字 / {w['chapter_count']} 节")
        print(f"    文件: {w['path_canon']}")
        print(f"    开头: {flat(body)[:220]}")
        print()

    ka, kb = data[a]["keys"], data[b]["keys"]
    sa, sb = set(ka), set(kb)
    inter = sa & sb
    print(f"段级重合: {len(inter)} / min({len(sa)},{len(sb)}) = "
          f"{len(inter) / max(1, min(len(sa), len(sb))):.2f}")
    only_a = [k for k in ka if k not in sb]
    only_b = [k for k in kb if k not in sa]
    print(f"仅 #{a} 有的段: {len(only_a)}   仅 #{b} 有的段: {len(only_b)}")
    for k in only_a[:5]:
        print(f"    [A独有] {k}")
    for k in only_b[:5]:
        print(f"    [B独有] {k}")
    con.close()


if __name__ == "__main__":
    main()
