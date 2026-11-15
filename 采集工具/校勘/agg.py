# -*- coding: utf-8 -*-
"""对 hits.csv 做聚合与抽样，并检测单篇内正写/异写混用，供人工裁量"""
import csv, collections, random, sys, os

path = sys.argv[1] if len(sys.argv) > 1 else r"D:\article_tools\work\hits.csv"
lex = sys.argv[2] if len(sys.argv) > 2 else r"D:\article_tools\lexicon"

rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
print("total_hits", len(rows))

# ---------- 1. 作品 x 变体 ----------
agg = collections.Counter()
for r in rows:
    parts = r["file"].replace("\\", "/").split("/")
    work = "(root)"
    if "校对后文章" in parts:
        i = parts.index("校对后文章")
        if len(parts) > i + 1 and not parts[i + 1].endswith(".txt"):
            work = parts[i + 1]
    agg[(work, r["variant"])] += 1

print("\n=== work x variant ===")
for (w, v), c in agg.most_common():
    print(f"{w}\t{v}\t{c}")

# ---------- 2. 抽样 ----------
print("\n=== samples per variant ===")
by = collections.defaultdict(list)
for r in rows:
    by[r["variant"]].append(r)
rnd = random.Random(7)
for v, rs in by.items():
    print(f"-- {v} -> {rs[0]['canon']} (n={len(rs)}) --")
    for r in rnd.sample(rs, min(4, len(rs))):
        print(f"  [{r['offset']}] {r['context']}")

# ---------- 3. 单篇混用检测 ----------
conf = {}
with open(os.path.join(lex, "confusion.txt"), encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = line.replace("\t", " ").split()
        if len(p) >= 2:
            conf[p[0]] = p[1]

files = sorted({r["file"] for r in rows})
print(f"\n=== per-file mixed (of {len(files)} files with hits) ===")
mixed = []
for fp in files:
    try:
        with open(fp, "r", encoding="utf-8", errors="replace", newline="") as fh:
            t = fh.read()
    except Exception:
        continue
    for bad, good in conf.items():
        nb, ng = t.count(bad), t.count(good)
        if nb > 0 and ng > 0:
            mixed.append((fp, bad, nb, good, ng))

mixed.sort(key=lambda x: -(x[2]))
print(f"mixed_groups={len(mixed)}")
for fp, bad, nb, good, ng in mixed[:25]:
    print(f"  {os.path.basename(fp)}\t{bad}={nb}\t{good}={ng}")

# ---------- 4. 纯异写（无正写）文件：最安全的批量改 ----------
pure = []
for fp in files:
    try:
        with open(fp, "r", encoding="utf-8", errors="replace", newline="") as fh:
            t = fh.read()
    except Exception:
        continue
    for bad, good in conf.items():
        nb, ng = t.count(bad), t.count(good)
        if nb > 0 and ng == 0:
            pure.append((fp, bad, nb, good))

print(f"\n=== pure variant files (no canonical form present) : {len(pure)} ===")
for fp, bad, nb, good in sorted(pure, key=lambda x: -x[2])[:15]:
    print(f"  {os.path.basename(fp)}\t{bad}={nb}\t->{good}")
