# -*- coding: utf-8 -*-
"""按「章号 + 文件内顺序」合并同作异名/分卷。

用户要求（m07847）：
- 不要生硬地把内容堆到末尾，要按上下文排序后拼接
- 排序的对象是**原文件**，同一个原文件内的章节顺序不动

做法：
1. 从子作品里取出主本没有的段落（段级去重，前 24 字比对）
2. 把这些段落组装成「子章节」，章号从子作品标题里的「第N章」取，取不到就继承上一节
3. 主本章节 + 子章节一起按 (章号, 主本优先, 原序) 稳定排序，重写 idx

用法：python merge_works2.py [--dry|--apply]
"""
import io
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_db import bigram_cn, chap_no, load_text  # noqa: E402

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"
ROOT = HERE.parents[1]
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 人工确认过的配对：(子作品 id, 主本 id)
PAIRS = [
    (160, 162), (161, 162),      # 斗破淫传分卷 -> 斗破淫传
    (196, 197),                  # 萧薰儿的征程短版 -> 长版
    (202, 168), (203, 168), (204, 168), (205, 168),  # 改编版各章独立文件 -> 合本
    (367, 388),                  # 邪恶主神短版 -> 霍雨浩的邪恶主神（重合 0.99）
    (373, 381),                  # 霍雨浩x王秋儿 -> 霍雨浩与王秋儿（重合 0.81）
    (351, 328),                  # 笑红尘与江楠楠 -> 江楠楠（子集，独有 0 段）
    (77, 58),                    # 武盈盈 -> 大主宰武盈盈（独有 1 段）
    (359, 271),                  # 绝世淫门 唐雅的堕落 -> 唐雅（独有 1 段）
    (190, 117),                  # 淫帝无双 -> 淫帝无双·操破苍穹（独有 35 段）
    (177, 117),                  # yin帝无双 -> 同上（190 的子集）
    (370, 371),                  # 雪帝 -> 雪帝与霍雨浩（独有 3 段）
    (167, 175),                  # 斗破苍穹 魔法学院 -> 斗破苍穹（萧黛儿/萧薰儿人名变体，同文 0.98）
    (279, 384),                  # 小桃 -> 霍雨浩与马小桃（子集，containment 1.00）
    (189, 169),                  # 斗破苍穹之淫宗肆虐 -> 斗破苍穹-淫宗肆虐（子集 0.92）
    (294, 317),                  # 斗破 -> 斗罗小狂四部曲（子集 0.9924）
    (413, 409),                  # 武动乾坤之异魔域大乱斗（上） -> 异魔域大乱斗（完整版，子集 0.95）
    (419, 96),                   # 遭媚药的绫清竹 -> 绫清竹（子集 0.88）
    (97, 27),                    # 续-冰灵族银宴 -> 冰灵族银宴（真续篇，见 SEQUEL）
]

# 真正的续篇：正文接续、无重复内容（互含 0.00），必须追加到主本末尾而不是判「无关」
SEQUEL = {
    (97, 27),                    # 续-冰灵族银宴：27 结尾「轰！」正是 97 开头「轰！伴随着一声震天轰响」
}

PUNCT = re.compile(r"\s+")
# 只认「第N章」，不认「第N节」（后者是按字数切出来的）
CHAP_ONLY = re.compile(r"^第[0-9零一二三四五六七八九十百千两]+章")


def flat(s: str) -> str:
    return PUNCT.sub("", s or "")


# 同文判定：段级前 24 字前缀会因「分段切法不同」而失配（同一段被切成两段，前缀就对不上），
# 结果一篇同文会被整篇当成独有内容重复追加（189 vs 169：8-gram 覆盖 0.92，段级却剩 3 万字）。
# 因此每个「前缀未命中」的段落再用 10-gram 复核一次：该段 gram 大部分已在主本里 → 仍是重复。
SAME_TEXT = 0.85
SEG_DUP = 0.40
MIN_UNIQ_PARA = 40      # 独有段落至少这么长才算数（短于此的是语气/短句/分隔线）


def grams(text: str, n: int = 8) -> set[str]:
    t = flat(text)
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def split_paras(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"[\r\n]+", text) if p.strip()]


def unique_text(child_text: str, parent_flat: str, parent_grams: set[str]) -> tuple[str, int, int]:
    """返回 (独有正文, 总段数, 被覆盖段数)。

    两重判重：段首 24 字前缀 + 段内 10-gram 覆盖。另过滤过短片段 ——
    同文的两个版本之间，差异大多是一句浪叫、一句短对话、一条分隔线，
    累加起来几千字但拼不成正文，追加进去只会让章节里夹生。
    """
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
        if len(flat(p)) < MIN_UNIQ_PARA:
            dup += 1
            continue
        keep.append(p)
    return "\n".join(keep), total, dup


