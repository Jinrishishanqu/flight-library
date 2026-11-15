# -*- coding: utf-8 -*-
"""辰东/待归类 拆分后，同步数据库的 source_work、path_* 与作品标签。

用法：python update_source_works.py [--apply]
"""
from __future__ import annotations

import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"F:\新建文件夹\read - 副本")
DB = ROOT / "采集工具" / "书库" / "data" / "library.db"
CANON = ROOT / "校勘版"
OLD_TREES = {"辰东", "待归类"}
OLD_TAG = "辰东作品集"


def main() -> int:
    apply = "--apply" in sys.argv
    # 校勘版 下 文件名 -> 作品目录
    name2work: dict[str, str] = {}
    for d in CANON.iterdir():
        if not d.is_dir():
            continue
        for p in d.glob("*.txt"):
            name2work[p.name] = d.name

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id,title,source_work,path_canon,path_proof,path_source FROM works"
    ).fetchall()

    plan = []
    for r in rows:
        pc = (r["path_canon"] or "").replace("\\", "/")
        if "/" not in pc:
            continue
        folder, fname = pc.split("/", 1)
        if folder not in OLD_TREES:
            continue
        work = name2work.get(fname)
        if not work:
            print("找不到目标目录:", pc)
            continue
        plan.append((r["id"], r["title"], r["source_work"], work,
                     f"{work}/{fname}",
                     (r["path_proof"] or "").replace(f"/{folder}/", f"/{work}/"),
                     (r["path_source"] or "").replace(f"/{folder}/", f"/{work}/")
                     if r["path_source"] else None))

    for pid, title, old, work, pc, pp, ps in plan:
        print(f"#{pid} {title} | {old} -> {work} | {pc}")
    print()
    print("统计:", Counter(p[3] for p in plan), "共", len(plan), "部")

    if not apply:
        return 0

    for pid, _t, _o, work, pc, pp, ps in plan:
        con.execute(
            "UPDATE works SET source_work=?, path_canon=?, path_proof=?, path_source=?, updated_at=datetime('now','localtime') WHERE id=?",
            (work, pc, pp, ps, pid))
        # 作品标签
        con.execute(
            "DELETE FROM work_tags WHERE work_id=? AND tag_id=(SELECT id FROM tags WHERE name=?)",
            (pid, OLD_TAG))
        cur = con.execute("SELECT id FROM tags WHERE name=?", (work,)).fetchone()
        if cur:
            tid = cur["id"]
        else:
            kind = "原作"
            tid = con.execute("INSERT INTO tags(name,kind) VALUES(?,?)", (work, kind)).lastrowid
        con.execute("INSERT OR IGNORE INTO work_tags(work_id,tag_id) VALUES(?,?)", (pid, tid))

    # 清理不再被引用的旧标签
    left = con.execute("SELECT COUNT(*) FROM work_tags WHERE tag_id=(SELECT id FROM tags WHERE name=?)",
                       (OLD_TAG,)).fetchone()[0]
    if left == 0:
        con.execute("DELETE FROM tags WHERE name=?", (OLD_TAG,))
        print("删除空标签", OLD_TAG)

    con.commit()
    print("已更新", len(plan), "部作品")
    return 0


if __name__ == "__main__":
    sys.exit(main())
