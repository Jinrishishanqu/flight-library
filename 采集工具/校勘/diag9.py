# -*- coding: utf-8 -*-
import os, re, sys
SRC = r"D:\article_tools\out\final7"
PAT = re.compile(r"发布邮箱|╒|★址|Nordfx|chapter\s*:|地.*址|邮.*箱|@\s*』|』\s*@", re.I)
hits = 0
seen = set()
for root, dirs, fs in os.walk(SRC):
    for fn in fs:
        if not fn.lower().endswith(".txt"):
            continue
        fp = os.path.join(root, fn)
        rel = os.path.relpath(fp, SRC)
        with open(fp, "r", encoding="utf-8", errors="replace", newline="") as f:
            for i, line in enumerate(f, 1):
                if PAT.search(line):
                    hits += 1
                    key = (rel, line.strip()[:40])
                    if key in seen:
                        continue
                    seen.add(key)
                    if hits <= 120:
                        print(f"{rel}:{i}: {line.strip()[:160]}")
print("TOTAL_MATCH_LINES", hits, "UNIQUE", len(seen))
