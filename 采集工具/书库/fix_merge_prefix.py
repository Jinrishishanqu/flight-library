# -*- coding: utf-8 -*-
"""把合并进来的章节标题从「【原：子书名】原节标题」改成「差异标签 · 原节标题」。

用户要求（m07814）：书名作前缀，像「前传 · 第1章」那样紧凑。

标签不是子书名全名（太长，且子书名往往就是「主书名+章号+章节名」，全名作前缀会把目录撑满），
而是子书名相对主书名**多出来的那一段**：

    斗破淫传1纳兰劫        vs 斗破淫传        -> 纳兰劫
    新-唐舞麟与娜儿        vs 唐舞麟与娜儿    -> 新
    斗破苍穹改编版第三章…  vs 斗破苍穹-改编版 -> 另版（差异部分与节标题重复，没有独立含义）

用法：python fix_merge_prefix.py [--apply]
"""
import io
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OLD = re.compile(r"^【原：(?P<child>.+?)】(?P<orig>.*)$")
CHAP_HEAD = re.compile(r"^第[0-9零一二三四五六七八九十百千两]+[章节回][：:、.．\s]*")
PUNCT = re.compile(r"[\s\-_—~～·、，,。.：:；;（）()【】\[\]「」\"'《》]+")


def norm(s: str) -> str:
    return PUNCT.sub("", s or "")


def bigram_overlap(a: str, b: str) -> float:
    """两串二元组的重叠率（交集 / 较小集合）。"""
    def bg(s):
        s = norm(s)
        return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else set()
    A, B = bg(a), bg(b)
    if not A or not B:
        return 0.0
    return len(A & B) / min(len(A), len(B))


def diff_label(child: str, parent: str, orig: str) -> str:
    c, p = norm(child), norm(parent)
    rest = c[len(p):] if (p and c.startswith(p)) else c
    # 子书名里若没有父书名，就整体作为差异部分
    rest = CHAP_HEAD.sub("", rest)
    if not rest:
        return "另版"
    if len(rest) <= 6:
        return rest
    # 差异部分与本节标题高度重叠 → 没有独立含义，用「另版」
    if orig and bigram_overlap(rest, orig) >= 0.2:
        return "另版"
    return rest[:8]


def main():
    apply = "--apply" in sys.argv
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.id, c.work_id, c.idx, c.title, w.title AS parent "
        "FROM chapters c JOIN works w ON w.id = c.work_id "
        "WHERE c.title LIKE '【原：%'"
    ).fetchall()
    print(f"待改标题 {len(rows)} 条\n")
    for cid, wid, idx, title, parent in rows:
        m = OLD.match(title)
        if not m:
            continue
        child, orig = m.group("child"), m.group("orig")
        label = diff_label(child, parent, orig)
        new = f"{label} · {orig}" if orig else label
        print(f"  {wid:>4}/{idx:<3} {title[:46]}")
        print(f"          -> {new[:56]}")
        if apply:
            con.execute("UPDATE chapters SET title=? WHERE id=?", (new, cid))
    if apply:
        con.commit()
        con.close()
        print("\n标题已更新，重灌 FTS …")
        subprocess.run([sys.executable, str(HERE / "refresh_fts.py")], check=False)
        return
    con.close()
    print("\n（--dry：未改库）")


if __name__ == "__main__":
    main()
