# -*- coding: utf-8 -*-
"""针对 Rou/Gui/Jing/She 与 口口 的上下文枚举"""
import os, re, collections

ROOT = r"D:\article_tools\work\校对后文章"
targets = {
    "Rou":  re.compile(r".{2}Rou.{4}"),
    "Gui":  re.compile(r".{2}Gui.{4}"),
    "Jing": re.compile(r".{2}Jing.{4}"),
    "She":  re.compile(r".{2}She.{4}"),
    "obox": re.compile(r".{5}口{2,4}.{5}"),
    "adfind": re.compile(r".{0,20}(找|网)[\s]*[|｜].{0,30}"),
}
out = collections.defaultdict(collections.Counter)
for root, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if not d.startswith("_")]
    for fn in files:
        if not fn.lower().endswith(".txt"): continue
        try:
            with open(os.path.join(root, fn), "r", encoding="utf-8", errors="replace", newline="") as fh:
                t = fh.read()
        except Exception: continue
        for k, rx in targets.items():
            for m in rx.finditer(t):
                out[k][m.group().replace("\r","").replace("\n","\u23ce")] += 1

for k in targets:
    c = out[k]
    print(f"\n=== {k} (distinct={len(c)} total={sum(c.values())}) ===")
    for s, n in c.most_common(25):
        print(f"{n}\t{s!r}")
