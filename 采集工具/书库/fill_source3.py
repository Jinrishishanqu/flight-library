# -*- coding: utf-8 -*-
"""第三次补 `path_source`：用正文内容反查原文文件（文件名怎么改都能命中）。

原理：`原文\` 里的原始文件经过 S1 排版层变成 `校对后文章\`，再经 S2/S3 变成 `校勘版\`。
S1 只动排版不动字，所以 `works` 第 1 节的正文前几百字必然能在对应的原文文件里找到
（去掉空白与标点后比对，避开换行差异）。

策略：
1. 取该作品第 1 节正文，清洗成「只留汉字」的串，取前 120 字作指纹
2. 在 `原文\` 全部 txt 里搜这个指纹
3. 同一指纹命中多个文件（分卷）→ `|` 连接

用法：
    python fill_source3.py
    python fill_source3.py --apply
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DB = HERE / "data" / "library.db"
SRC_ROOT = ROOT / "原文"
FINGER = 120          # 指纹长度（只留汉字）
HAN = re.compile(r"[^\u4e00-\u9fff]")


def flat(s: str) -> str:
    return HAN.sub("", s or "")


def read_any(p: Path) -> str:
    """原文里 utf-8 与 gb18030 混存，必须回退解码，否则指纹全打不中。"""
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def main() -> int:
    apply_ = "--apply" in sys.argv
    con = sqlite3.connect(DB, timeout=60)
    missing = con.execute(
        "SELECT id,title,source_work FROM works "
        "WHERE merged_into IS NULL AND (path_source IS NULL OR path_source='') ORDER BY id"
    ).fetchall()
    print(f"待补 {len(missing)} 部")

    files = sorted(SRC_ROOT.rglob("*.txt"))
    cache: dict[Path, str] = {}

    def text_of(p: Path) -> str:
        if p not in cache:
            cache[p] = flat(read_any(p))
        return cache[p]

    fixed, unfixed = [], []
    for wid, title, src_work in missing:
        body = con.execute(
            "SELECT content FROM chapters WHERE work_id=? ORDER BY idx LIMIT 1", (wid,)
        ).fetchone()
        if not body:
            unfixed.append((wid, title, "无章节"))
            continue
        # 单一从头开始的指纹会因「works 里标题与正文紧邻、原文里被作者/日期隔开」而失配，
        # 改成取 4 个不重叠片段，命中任意一段即可。
        flatbody = flat(body[0])
        fps = [flatbody[o:o + FINGER] for o in (0, 150, 400, 800)]
        fps = [s for s in fps if len(s) >= 60]
        if not fps:
            unfixed.append((wid, title, "指纹过短"))
            continue
        hits = []
        for p in files:
            t = text_of(p)
            if any(t.find(s) >= 0 for s in fps):
                hits.append(p)
        if not hits:
            unfixed.append((wid, title, "原文无此指纹"))
            continue
        # 同目录优先，减少「同文异本」误绑
        same = [p for p in hits if src_work and p.parent.name == src_work]
        pick = same or hits
        rel = "|".join(str(p.relative_to(ROOT)).replace("/", "\\") for p in pick)
        fixed.append((rel, wid))
        print(f"  #{wid:<4} {title[:24]:<24} -> {rel[:92]}")

    print(f"\n内容匹配命中 {len(fixed)} / {len(missing)}")
    for wid, title, why in unfixed:
        print(f"  未命中 #{wid:<4} {title[:24]:<24} {why}")

    if apply_ and fixed:
        con.executemany("UPDATE works SET path_source=? WHERE id=?", fixed)
        con.commit()
        n = con.execute(
            "SELECT COUNT(*) FROM works WHERE merged_into IS NULL AND path_source IS NOT NULL AND path_source <> ''"
        ).fetchone()[0]
        tot = con.execute("SELECT COUNT(*) FROM works WHERE merged_into IS NULL").fetchone()[0]
        print(f"已写库：path_source {n} / {tot}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
