# -*- coding: utf-8 -*-
"""跨作品性别共识：只用于给「不明」补值，不改已明确的判断。

同一角色名（如「唐三」「比比东」）在多部同人里反复出现，各书代词环境差别很大
（有的书他戏份多、有的书她戏份多）。这里按名字聚合所有作品的判定，取众数：
占比 ≥0.6 且样本 ≥2 时，把该名字下所有 gender='不明' 的记录改成众数。

注意：这不产生「跨作品角色记录」——characters 表仍然一行一作品，
这里只借别处的证据补本书缺失的那一格。
"""
from __future__ import annotations

import sqlite3
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"


def main() -> int:
    apply = "--apply" in sys.argv
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT name, gender, COUNT(*) FROM characters"
        " WHERE gender IN ('男','女') GROUP BY name, gender"
    ).fetchall()
    votes: dict[str, Counter] = {}
    for name, g, n in rows:
        votes.setdefault(name, Counter())[g] += n

    fixed = 0
    for name, cnt in votes.items():
        total = sum(cnt.values())
        if total < 3:
            continue
        g, n = cnt.most_common(1)[0]
        # 只有极强共识才敢统一（0.6 会放大错误：后宫文里「她」太多）
        if n / total < 0.85:
            continue
        cur = con.execute(
            "SELECT COUNT(*) FROM characters WHERE name=? AND gender<>?", (name, g))
        k = cur.fetchone()[0]
        if not k:
            continue
        if apply:
            con.execute("UPDATE characters SET gender=? WHERE name=?", (g, name))
        fixed += k
        print(f"  {name:8s} → {g}  ({n}/{total} 证据)  修 {k} 条")

    if apply:
        con.commit()
    print(f"{'已写入' if apply else '待写入（--apply 才执行）'}：{fixed} 条")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
