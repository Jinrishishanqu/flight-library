# -*- coding: utf-8 -*-
"""重建 chapters_fts：title 与 body_bi 都做 bigram，标题里的词也能被搜到。

contentless FTS5 不支持 'rebuild'，只能整表重建后重灌。
"""
import sqlite3, sys, io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_db import bigram_cn  # noqa: E402

DB = Path(__file__).resolve().parent / "data" / "library.db"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def main():
    con = sqlite3.connect(DB)
    con.execute("DROP TABLE IF EXISTS chapters_fts")
    con.execute(
        "CREATE VIRTUAL TABLE chapters_fts USING fts5("
        "title, body_bi, work_title, content='', tokenize='unicode61 remove_diacritics 0')"
    )
    rows = con.execute(
        "SELECT c.id, c.title, c.body_bi, w.title FROM chapters c JOIN works w ON w.id=c.work_id "
        "WHERE w.merged_into IS NULL"
    ).fetchall()
    con.executemany(
        "INSERT INTO chapters_fts(rowid,title,body_bi,work_title) VALUES (?,?,?,?)",
        [(r[0], bigram_cn(r[1] or ""), r[2], bigram_cn(r[3] or "")) for r in rows],
    )
    con.execute("INSERT INTO chapters_fts(chapters_fts) VALUES('optimize')")
    con.commit()
    print(f"FTS 重灌完成：{len(rows)} 条")

    for q in ['"云 云韵"', '"薰 薰儿 儿"']:
        n = con.execute(
            "SELECT COUNT(*) FROM chapters_fts WHERE chapters_fts MATCH ?", (q,)
        ).fetchone()[0]
        print(f"  {q} -> {n}")
    for kw in ["日常周旋于三个女斗宗之间", "升魂丹", "忽悠之王雅妃"]:
        bg = " ".join(kw[i:i + 2] for i in range(len(kw) - 1))
        n = con.execute(
            "SELECT COUNT(*) FROM chapters_fts WHERE chapters_fts MATCH ?", (f'"{bg}"',)
        ).fetchone()[0]
        print(f"  标题词「{kw}」 -> {n}")
    con.close()


if __name__ == "__main__":
    main()
