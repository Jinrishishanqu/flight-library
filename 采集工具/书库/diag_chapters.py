# -*- coding: utf-8 -*-
"""诊断：某章节所属作品为什么没按原文章标记切分。"""
import sqlite3, re, sys, io
from pathlib import Path

DB = Path(__file__).resolve().parent / "data" / "library.db"
ROOT = Path(__file__).resolve().parents[2]

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CHAP = re.compile(r"第[0-9零一二三四五六七八九十百千两]+[章节回]")


def main(cid):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    ch = con.execute("SELECT id,work_id,idx,title,char_count FROM chapters WHERE id=?", (cid,)).fetchone()
    if not ch:
        print("chapter not found:", cid)
        return
    w = con.execute("SELECT id,title,path_canon,chapter_count,char_count FROM works WHERE id=?", (ch["work_id"],)).fetchone()
    print(f"chapter id={ch['id']} work={ch['work_id']} idx={ch['idx']} title={ch['title']} chars={ch['char_count']}")
    print(f"work: {w['title']}  节数={w['chapter_count']} 字数={w['char_count']}")
    print(f"path: {w['path_canon']}")

    p = Path(w["path_canon"])
    if not p.is_absolute():
        p = ROOT / "校勘版" / p
    if not p.exists():
        print("!! 文件不存在:", p)
        return
    raw = p.open("r", encoding="utf-8", errors="replace", newline="").read()
    print(f"磁盘: {len(raw)} 字符")
    hits = CHAP.findall(raw)
    print(f"章标记总数: {len(hits)}")
    uniq = []
    for m in CHAP.finditer(raw):
        t = m.group(0)
        if t not in uniq:
            uniq.append(t)
    print(f"唯一标记数: {len(uniq)} -> {uniq[:8]}{' ...' if len(uniq) > 8 else ''}")

    # 标记是否独占一行
    alone = glued = 0
    for m in CHAP.finditer(raw):
        s = m.start()
        rest = raw[m.end():m.end() + 40]
        prev = raw[max(0, s - 2):s]
        line_break_after = rest.startswith("\r\n") or rest.startswith("\n")
        if line_break_after:
            alone += 1
        else:
            glued += 1
    print(f"标记后立刻换行: {alone}   后面还连着内容: {glued}")

    # 看第 83 章附近的原文
    i = raw.find("第83章")
    if i > 0:
        print("\n---- 第83章 上下文 ----")
        print(repr(raw[max(0, i - 60):i + 80]))
    else:
        j = raw.find("第八十三章")
        if j > 0:
            print("\n---- 第八十三章 上下文 ----")
            print(repr(raw[max(0, j - 60):j + 80]))

    # 该 work 现有章节标题分布
    rows = con.execute("SELECT idx,title,is_real_title,char_count FROM chapters WHERE work_id=? ORDER BY idx LIMIT 6", (w["id"],)).fetchall()
    print("\n现有前 6 节:", [(r["idx"], r["title"], r["is_real_title"], r["char_count"]) for r in rows])
    con.close()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1001)
