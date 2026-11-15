# -*- coding: utf-8 -*-
"""补 works.description —— 结构化的一句话定位。

与 summary_ai（140–240 字散文简介）分工不同：
  summary_ai  详情页正文上方那段散文
  description 列表/搜索/分享卡片用的一句话，便于扫读与外部引用

内容 = 题材 + 原作 + 主题 + 主要角色 + 篇幅，全部取自库内已有字段，不调用 AI。

用法：python fill_desc.py [--apply]
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"


def wan(n: int) -> str:
    return f"{n / 10000:.1f} 万字" if n >= 10000 else f"{n} 字"


def build(w: sqlite3.Row, names: list[str]) -> str:
    parts: list[str] = []
    if w["source_work"]:
        parts.append(f"《{w['source_work']}》同人")
    elif w["genre"]:
        parts.append(w["genre"])

    if w["theme"]:
        parts.append(f"主题「{w['theme']}」")
    if w["pairing"]:
        parts.append(w["pairing"])

    if names:
        head = "、".join(names[:4])
        parts.append(f"主要角色 {head}" + (f" 等 {len(names)} 人" if len(names) > 4 else ""))

    parts.append(f"{wan(w['char_count'])}，{w['chapter_count']} 节")
    return "。".join(parts) + "。"


def main() -> int:
    apply = "--apply" in sys.argv
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    works = con.execute(
        "SELECT id,title,genre,source_work,theme,pairing,char_count,chapter_count "
        "FROM works WHERE merged_into IS NULL ORDER BY id"
    ).fetchall()

    n = 0
    for w in works:
        names = [r[0] for r in con.execute(
            "SELECT name FROM characters WHERE work_id=? "
            "ORDER BY score DESC, mentions DESC LIMIT 6", (w["id"],))]
        desc = build(w, names)
        if apply:
            con.execute("UPDATE works SET description=? WHERE id=?", (desc, w["id"]))
        n += 1
        if n <= 3:
            print(f"  #{w['id']} {w['title']}\n    -> {desc}")

    if apply:
        con.commit()
    left = con.execute(
        "SELECT COUNT(*) FROM works WHERE merged_into IS NULL AND (description IS NULL OR description='')"
    ).fetchone()[0]
    print(("已写库" if apply else "预演") + f"：description {n} 部，缺 {left} 部")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
