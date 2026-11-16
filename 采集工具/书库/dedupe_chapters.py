# -*- coding: utf-8 -*-
"""检测章节级重复：同一部作品里，后出现的节与前面某节内容高度重合。

典型病例：`#3 反转仙逆` 第1/3/4/5章各出现两次（源文件本身就是两套拼在一起）。

判据（两条都要满足）：
- 8-gram containment >= DUP_OV（默认 0.85）—— 双向取其大，容忍删节
- 长度比在 [0.7, 1.4] 之间 —— 防止「短节被长节完整包含」这种正常情况被误杀

用法：
    python dedupe_chapters.py                 # 只报告
    python dedupe_chapters.py --apply         # 删除后面的重复节（保留第一次出现）
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"

DUP_OV = 0.85
DUP_DELETE = 0.98      # 只有几乎逐字相同才整节删；0.85–0.98 之间常有作者改写，保留
LEN_LO, LEN_HI = 0.7, 1.4
N = 8
WS = re.compile(r"\s+")


def flat(s: str) -> str:
    return WS.sub("", s or "")


def grams(s: str, n: int = N) -> set[str]:
    return {s[i : i + n] for i in range(len(s) - n + 1)}


def find_dups(chs: list[tuple[int, str, str]]) -> list[tuple[int, int, float]]:
    """返回 [(重复节 idx, 首次出现 idx, 重合率)]。"""
    out: list[tuple[int, int, float]] = []
    kept: list[tuple[int, set[str], int]] = []      # (idx, grams, len)
    for idx, title, content in chs:
        f = flat(content)
        if len(f) < N * 4:
            continue
        g = grams(f)
        hit = None
        for kidx, kg, klen in kept:
            if not kg:
                continue
            ratio = len(f) / max(1, klen)
            if not (LEN_LO <= ratio <= LEN_HI):
                continue
            ov = len(g & kg) / min(len(g), len(kg))
            if ov >= DUP_OV:
                hit = (kidx, ov)
                break
        if hit:
            out.append((idx, hit[0], hit[1]))
        else:
            kept.append((idx, g, len(f)))
    return out


def main() -> int:
    apply = "--apply" in sys.argv
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT id, title FROM works WHERE merged_into IS NULL ORDER BY id"
    ).fetchall()

    total_dup = 0
    hit_works = 0
    deletable = 0
    to_delete: list[int] = []
    for wid, wtitle in rows:
        chs = con.execute(
            "SELECT idx, title, content FROM chapters WHERE work_id=? ORDER BY idx", (wid,)
        ).fetchall()
        dups = find_dups([(i, t, c) for i, t, c in chs])
        if not dups:
            continue
        hit_works += 1
        total_dup += len(dups)
        by_idx = {i: t for i, t, _ in chs}
        print(f"#{wid} {wtitle}  {len(dups)} 处重复")
        for idx, kidx, ov in dups[:6]:
            flag = "删" if ov >= DUP_DELETE else "留"
            print(f"    [{flag}] 第{idx}节 ⊂ 第{kidx}节  重合 {ov:.3f}   {by_idx.get(idx, '')[:30]!r}")
        if len(dups) > 6:
            print(f"    … 还有 {len(dups) - 6} 处")
        kill = [idx for idx, _, ov in dups if ov >= DUP_DELETE]
        deletable += len(kill)
        if apply and kill:
            ids = con.execute(
                "SELECT id, idx FROM chapters WHERE work_id=?", (wid,)
            ).fetchall()
            idd = {i: d for d, i in ids}
            to_delete.extend(idd[idx] for idx in kill if idx in idd)

    print(f"\n合计：{hit_works} 部作品、{total_dup} 处重复；其中 {deletable} 处可直接删（≥{DUP_DELETE}）")
    if apply and to_delete:
        con.executemany("DELETE FROM chapters WHERE id=?", [(x,) for x in to_delete])
        con.commit()
        print(f"已删除 {len(to_delete)} 节")
        print("下一句必须跑：python rebuild_chapters.py --dry  ← 不要跑 --apply，会覆盖合并内容")
        print("           ：python refresh_fts.py")
        # 重算受影响作品的字数与节数
        for wid in {con.execute("SELECT work_id FROM chapters WHERE id=?", (x,)).fetchone() for x in []}:
            pass
        con.execute(
            "UPDATE works SET chapter_count=(SELECT COUNT(*) FROM chapters WHERE work_id=works.id),"
            " char_count=(SELECT COALESCE(SUM(char_count),0) FROM chapters WHERE work_id=works.id),"
            " reading_minutes=MAX(1, ROUND((SELECT COALESCE(SUM(char_count),0) FROM chapters WHERE work_id=works.id)/400.0))"
        )
        con.commit()
        print("已重算 works 的字数/节数/时长")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
