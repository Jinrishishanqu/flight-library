# -*- coding: utf-8 -*-
"""用 AI 写好的 bio 校正角色性别。

bio 是专门为某个角色写的第三人称叙述，里面的「他/她」几乎都指向本人 ——
这比在正文里统计代词可靠得多（正文里「韩立看着她」的「她」是别人）。

规则：bio 里「她」出现 ≥2 次且是「他」的 2 倍以上 → 女；反之男；否则不动。
只覆盖 gender 为「不明」或与 bio 矛盾的记录；--apply 才写库。
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"


def main() -> int:
    apply = "--apply" in sys.argv
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT id, name, gender, bio FROM characters"
        " WHERE bio IS NOT NULL AND length(bio) > 20"
    ).fetchall()
    fixed = 0
    for cid, name, gender, bio in rows:
        f = bio.count("她")
        m = bio.count("他")
        if f >= 2 and f > m * 2:
            want = "女"
        elif m >= 2 and m > f * 2:
            want = "男"
        else:
            continue
        if gender == want:
            continue
        if apply:
            con.execute("UPDATE characters SET gender=? WHERE id=?", (want, cid))
        if fixed < 20:
            print(f"  #{cid} {name}: {gender} → {want}  (bio 她{f}/他{m})")
        fixed += 1
    if apply:
        con.commit()
    print(f"{'已写入' if apply else '待写入（--apply 才执行）'}：{fixed} 条")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
