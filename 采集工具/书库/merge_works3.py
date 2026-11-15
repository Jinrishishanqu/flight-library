# -*- coding: utf-8 -*-
"""把「同作异名 / 分卷 / 续篇」的子本并进主本。

与 merge_works2.py 的区别（用户 2026-11-16 的要求）：
  旧版按章号把子本章节插到主本对应章号的位置 → 一本书被拆成好多段散落各处。
  新版按「首位交接」处理：
    1. 子本开头连续与主本重合的节整段剔除（那是两书重叠的部分）
    2. 剩下的内容**保持子本原序、作为一整块**插到交接点之后
    3. 主本原有章节的相对顺序完全不动

用法：python merge_works3.py [--dry]
"""
from __future__ import annotations

import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"

# (子本, 主本)。子本并入主本后只标 merged_into，不再单独展示。
PAIRS = [
    (160, 162), (161, 162),
    (196, 197),
    (202, 168), (203, 168), (204, 168), (205, 168),
    (367, 388), (373, 381),
    (351, 328), (77, 58), (359, 271),
    (190, 117), (177, 117),
    (370, 371),
    (167, 175),
    (279, 384),
    (189, 169),
    (294, 317),
    (413, 409),
    (419, 96),
    (97, 27),          # 真续篇：结尾「轰！」与主本开头无缝衔接
]

# 真续篇：内容与主本几乎不重合，但确实是接着往下写的 → 全量追加、不剔除
SEQUEL = {(97, 27)}

SAME_TEXT = 0.85       # 子本整体 8-gram 覆盖率 ≥ 此值 → 判同文（删节/分段差异），只标 merged
SEG_DUP = 0.40         # 单节判「与主本重合」的 10-gram 覆盖率
MIN_UNIQ = 200         # 一节剔除后不足这么多字就不建节
HANDOFF_OV = 0.30      # 判定「这一节主本里也有」的重合阈值


def flat(t: str) -> str:
    return re.sub(r"[^\u4e00-\u9fff]", "", t or "")


def grams(t: str, n: int = 10) -> set[str]:
    s = flat(t)
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


def split_paras(t: str) -> list[str]:
    return [p.strip() for p in re.split(r"\r?\n+", t or "") if p.strip()]


def unique_text(child_text, parent_flat, parent_grams):
    keep, total, dup = [], 0, 0
    for p in split_paras(child_text):
        total += 1
        key = flat(p)[:24]
        if len(key) >= 12 and key in parent_flat:
            dup += 1
            continue
        pg = grams(p, 10)
        if pg and len(pg & parent_grams) / len(pg) >= SEG_DUP:
            dup += 1
            continue
        keep.append(p)
    return "\n".join(keep), total, dup


def head_overlap(child_chs, p_flat, p_grams) -> int:
    """子本开头连续「与主本重合」的节数 —— 这段是两书重叠，要整段剔除。"""
    k = 0
    for ch in child_chs:
        _u, total, dup = unique_text(ch["content"], p_flat, p_grams)
        if total and dup / total >= 0.5:
            k += 1
        else:
            break
    return k


def handoff_idx(child_chs, k, p_chs, p_grams_by_id) -> int | None:
    """子本第 k-1 节（最后一个重叠节）在主本里对应的节 idx。

    找不到就返回 None（两书没有重叠，按末尾追加处理）。
    """
    if k == 0:
        return None
    probe = grams(child_chs[k - 1]["content"], 10)
    if not probe:
        return None
    best = None
    for pc in p_chs:
        pg = p_grams_by_id.get(pc["id"]) or set()
        if not pg:
            continue
        if len(probe & pg) / max(1, len(probe)) >= HANDOFF_OV:
            best = pc["idx"]
    return best


def resequence(con, wid: int) -> None:
    rows = con.execute(
        "SELECT id FROM chapters WHERE work_id=? ORDER BY idx", (wid,)).fetchall()
    for i, (cid,) in enumerate(rows, 1):
        con.execute("UPDATE chapters SET idx=? WHERE id=?", (i, cid))