def chapters_of(con, wid: int) -> list[tuple[int, str, str]]:
    return [
        (r[0], r[1] or "", r[2] or "")
        for r in con.execute(
            "SELECT idx, title, content FROM chapters WHERE work_id=? ORDER BY idx", (wid,)
        )
    ]


def main():
    apply = "--apply" in sys.argv
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    # 重置上一次的合并状态，保证幂等
    if apply:
        con.execute("UPDATE works SET merged_into=NULL WHERE merged_into IS NOT NULL")
        con.commit()

    for child_id, parent_id in PAIRS:
        cw = con.execute("SELECT id,title FROM works WHERE id=?", (child_id,)).fetchone()
        pw = con.execute("SELECT id,title FROM works WHERE id=?", (parent_id,)).fetchone()
        if not cw or not pw:
            print(f"!! 缺作品 {child_id}->{parent_id}")
            continue

        p_chs = chapters_of(con, parent_id)
        p_flat = flat("\n".join(c[2] for c in p_chs))
        c_chs = chapters_of(con, child_id)
        is_seq = (child_id, parent_id) in SEQUEL
        p_max = max((chap_no(t) or 0 for _, t, _ in p_chs), default=0)

        # 子章节的章号：从子作品标题取，取不到就沿用上一节的章号
        m = re.search(r"第[0-9零一二三四五六七八九十百千两]+章", cw["title"] or "")
        child_no = chap_no(m.group(0)) if m else None

        entries = []   # (章号, 主本优先, 原序, 标题, 内容)
        for i, (idx, title, content) in enumerate(p_chs):
            no = chap_no(title) or (entries[-1][0] if entries else 0)
            entries.append((no, 0, i, title, content))

        added = 0
        p_grams = grams("\n".join(c[2] for c in p_chs))
        cg = grams("\n".join(c[2] for c in c_chs)) if c_chs else set()
        cover = (len(cg & p_grams) / len(cg)) if cg and not is_seq else 0.0
        if is_seq:
            print(f"  ~ #{child_id}《{cw['title'][:22]}》判为续篇 → 全量追加到主本章{p_max + 1}之后")
        else:
            print(f"  · #{child_id}《{cw['title'][:22]}》字符级覆盖 {cover:.3f}"
                  f"（{len(cg)} 个 gram）→ 逐段复核后追加独有段落")
        skipped = (not is_seq) and cover >= SAME_TEXT
        if skipped:
            print(f"  = #{child_id}《{cw['title'][:22]}》同文覆盖 {cover:.3f} ≥ {SAME_TEXT}"
                  f" → 只标合并、不追加章节（差异是删节与分段，不是新内容）")
        for j, (idx, title, content) in enumerate(c_chs):
            if skipped:
                break
            body, total, dup = unique_text(content, p_flat, p_grams)
            if len(body) < 500:
                continue
            no = (chap_no(title) if CHAP_ONLY.match(title or "") else None) or child_no \
                or (p_max + 1 + j if is_seq else 0)
            label = "续" if is_seq else "另版"
            entries.append((no, 1, j, f"{label} · {title}" if title else label, body))
            added += 1
            print(f"  + #{child_id}《{cw['title'][:22]}》第 {j + 1} 节 -> 章{no}"
                  f"  覆盖 {dup}/{total} 段，独有 {len(body)} 字")

        entries.sort(key=lambda e: (e[0], e[1], e[2]))

        print(f"{child_id}《{cw['title'][:22]}》-> {parent_id}《{pw['title'][:22]}》"
              f"  主本 {len(p_chs)} 节 + 新增 {added} 节 = {len(entries)} 节")
        if not apply:
            continue

        con.execute("DELETE FROM chapters WHERE work_id=?", (parent_id,))
        con.executemany(
            "INSERT INTO chapters (work_id,idx,title,is_real_title,content,body_bi,char_count)"
            " VALUES (?,?,?,?,?,?,?)",
            [
                (parent_id, n, title, 1 if title.startswith("第") or "·" in title else 0,
                 body, bigram_cn(body), len(body))
                for n, (_, _, _, title, body) in enumerate(entries, 1)
            ],
        )
        tot = sum(len(e[4]) for e in entries)
        con.execute(
            "UPDATE works SET chapter_count=?, char_count=?, reading_minutes=?,"
            " updated_at=datetime('now','localtime') WHERE id=?",
            (len(entries), tot, max(1, round(tot / 400)), parent_id),
        )
        con.execute("UPDATE works SET merged_into=? WHERE id=?", (parent_id, child_id))
        con.commit()

    if not apply:
        print("\n（--dry：未改库）")
        con.close()
        return

    con.close()
    print("\n重灌 FTS …")
    import subprocess
    subprocess.run([sys.executable, str(HERE / "refresh_fts.py")], check=False)


if __name__ == "__main__":
    main()
