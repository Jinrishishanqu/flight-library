# -*- coding: utf-8 -*-
"""数据库一致性体检，可选修正 char_count 口径。

口径说明：
- `works.char_count` 最初记的是源文件字符数（含章标题）
- `chapters.char_count` 记的是该节正文字数
- `merge_works2.py` 用自己的口径重算过主本，于是两类作品的 char_count 不可比

`--fix-chars` 把 `works.char_count` 统一为 `SUM(chapters.char_count)`，
即「读者真正能看到的正文字数」。

用法：
    python check_db.py
    python check_db.py --fix-chars
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"

Q_CHAR_MISMATCH = """
SELECT w.id, w.title, w.char_count,
       (SELECT SUM(c.char_count) FROM chapters c WHERE c.work_id = w.id) AS real_chars
FROM works w
WHERE w.merged_into IS NULL
  AND ABS(w.char_count
          - (SELECT COALESCE(SUM(c.char_count),0) FROM chapters c WHERE c.work_id = w.id)) > 50
"""


def main() -> int:
    fix = "--fix-chars" in sys.argv
    con = sqlite3.connect(DB, timeout=60)
    q = lambda s, *a: con.execute(s, a).fetchone()[0]

    total = q("SELECT COUNT(*) FROM works")
    vis = q("SELECT COUNT(*) FROM works WHERE merged_into IS NULL")
    print(f"works {total}（可见 {vis} / 已合并 {total - vis}）")
    print(f"chapters {q('SELECT COUNT(*) FROM chapters')}"
          f"  其中可见作品 {q('SELECT COUNT(*) FROM chapters c JOIN works w ON w.id=c.work_id WHERE w.merged_into IS NULL')}")
    print(f"FTS {q('SELECT COUNT(*) FROM chapters_fts')}")
    print(f"characters {q('SELECT COUNT(*) FROM characters')}"
          f"  缺 bio {q('SELECT COUNT(*) FROM characters WHERE bio IS NULL OR bio = ' + chr(39) + chr(39))}")

    print(f"无章节的可见作品 {q('SELECT COUNT(*) FROM works w WHERE merged_into IS NULL AND NOT EXISTS(SELECT 1 FROM chapters c WHERE c.work_id=w.id)')}")
    print(f"空正文的章节 {q('SELECT COUNT(*) FROM chapters WHERE body_bi IS NULL OR body_bi = ' + chr(39) + chr(39))}")
    print(f"缺 AI 简介的可见作品 {q('SELECT COUNT(*) FROM works WHERE merged_into IS NULL AND (summary_ai IS NULL OR summary_ai = ' + chr(39) + chr(39) + ')')}")

    rows = con.execute(Q_CHAR_MISMATCH).fetchall()
    print(f"\nchar_count 与正文和不一致：{len(rows)} 部")
    for r in rows[:5]:
        print(f"   #{r[0]:<4} {r[1][:26]:<26} 记 {r[2]:>8} 实 {r[3]:>8} 差 {r[2]-r[3]:>6}")

    if fix and rows:
        con.execute("""
            UPDATE works
               SET char_count = (SELECT COALESCE(SUM(c.char_count),0)
                                   FROM chapters c WHERE c.work_id = works.id)
             WHERE merged_into IS NULL
        """)
        con.commit()
        after = len(con.execute(Q_CHAR_MISMATCH).fetchall())
        print(f"--fix-chars 已执行，仍不一致 {after} 部")
        print(f"总字数 {q('SELECT SUM(char_count) FROM works WHERE merged_into IS NULL')}")

    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
