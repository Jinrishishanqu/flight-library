# -*- coding: utf-8 -*-
"""盘点：符号风格分布 + 性词变形形态"""
import os, re, json, collections

ROOT = r"D:\article_tools\out\final7"

# ---------- 符号风格 ----------
STYLE = {
    "quote_cn":   re.compile(r"“[^”\r\n]{0,80}”"),
    "quote_corner": re.compile(r"「[^」\r\n]{0,80}」"),
    "quote_double_corner": re.compile(r"『[^』\r\n]{0,80}』"),
    "quote_ascii": re.compile(r"\"[^\"\r\n]{0,80}\""),
    "quote_single_cn": re.compile(r"‘[^’\r\n]{0,80}’"),
    "dash_em2":   re.compile(r"——"),
    "dash_em1":   re.compile(r"(?<!—)—(?!—)"),
    "dash_ascii": re.compile(r"--+"),
    "wave_full":  re.compile(r"～"),
    "wave_ascii": re.compile(r"~"),
    "ellip_cn":   re.compile(r"……"),
    "ellip_cn1":  re.compile(r"(?<!…)…(?!…)"),
    "ellip_ascii": re.compile(r"\.{2,}"),
    "paren_full": re.compile(r"（[^）\r\n]{0,40}）"),
    "paren_ascii": re.compile(r"\([^)\r\n]{0,40}\)"),
    "bracket_full": re.compile(r"【[^】\r\n]{0,40}】"),
    "bracket_sq": re.compile(r"\[[^\]\r\n]{0,40}\]"),
    "sep_asterisk": re.compile(r"(?m)^\*\*\*\r?$"),
    "sep_dash":   re.compile(r"(?m)^-{3,}\r?$"),
}

# ---------- 性词变形 ----------
BASE = ["肉棒", "龟头", "精液", "射精", "阴道", "阴茎", "阴唇", "子宫", "奶子",
        "乳头", "屁股", "鸡巴", "骚逼", "小穴", "淫水", "高潮", "淫穴", "肉穴",
        "肉洞", "阳具", "阴蒂", "睾丸", "pussy", "cock", "penis"]

def gap_pattern(w):
    """词中间允许插入 1-2 个非汉字字符"""
    parts = list(w)
    return re.compile(r"[^\u4e00-\u9fff]{0,2}".join(map(re.escape, parts)))

GAP = {w: gap_pattern(w) for w in BASE}
EXACT = re.compile("|".join(map(re.escape, sorted(BASE, key=len, reverse=True))))

def main():
    st = collections.Counter()
    stfiles = collections.Counter()
    gap_hits = collections.Counter()
    gap_ctx = collections.defaultdict(list)
    exact_hits = collections.Counter()

    for root, dirs, fs in os.walk(ROOT):
        for fn in fs:
            if not fn.lower().endswith(".txt"):
                continue
            fp = os.path.join(root, fn)
            t = open(fp, encoding="utf-8", errors="replace", newline="").read()
            for k, p in STYLE.items():
                n = len(p.findall(t))
                if n:
                    st[k] += n
                    stfiles[k] += 1
            for w, p in GAP.items():
                for m in p.finditer(t):
                    s = m.group()
                    if s == w:
                        exact_hits[w] += 1
                        continue
                    gap_hits[s] += 1
                    if len(gap_ctx[s]) < 3:
                        a, b = max(0, m.start() - 25), min(len(t), m.end() + 25)
                        gap_ctx[s].append(t[a:b].replace("\r\n", " "))

    print("=== 符号风格分布 ===")
    for k in STYLE:
        print(f"{k:22} {st[k]:>8}   files={stfiles[k]}")
    print("\n=== 性词精确命中 top ===")
    for w, n in exact_hits.most_common():
        print(f"{w}\t{n}")
    print(f"\n=== 变形形态 distinct={len(gap_hits)} total={sum(gap_hits.values())} ===")
    for s, n in gap_hits.most_common(40):
        print(f"{n}\t{s!r}\t{gap_ctx[s][0][:60]!r}")

if __name__ == "__main__":
    main()
