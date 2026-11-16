# -*- coding: utf-8 -*-
"""重建 chapters_fts：title 与 body_bi 都做 bigram，标题里的词也能被搜到。

contentless FTS5 不支持 'rebuild'，只能整表重建后重灌。

护栏（都踩过坑才加）：
1) body_bi 为空但 content 非空的章节，现场用 content 重算 —— 否则该章永远搜不到
   （实测漏过 3 章 18,874 字：w168 ch21457、w27 ch21458/21459，其中「萧夫人」190 次全漏）
2) 重灌后逐章断言「body_bi 非空」，不一致直接报错退出，不静默放过
3) 单字与拉丁词也进索引（见 build_db.bigram_cn），否则「乳」「NTR」搜不到
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
        "SELECT c.id, c.title, c.body_bi, w.title, c.content FROM chapters c "
        "JOIN works w ON w.id=c.work_id WHERE w.merged_into IS NULL"
    ).fetchall()

    fixed = []
    payload = []
    for cid, title, bi, wtitle, content in rows:
        # body_bi 一律按当前 bigram_cn 重算：旧值可能是旧口径算的
        # （实测：22 章正文含 NTR、55 章含 SM，但 body_bi 里一个都没有，
        #  因为那批数据是「拉丁词被当分隔符丢掉」的旧版本生成的）
        new_bi = bigram_cn(content or "")
        if new_bi != (bi or ""):
            fixed.append(cid)
        payload.append((cid, bigram_cn(title or ""), new_bi, bigram_cn(wtitle or "")))

    if fixed:
        con.executemany(
            "UPDATE chapters SET body_bi=? WHERE id=?",
            [(p[2], p[0]) for p in payload if p[0] in set(fixed)],
        )
        print(f"重算 body_bi：{len(fixed)} 章")

    con.executemany(
        "INSERT INTO chapters_fts(rowid,title,body_bi,work_title) VALUES (?,?,?,?)", payload
    )
    con.execute("INSERT INTO chapters_fts(chapters_fts) VALUES('optimize')")
    con.commit()
    print(f"FTS 重灌完成：{len(rows)} 条")

    # 断言：可见章节里不该再有「有正文但索引为空」
    bad = con.execute(
        "SELECT COUNT(*) FROM chapters c JOIN works w ON w.id=c.work_id "
        "WHERE w.merged_into IS NULL AND (c.body_bi IS NULL OR c.body_bi='') "
        "AND c.content IS NOT NULL AND c.content<>''"
    ).fetchone()[0]
    if bad:
        print(f"[FAIL] 仍有 {bad} 章 body_bi 为空，索引不完整")
        sys.exit(1)

    # 冒烟：与 server.to_fts_query 同口径（单字走前缀、拉丁词直查、多字走 bigram 短语）
    def fts_q(kw: str) -> str:
        parts = []
        for s in __import__("re").findall(r"[\u4e00-\u9fff]+", kw):
            if len(s) < 2:
                parts.append(s + "*")
            else:
                parts.append('"' + " ".join(s[i : i + 2] for i in range(len(s) - 1)) + '"')
        for s in __import__("re").findall(r"[A-Za-z0-9]+", kw):
            parts.append('"' + s.lower() + '"')
        return " AND ".join(parts)

    for kw in ["乳", "NTR", "SM", "薰儿", "升魂丹", "日常周旋于三个女斗宗之间"]:
        n = con.execute(
            "SELECT COUNT(*) FROM chapters_fts WHERE chapters_fts MATCH ?", (fts_q(kw),)
        ).fetchone()[0]
        print(f"  「{kw}」 -> {n} 章")
    con.close()


if __name__ == "__main__":
    main()
