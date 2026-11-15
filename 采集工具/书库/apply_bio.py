# -*- coding: utf-8 -*-
"""把 AI 生成的摘要写回库。

输入 JSON（数组），每项：
{
  "work_id": 16,
  "summary": "书籍简介，150-250字，自然段",
  "characters": [
      {"name": "韩立", "gender": "男", "bio": "1-4 个自然段，自然语言描述"}
  ]
}

用法：python apply_bio.py data/bio_out/batch1.json [batch2.json ...]
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"


def apply_one(con, item: dict) -> tuple[int, int]:
    wid = int(item["work_id"])
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    ns = nc = 0
    sm = (item.get("summary") or "").strip()
    if sm:
        con.execute("UPDATE works SET summary_ai=?, summary_at=? WHERE id=?", (sm, now, wid))
        ns = 1
    for c in item.get("characters") or []:
        name = (c.get("name") or "").strip()
        bio = (c.get("bio") or "").strip()
        if not name or not bio:
            continue
        g = (c.get("gender") or "").strip()
        if g not in ("男", "女", "不明"):
            g = None
        if g:
            cur = con.execute(
                "UPDATE characters SET bio=?, bio_at=?, gender=? WHERE work_id=? AND name=?",
                (bio, now, g, wid, name))
        else:
            cur = con.execute(
                "UPDATE characters SET bio=?, bio_at=? WHERE work_id=? AND name=?",
                (bio, now, wid, name))
        nc += cur.rowcount
    return ns, nc


def main() -> int:
    if len(sys.argv) < 2:
        print("用法：python apply_bio.py <json...>")
        return 2
    con = sqlite3.connect(DB)
    tn = tc = 0
    for fp in sys.argv[1:]:
        p = Path(fp)
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("items") if isinstance(data.get("items"), list) else [data]
        data = [x for x in data if isinstance(x, dict) and "work_id" in x]
        for item in data:
            a, b = apply_one(con, item)
            tn += a
            tc += b
        print(f"{p.name}: {len(data)} 部")
    con.commit()
    print(f"写入 summary {tn} 条，character bio {tc} 条")
    left = con.execute("SELECT COUNT(*) FROM works WHERE summary_ai IS NULL").fetchone()[0]
    leftc = con.execute("SELECT COUNT(*) FROM characters WHERE bio IS NULL").fetchone()[0]
    print(f"剩余未生成：works {left} / characters {leftc}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
