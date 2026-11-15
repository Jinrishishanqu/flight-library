# -*- coding: utf-8 -*-
import os, re, collections
ROOT = r"D:\article_tools\out\final4"
PATS = {
 "stars": re.compile(r"[＊*]{3,}"),
 "dash":  re.compile(r"[─━]{3,}"),
 "tilde": re.compile(r"[~～]{3,}"),
 "eq":    re.compile(r"[=═]{3,}"),
 "ltco":  re.compile(r"(?i)\.?lt\?{2}s|\.co\?{2}|zw\.m|ww\.lt|lтｘ|a\.c〇"),
}
seen = collections.defaultdict(list)
for root, dirs, fs in os.walk(ROOT):
    for fn in fs:
        if not fn.lower().endswith(".txt"): continue
        fp = os.path.join(root, fn)
        t = open(fp, encoding="utf-8", errors="replace", newline="").read()
        for k, p in PATS.items():
            if len(seen[k]) >= 5: continue
            m = p.search(t)
            if m:
                a, b = max(0, m.start()-60), min(len(t), m.end()+60)
                seen[k].append((fn, t[a:b]))
for k, v in seen.items():
    print(f"\n##### {k}")
    for fn, s in v:
        print(f"-- {fn}\n{s!r}")