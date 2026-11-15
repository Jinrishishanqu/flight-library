# -*- coding: utf-8 -*-
"""探查 final 里几类可疑残留的真实上下文，用于定规则"""
import os, re, sys, glob

ROOT = sys.argv[1] if len(sys.argv) > 1 else r"D:\article_tools\out\final"
PATS = {
    "ad_en": re.compile(r"(?i)saved|using|versin|dwnlad|depiler|trial|ureed|powered"),
    "page": re.compile(r"【\d+】"),
    "dots": re.compile(r"\.{3,}"),
    "sep": re.compile(r"[─━═~～★☆＊*※·]{5,}"),
}

def main():
    buf = {k: [] for k in PATS}
    for root, dirs, fs in os.walk(ROOT):
        for fn in fs:
            if not fn.lower().endswith(".txt"):
                continue
            fp = os.path.join(root, fn)
            with open(fp, "r", encoding="utf-8", errors="replace", newline="") as f:
                t = f.read()
            for k, p in PATS.items():
                if len(buf[k]) >= 6:
                    continue
                m = p.search(t)
                if m:
                    a, b = max(0, m.start() - 90), min(len(t), m.end() + 90)
                    buf[k].append((fn, t[a:b].replace("\r\n", " ⏎ ")))
    for k, items in buf.items():
        print(f"\n########## {k} ##########")
        for fn, s in items:
            print(f"--- {fn}\n{s}")

if __name__ == "__main__":
    main()