def merge_one(con, child_id: int, parent_id: int, dry: bool) -> None:
    cw = con.execute("SELECT id,title FROM works WHERE id=?", (child_id,)).fetchone()
    pw = con.execute("SELECT id,title FROM works WHERE id=?", (parent_id,)).fetchone()
    if not cw or not pw:
        print(f"  ! #{child_id} 或 #{parent_id} 不存在，跳过")
        return

    child_chs = con.execute(
        "SELECT id,idx,title,content FROM chapters WHERE work_id=? ORDER BY idx",
        (child_id,)).fetchall()
    p_chs = con.execute(
        "SELECT id,idx,title,content FROM chapters WHERE work_id=? ORDER BY idx",
        (parent_id,)).fetchall()
    if not child_chs:
        print(f"  - #{child_id}《{cw['title']}》没有章节，跳过")
        return

    p_flat = flat("".join(c["content"] for c in p_chs))
    p_grams = set()
    for c in p_chs:
        p_grams |= grams(c["content"], 8)
    p_grams_by_id = {c["id"]: grams(c["content"], 10) for c in p_chs}

    is_seq = (child_id, parent_id) in SEQUEL
    body_all = "".join(c["content"] for c in child_chs)
    cover = len(grams(body_all, 8) & p_grams) / max(1, len(grams(body_all, 8)))

    if not is_seq and cover >= SAME_TEXT:
        print(f"  = #{child_id}《{cw['title']}》同文覆盖 {cover:.3f} ≥ {SAME_TEXT} "
              f"→ 只标合并、不追加章节")
        if not dry:
            con.execute("UPDATE works SET merged_into=? WHERE id=?", (parent_id, child_id))
        return

    k = 0 if is_seq else head_overlap(child_chs, p_flat, p_grams)
    handoff = handoff_idx(child_chs, k, p_chs, p_grams_by_id)
    if is_seq:
        # 续篇：接着主本最后一章往下写
        handoff = p_chs[-1]["idx"] if p_chs else 0

    base = handoff if handoff is not None else (p_chs[-1]["idx"] if p_chs else 0)
    rest = child_chs[k:]

    kept = []
    for ch in rest:
        uniq, _total, _dup = unique_text(ch["content"], p_flat, p_grams)
        if len(flat(uniq)) < MIN_UNIQ:
            continue
        kept.append((ch["title"], uniq))

    kind = "续篇全量" if is_seq else f"剔除头部 {k} 节重合后"
    uniq_chars = sum(len(flat(b)) for _, b in kept)
    if not kept:
        print(f"  - #{child_id}《{cw['title']}》{kind} 无独有内容"
              f"（覆盖 {cover:.3f}）→ 只标合并")
        if not dry:
            con.execute("UPDATE works SET merged_into=? WHERE id=?", (parent_id, child_id))
        return

    prefix = "续 · " if is_seq else "另版 · "
    print(f"  + #{child_id}《{cw['title']}》{kind} 独有 {len(kept)} 节 "
          f"（{uniq_chars} 字）"
          f"→ 整块插入 #{parent_id} 的章{base} 之后")

    if dry:
        return

    # 把 base 之后的节整体后移，空出位置
    con.execute("UPDATE chapters SET idx = idx + ? WHERE work_id=? AND idx > ?",
                (len(kept), parent_id, base))
    for i, (title, body) in enumerate(kept, 1):
        con.execute(
            "INSERT INTO chapters(work_id,idx,title,is_real_title,content,body_bi,char_count)"
            " VALUES(?,?,?,0,?,'',?)",
            (parent_id, base + i, prefix + (title or f"第{i}节"), body, len(body)))
    resequence(con, parent_id)
    con.execute("UPDATE works SET merged_into=? WHERE id=?", (parent_id, child_id))


def refresh_work(con, wid: int) -> None:
    n, chars = con.execute(
        "SELECT COUNT(*), COALESCE(SUM(char_count),0) FROM chapters WHERE work_id=?",
        (wid,)).fetchone()
    con.execute(
        "UPDATE works SET chapter_count=?, char_count=?, reading_minutes=?, updated_at=?"
        " WHERE id=?",
        (n, chars, max(1, round(chars / 400)),
         datetime.now().strftime("%Y-%m-%d %H:%M"), wid))


def main() -> int:
    dry = "--dry" in sys.argv
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    if not dry:
        con.execute("UPDATE works SET merged_into=NULL WHERE merged_into IS NOT NULL")

    print(f"{'[预演]' if dry else '[执行]'} {len(PAIRS)} 对")
    touched = set()
    for child, parent in PAIRS:
        merge_one(con, child, parent, dry)
        touched.add(parent)

    if not dry:
        for wid in sorted(touched):
            refresh_work(con, wid)
        con.commit()
        print("FTS 未自动重灌，接着跑：python refresh_fts.py")
    print(f"主本：{sorted(touched)}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
