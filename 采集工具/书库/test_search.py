# -*- coding: utf-8 -*-
"""检索质量实测：bigram FTS5 能不能扛住 1900 万字的中文查询。"""
import re
import sqlite3
import sys
import time
from pathlib import Path

DB = Path(__file__).resolve().parent / "data" / "library.db"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_db import bigram_cn  # noqa: E402


def to_query(q: str) -> str:
    segs = re.findall(r"[\u4e00-\u9fff]+", q)
    phrases = []
    for s in segs:
        if len(s) < 2:
            continue
        bg = [s[i : i + 2] for i in range(len(s) - 1)]
        phrases.append('"' + " ".join(bg) + '"')
    return " AND ".join(phrases)


con = sqlite3.connect(DB)
TESTS = ["薰儿", "美杜莎", "斗气化马", "萧炎", "云韵", "洛璃", "娇喘", "紫妍", "唐三", "淫水"]
print(f"{'查询':<8} {'短语式':<26} {'命中章节':>8} {'耗时ms':>8}  首条")
for q in TESTS:
    fq = to_query(q)
    t0 = time.time()
    rows = con.execute(
        "SELECT c.work_id, c.idx, w.title, c.title FROM chapters_fts f "
        "JOIN chapters c ON c.id = f.rowid JOIN works w ON w.id = c.work_id "
        "WHERE chapters_fts MATCH ? LIMIT 3",
        (fq,),
    ).fetchall()
    dt = (time.time() - t0) * 1000
    total = con.execute(
        "SELECT COUNT(*) FROM chapters_fts WHERE chapters_fts MATCH ?", (fq,)
    ).fetchone()[0]
    head = f"{rows[0][2][:14]}/{rows[0][3]}" if rows else "-"
    print(f"{q:<8} {fq[:26]:<26} {total:>8} {dt:>8.1f}  {head}")

print("\n--- 元数据检索 ---")
print("原作分布：")
for r in con.execute(
    "SELECT source_work, COUNT(*), SUM(char_count) FROM works GROUP BY source_work ORDER BY 3 DESC"
):
    print(f"  {str(r[0]):<12} {r[1]:>4} 部  {r[2] or 0:>10,} 字")
print("标签 Top15：")
for r in con.execute("SELECT name, count FROM tags ORDER BY count DESC LIMIT 15"):
    print(f"  {r[0]:<12} {r[1]}")
print("角色 Top10：")
for r in con.execute(
    "SELECT name, SUM(mentions) m FROM characters GROUP BY name ORDER BY m DESC LIMIT 10"
):
    print(f"  {r[0]:<12} {r[1]}")
print("章节数分布：")
for r in con.execute(
    "SELECT CASE WHEN chapter_count<=5 THEN '1-5' WHEN chapter_count<=20 THEN '6-20' "
    "WHEN chapter_count<=50 THEN '21-50' ELSE '50+' END g, COUNT(*) FROM works GROUP BY g"
):
    print(f"  {r[0]:<8} {r[1]}")
n = con.execute("SELECT COUNT(*) FROM chapters WHERE is_real_title=1").fetchone()[0]
print(f"真实章标题章节数：{n} / 3177")
