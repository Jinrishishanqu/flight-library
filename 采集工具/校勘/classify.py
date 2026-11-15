# -*- coding: utf-8 -*-
"""排除备份/重复目录后，按变体给出可操作分类"""
import csv, collections, os, sys, json

HITS = r"D:\article_tools\work\hits.csv"
LEX = r"D:\article_tools\lexicon"
EXCLUDE_DIRS = {"归档", "_校勘版", "_legacy"}

conf = {}
with open(os.path.join(LEX, "confusion.txt"), encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = line.replace("\t", " ").split()
        if len(p) >= 2:
            conf[p[0]] = p[1]

rows = list(csv.DictReader(open(HITS, encoding="utf-8-sig")))

def is_excluded(path):
    parts = path.replace("\\", "/").split("/")
    return any(p in EXCLUDE_DIRS for p in parts)

def work_of(path):
    parts = path.replace("\\", "/").split("/")
    if "校对后文章" in parts:
        i = parts.index("校对后文章")
        if len(parts) > i + 1 and not parts[i + 1].endswith(".txt"):
            return parts[i + 1]
    return "(root)"

live = [r for r in rows if not is_excluded(r["file"])]
print(f"hits_total={len(rows)}  hits_live={len(live)}  excluded={len(rows)-len(live)}")

sub = collections.Counter()
for r in live:
    sub[(work_of(r["file"]), r["variant"])] += 1
print("\n=== live: work x variant ===")
for (w, v), c in sub.most_common():
    print(f"{w}\t{v}->{conf[v]}\t{c}")

# 按变体分类文件
files = sorted({r["file"] for r in live})
stats = collections.defaultdict(lambda: {"pure": [], "mixed": [], "none": 0})
for fp in files:
    try:
        with open(fp, "r", encoding="utf-8", errors="replace", newline="") as fh:
            t = fh.read()
    except Exception:
        continue
    for bad, good in conf.items():
        nb, ng = t.count(bad), t.count(good)
        if nb == 0:
            continue
        rec = {"file": fp, "work": work_of(fp), "bad": nb, "good": ng}
        (stats[bad]["mixed"] if ng else stats[bad]["pure"]).append(rec)

print("\n=== classification per variant ===")
summary = []
for bad, good in conf.items():
    s = stats[bad]
    np_ = len(s["pure"]); nm = len(s["mixed"])
    bp = sum(x["bad"] for x in s["pure"]); bm = sum(x["bad"] for x in s["mixed"])
    print(f"{bad}->{good}: pure_files={np_} hits={bp} | mixed_files={nm} hits={bm}")
    summary.append({"variant": bad, "canon": good, "pure_files": np_, "pure_hits": bp,
                    "mixed_files": nm, "mixed_hits": bm})

json.dump(summary, open(r"D:\article_tools\work\classify.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

print("\n=== mixed files detail (top 20 by bad count) ===")
allmixed = [x for v in stats for x in stats[v]["mixed"]]
for x in sorted(allmixed, key=lambda y: -y["bad"])[:20]:
    print(f"  {work_of(x['file'])}/{os.path.basename(x['file'])}\t{x['bad']}={x['bad']}\tcanon={x['good']}")

print("\n=== pure files detail (top 20) ===")
allpure = [x for v in stats for x in stats[v]["pure"]]
for x in sorted(allpure, key=lambda y: -y["bad"])[:20]:
    print(f"  {work_of(x['file'])}/{os.path.basename(x['file'])}\t{x['bad']}x -> {x['good']}")
