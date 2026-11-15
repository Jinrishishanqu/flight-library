# -*- coding: utf-8 -*-
"""内容级查重：找出「A 的正文基本被 B 包含」的作品对。

用途：分卷 → 合集、连载续篇、重复下载。
不动库，只出报告。

用法：python dupe_content.py [--threshold 0.85]
"""
import io
import json
import re
import sqlite3
import sys
from pathlib import Path

from datasketch import MinHash, MinHashLSH

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"
ROOT = HERE.parents[1]
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

K = 5          # shingle 长度
SAMPLE = 4000  # 每部采样多少个 shingle 建索引


def shingles(text: str, k: int = K) -> set[str]:
    flat = re.sub(r"\s+", "", text)
    return {flat[i:i + k] for i in range(len(flat) - k + 1)}


def sample(text: str, n: int = SAMPLE) -> set[str]:
    """均匀采样，避免取整段导致头部相同的两本书误判。"""
    flat = re.sub(r"\s+", "", text)
    total = len(flat) - K + 1
    if total <= n:
        return {flat[i:i + K] for i in range(total)}
    step = max(1, total // n)
    out = set()
    for i in range(0, total, step):
        out.add(flat[i:i + K])
        if len(out) >= n:
            break
    return out


def main():
    th = 0.85
    if "--threshold" in sys.argv:
        th = float(sys.argv[sys.argv.index("--threshold") + 1])

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    works = con.execute(
        "SELECT id,title,char_count,path_canon FROM works ORDER BY id"
    ).fetchall()

    texts, meta = {}, {}
    for w in works:
        p = Path(w["path_canon"])
        if not p.is_absolute():
            p = ROOT / "校勘版" / p
        if not p.exists():
            continue
        t = p.open("r", encoding="utf-8", errors="replace", newline="").read()
        texts[w["id"]] = re.sub(r"\s+", "", t)
        meta[w["id"]] = (w["title"], len(texts[w["id"]]))

    print(f"载入 {len(texts)} 部")

    lsh = MinHashLSH(threshold=0.6, num_perm=128)
    mhs = {}
    for wid, flat in texts.items():
        m = MinHash(num_perm=128)
        for s in sample(flat):
            m.update(s.encode())
        mhs[wid] = m
        lsh.insert(str(wid), m)

    pairs = set()
    for wid in texts:
        for other in lsh.query(mhs[wid]):
            o = int(other)
            if o != wid:
                pairs.add((min(wid, o), max(wid, o)))
    print(f"LSH 候选对 {len(pairs)}")

    # 精确 containment
    full = {}
    hits = []
    for a, b in sorted(pairs):
        for x, y in ((a, b), (b, a)):
            if x not in full:
                full[x] = shingles(texts[x])
            if y not in full:
                full[y] = shingles(texts[y])
            inter = len(full[x] & full[y])
            if not inter:
                continue
            contain = inter / len(full[x])
            jac = inter / len(full[x] | full[y])
            if contain >= th:
                hits.append({
                    "inner": x, "outer": y,
                    "contain": round(contain, 4), "jaccard": round(jac, 4),
                    "inner_chars": meta[x][1], "outer_chars": meta[y][1],
                    "inner_title": meta[x][0], "outer_title": meta[y][0],
                })
    # 去重：同一个 inner 只留 containment 最高、outer 最小的
    best = {}
    for h in hits:
        k = h["inner"]
        if k not in best or h["contain"] > best[k]["contain"]:
            best[k] = h
    rows = sorted(best.values(), key=lambda h: -h["contain"])

    also = sorted({(h["inner"], h["outer"]) for h in rows})
    covered = {h["inner"] for h in rows}
    print(f"\n=== 被别的作品包含（contain ≥ {th}）：{len(rows)} 组 ===")
    for h in rows:
        tag = "完全重复" if h["jaccard"] >= 0.95 else ("分卷/片段" if h["contain"] >= 0.95 else "高度重合")
        extra = ""
        if h["inner_chars"] > h["outer_chars"]:
            extra = "  ⚠ inner 比 outer 还长"
        print(f"  [{tag} c={h['contain']:.2f} j={h['jaccard']:.2f}] "
              f"{h['inner']}:{h['inner_title'][:24]}({h['inner_chars']//1000}k)"
              f"  ⊂  {h['outer']}:{h['outer_title'][:24]}({h['outer_chars']//1000}k){extra}")

    out = HERE / "data" / "dupes_content.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n涉及 {len(covered)} 部，报告 -> {out}")
    con.close()


if __name__ == "__main__":
    main()
