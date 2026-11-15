# -*- coding: utf-8 -*-
"""保守的同作异名候选扫描。

判据分三级，只有 A 级才建议合并：
  A 级 —— 书名相近 + 两边都有「原创角色」且名字有交集 + 正文段级重合 ≥0.35
          （原创角色同名是最强信号：原作角色重名是常态，作者自创的人物重名才说明是同一篇）
  B 级 —— 书名相近 + 正文重合 ≥0.20，但角色证据不足 → 需要人读原文确认
  C 级 —— 只有书名相近

输出 data/similar_candidates.json 与屏幕摘要。
"""
import io
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"
OUT = HERE / "data" / "similar_candidates.json"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PUNCT = re.compile(r"[\s\-_—~～·、，,。.：:；;（）()【】\[\]「」\"'《》]+")
PARA_MIN = 12


def norm(s: str) -> str:
    return PUNCT.sub("", s or "")


def bigrams(s: str) -> set[str]:
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else set(s)


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0
    return len(a & b) / len(a | b)


def para_keys(text: str, limit: int = 400) -> set[str]:
    """取每段前 24 字做指纹（去空白），用于段级重合率。"""
    keys = set()
    n = 0
    for p in re.split(r"[\r\n]+", text):
        k = re.sub(r"\s+", "", p)[:24]
        if len(k) >= PARA_MIN:
            keys.add(k)
            n += 1
            if n >= limit:
                break
    return keys


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    works = con.execute(
        "SELECT id, title, char_count FROM works WHERE merged_into IS NULL ORDER BY id"
    ).fetchall()
    print(f"可见作品 {len(works)} 部")

    # 原创角色（作者自创，不在 guard 里的）
    orig_chars = defaultdict(set)
    for r in con.execute(
        "SELECT work_id, name FROM characters WHERE origin='原创'"
    ):
        orig_chars[r[0]].add(r[1])

    # 正文段落指纹（取前 3000 字，够判断重合）
    keys = {}
    for w in works:
        body = con.execute(
            "SELECT content FROM chapters WHERE work_id=? ORDER BY idx LIMIT 2", (w["id"],)
        ).fetchall()
        txt = "\n".join(r[0] for r in body)[:30000]
        keys[w["id"]] = para_keys(txt)

    tnames = {w["id"]: norm(w["title"]) for w in works}
    tbg = {wid: bigrams(t) for wid, t in tnames.items()}

    out = []
    n = len(works)
    for i in range(n):
        a = works[i]
        for j in range(i + 1, n):
            b = works[j]
            # 书名相似：bigram Jaccard 或互相包含
            ta, tb = tnames[a["id"]], tnames[b["id"]]
            title_sim = jaccard(tbg[a["id"]], tbg[b["id"]])
            if ta and tb and (ta in tb or tb in ta):
                title_sim = max(title_sim, 0.55)
            if title_sim < 0.45:
                continue

            ka, kb = keys[a["id"]], keys[b["id"]]
            cont = (len(ka & kb) / min(len(ka), len(kb))) if (ka and kb) else 0.0
            shared = orig_chars[a["id"]] & orig_chars[b["id"]]

            if cont >= 0.35 and shared:
                level = "A"
            elif cont >= 0.20:
                level = "B"
            else:
                level = "C"
            out.append({
                "a": a["id"], "a_title": a["title"], "a_chars": a["char_count"],
                "b": b["id"], "b_title": b["title"], "b_chars": b["char_count"],
                "title_sim": round(title_sim, 3),
                "content_overlap": round(cont, 3),
                "shared_original_chars": sorted(shared),
                "level": level,
            })

    out.sort(key=lambda x: (-{"A": 2, "B": 1, "C": 0}[x["level"]], -x["content_overlap"]))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    cnt = defaultdict(int)
    for x in out:
        cnt[x["level"]] += 1
    print(f"候选 {len(out)} 对：A={cnt['A']} B={cnt['B']} C={cnt['C']}  -> {OUT}\n")

    for lv in ("A", "B"):
        rows = [x for x in out if x["level"] == lv]
        if not rows:
            continue
        print(f"===== {lv} 级（{len(rows)} 对，前 25） =====")
        for x in rows[:25]:
            print(f"  {x['a']:>4} {x['a_title'][:26]:28s} x {x['b']:>4} {x['b_title'][:26]:28s}"
                  f" 重合{x['content_overlap']:.2f} 书名{x['title_sim']:.2f}"
                  f" 共有人物: {','.join(x['shared_original_chars'][:4]) or '—'}")
    con.close()


if __name__ == "__main__":
    main()
