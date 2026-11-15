# -*- coding: utf-8 -*-
"""为 works.notes 生成数据质量备注（事实性说明，不做评价）。

写入的条目（用「；」连接）：
  · 原文无完整章标记，按 6000 字切节        —— 来自 章节划分报告.csv
  · 分卷结构（第N卷），卷内章号各自从 1 开始  —— 章节标题里出现「第N卷」
  · 含 N 处私有区字符（源文件乱码，不可逆）    —— 扫校勘版正文
  · 作者未标注                              —— author 为空或「佚名」
  · 已并入《X》                             —— merged_into（子本才有）

用法：python fill_notes.py [--apply]
"""
from __future__ import annotations

import csv
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DB = HERE / "data" / "library.db"
CANON = ROOT / "校勘版"
REPORT = ROOT / "采集工具" / "记录" / "章节划分报告.csv"

VOL_RE = re.compile(r"第[0-9零一二三四五六七八九十百千两]+卷")
PRIVATE = re.compile("[\ue000-\uf8ff]")


def load_modes() -> dict[str, str]:
    """书名 -> 分章模式。"""
    out: dict[str, str] = {}
    if not REPORT.exists():
        return out
    with REPORT.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            title = (row.get("书名") or row.get("title") or "").strip()
            mode = (row.get("模式") or row.get("mode") or "").strip()
            if title and mode:
                out[title] = mode
    return out


def count_private(text: str) -> int:
    return len(PRIVATE.findall(text))


def main() -> int:
    apply = "--apply" in sys.argv
    modes = load_modes()
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT id,title,author,path_canon,merged_into FROM works ORDER BY id"
    ).fetchall()

    private_cache: dict[str, int] = {}
    todo = []
    for wid, title, author, path_canon, merged in rows:
        notes: list[str] = []

        mode = modes.get(title, "")
        if "字数" in mode:
            notes.append("原文无完整章标记，按 6000 字切节")

        nvol = con.execute(
            "SELECT COUNT(*) FROM chapters WHERE work_id=? AND title LIKE '%卷%'", (wid,)
        ).fetchone()[0]
        if nvol:
            notes.append("分卷结构（第N卷），卷内章号各自从 1 开始")

        if path_canon:
            p = CANON / path_canon
            key = str(p)
            if key not in private_cache:
                private_cache[key] = count_private(
                    p.read_text(encoding="utf-8", errors="replace")
                ) if p.exists() else 0
            n = private_cache[key]
            if n:
                notes.append(f"含 {n} 处私有区字符（源文件乱码，不可逆）")

        if not author or author in ("佚名", "（原文未标注）"):
            notes.append("作者未标注")

        if merged:
            pt = con.execute("SELECT title FROM works WHERE id=?", (merged,)).fetchone()
            if pt:
                notes.append(f"已并入《{pt[0]}》")

        todo.append((wid, title, "；".join(notes)))

    filled = [t for t in todo if t[2]]
    for wid, title, note in filled[:8]:
        print(f"  #{wid} {title[:24]:24s} | {note[:70]}")
    print(f"...共 {len(filled)} / {len(todo)} 部有备注")

    if apply:
        con.executemany("UPDATE works SET notes=? WHERE id=?", [(n, w) for w, _, n in todo])
        con.commit()
        print(f"已写库：notes {len(filled)} / {len(todo)}")
    else:
        print("（dry-run，加 --apply 写库）")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
