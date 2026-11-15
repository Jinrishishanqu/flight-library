# -*- coding: utf-8 -*-
"""枚举 clean1 之后残留的可疑串：连续非汉字片段 + 孤标点行"""
import os, re, collections

OUT = r"D:\article_tools\out\clean1"
rx_latin = re.compile(r"[^\u4e00-\u9fff\s，。！？、；：「」『』（）《》…—～·\"'“”‘’]{5,}")
rx_lone = re.compile(r"^\s*[;；,，\.。·、]\s*$", re.M)

latin = collections.Counter()
filecnt = collections.Counter()
lone = collections.Counter()

for root, dirs, files in os.walk(OUT):
    dirs[:] = [d for d in dirs if not d.startswith("_")]
    for fn in files:
        if not fn.lower().endswith(".txt"):
            continue
        with open(os.path.join(root, fn), "r", encoding="utf-8", errors="replace", newline="") as f:
            t = f.read()
        for m in rx_latin.finditer(t):
            s = m.group()
            latin[s] += 1
            filecnt[fn] += 1
        for m in rx_lone.finditer(t):
            lone[fn] += 1

print(f"=== suspicious latin/non-CJK runs (distinct={len(latin)} total={sum(latin.values())}) ===")
for s, n in latin.most_common(50):
    print(f"{n}\t{s!r}")
print("\n=== files with most latin runs ===")
for fn, n in filecnt.most_common(10):
    print(f"{n}\t{fn}")
print("\n=== lone punctuation lines ===")
for fn, n in lone.most_common(10):
    print(f"{n}\t{fn}")
