# -*- coding: utf-8 -*-
"""打码/自审痕迹统计：作者为规避审查留下的残留

用法: python scan_masks.py <target_dir> [--out OUT_CSV]
"""
import os, re, sys, csv, collections

PATTERNS = [
    ("star",      re.compile(r"\*{2,}")),
    ("box",       re.compile(r"[口囗□]{1,6}")),
    ("pipe",      re.compile(r"[|｜]")),
    ("circle",    re.compile(r"[〇○●]+")),
    ("fullstar",  re.compile(r"[＊﹡]+")),
    ("pinyin",    re.compile(r"[A-Za-z]{2,8}(?=[液精穴道棒茎头胸臀裙腿干插射淫欲肉体])")),
    ("letters",   re.compile(r"(?<![A-Za-z])[A-Za-z]{3,8}(?![A-Za-z])")),
    ("underscore",re.compile(r"[_＿]{2,}")),
    ("punct_mask",re.compile(r"[#＃@※△▲]+")),
]

def ctx(text, i, ln, pad=18):
    return text[max(0, i - pad):i + ln + pad].replace("\r", "").replace("\n", "\u23ce")

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else r"D:\article_tools\work\校对后文章"
    cnt = collections.Counter()
    samples = collections.defaultdict(list)
    filecnt = collections.Counter()
    nfile = nchar = 0

    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        for fn in files:
            if not fn.lower().endswith(".txt"):
                continue
            fp = os.path.join(root, fn)
            try:
                with open(fp, "r", encoding="utf-8", errors="replace", newline="") as fh:
                    t = fh.read()
            except Exception:
                continue
            nfile += 1
            nchar += len(t)
            for name, rx in PATTERNS:
                for m in rx.finditer(t):
                    cnt[name] += 1
                    filecnt[(name, fn)] += 1
                    if len(samples[name]) < 12:
                        samples[name].append(f"{fn} | {ctx(t, m.start(), m.end()-m.start())}")

    print(f"files={nfile} chars={nchar}")
    print("\n=== pattern totals ===")
    for name, _ in PATTERNS:
        print(f"{name}\t{cnt[name]}")
    print("\n=== samples ===")
    for name, _ in PATTERNS:
        if not samples[name]:
            continue
        print(f"-- {name} (n={cnt[name]}) --")
        for s in samples[name][:6]:
            print(f"   {s}")
    print("\n=== top files per pattern ===")
    byp = collections.defaultdict(list)
    for (name, fn), c in filecnt.items():
        byp[name].append((c, fn))
    for name, lst in byp.items():
        lst.sort(reverse=True)
        top = ", ".join(f"{fn}({c})" for c, fn in lst[:3])
        print(f"{name}: files={len(lst)} top={top}")

if __name__ == "__main__":
    main()
