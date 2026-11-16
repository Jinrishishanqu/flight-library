# -*- coding: utf-8 -*-
"""逐部验证章节划分修复效果。

用法：
    python verify_split.py             # 检查审计里点名的 6 部
    python verify_split.py 185 303     # 检查指定 work id
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import build_db as B  # noqa: E402

DB = HERE / "data" / "library.db"
CANON = ROOT / "校勘版"

CASES = {
    185: "斗破苍穹之恋足大陆（49 处行首第N章却 real=0）",
    303: "斗罗大陆2绝世唐门足交传说（硬切吞下一章标题）",
    307: "斗罗大陆之开局截胡比比东（开篇·续N 吞噬 12 万字）",
    220: "绿帽之斗破苍穹（第三回的时候他忍不住了 / ·续N 17 节）",
    369: "（极短空壳节 21 字）",
    189: "（卷名重复叠加）",
}


def main() -> int:
    con = sqlite3.connect(DB)
    ids = [int(x) for x in sys.argv[1:]] or list(CASES)
    for wid in ids:
        row = con.execute(
            "SELECT title, path_canon FROM works WHERE id=?", (wid,)
        ).fetchone()
        if not row:
            print(f"#{wid} 不存在")
            continue
        title, rel = row
        p = CANON / rel
        if not p.exists():
            print(f"#{wid} 《{title}》 文件缺失 {p}")
            continue
        text = B.load_text(p)
        chunks = B.split_chapters(text)
        real = sum(1 for _, r, _ in chunks if r)
        lens = [len(b) for _, _, b in chunks]
        empty = sum(1 for n in lens if n < B.MIN_BODY)
        longest = max(lens) if lens else 0
        # 复核：是否还有「章标题落在节中段」与「·续N」
        glue = 0
        for _, _, body in chunks:
            for m in B.CHAPTER_RE.finditer(body):
                if body[: m.start()].strip():
                    glue += 1
        cont = sum(1 for t, _, _ in chunks if "·续" in t)
        paren = sum(1 for t, _, _ in chunks if "（" in t and "/" in t)
        vols = sum(1 for t, _, _ in chunks if B.VOL_RE.search(t))
        print(f"#{wid} 《{title}》  {CASES.get(wid, '')}")
        print(f"   节数 {len(chunks)}  真标题 {real}  最短 {min(lens) if lens else 0}  "
              f"最长 {longest}  空壳 {empty}  节中章标 {glue}  ·续N {cont}  （i/n） {paren}  卷名 {vols}")
        for t, r, b in chunks[:4]:
            print(f"   {'真' if r else '切'} {t[:36]:38s} {len(b)}")
        print()
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
