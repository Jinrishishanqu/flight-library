# -*- coding: utf-8 -*-
"""打码/污染精确统计 v2
修正: 单个「口」是正常字, 只有 口口+ / 囗 / □ 才算打码
新增: 盗版站广告水印 / HTML 实体残留 / 联系方式
"""
import os, re, sys, collections

PATTERNS = [
    ("mask_box",    re.compile(r"[囗□]{1,6}|口{2,6}")),
    ("mask_star",   re.compile(r"[*＊﹡]{2,}")),
    ("mask_pipe",   re.compile(r"[|｜](?=[\u4e00-\u9fff])|(?<=[\u4e00-\u9fff])[|｜]")),
    ("mask_pinyin", re.compile(r"[A-Za-z]{2,8}(?=[液精穴道棒茎头胸臀裙腿干插射淫欲肉体肉鸽乳阴])")),
    ("mask_underscore", re.compile(r"[_＿]{3,}")),
    ("ad_domain",   re.compile(r"(?i)(w{1,3}[.\u3002][a-z0-9\-]{2,20}[.\u3002]?(?:com|net|org|cc|cn|me|xyz|top|tv)|\.c〇[mＭ]|[a-z]+\.[a-z]{2,4}/)")),
    ("ad_qq",       re.compile(r"(?i)(qq\s*群|企鹅群|群号|加群|vx|微信|公众号|telegram|飞机群)\s*[:：]?\s*\d{4,}")),
    ("ad_email",    re.compile(r"(?i)[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}")),
    ("html_entity", re.compile(r"&(nbsp|amp|lt|gt|quot|#\d{2,5}|#x[0-9a-fA-F]{2,4});?")),
    ("site_tag",    re.compile(r"(?i)(本站|首发|转自|更多精彩|最新章节|请记住|笔下文学|笔趣阁|顶点|txt下载|免费阅读|手机阅读)")),
    ("junk_sym",    re.compile(r"[℃╒╜•·※△▲◆◇○●◎]{2,}")),
]

def ctx(t, i, ln, pad=18):
    return t[max(0, i-pad):i+ln+pad].replace("\r","").replace("\n","\u23ce")

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else r"D:\article_tools\work\校对后文章"
    cnt = collections.Counter(); samples = collections.defaultdict(list)
    filecnt = collections.Counter(); nfile = nchar = 0

    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        for fn in files:
            if not fn.lower().endswith(".txt"): continue
            fp = os.path.join(root, fn)
            try:
                with open(fp, "r", encoding="utf-8", errors="replace", newline="") as fh:
                    t = fh.read()
            except Exception: continue
            nfile += 1; nchar += len(t)
            for name, rx in PATTERNS:
                for m in rx.finditer(t):
                    cnt[name] += 1; filecnt[(name, fn)] += 1
                    if len(samples[name]) < 10:
                        samples[name].append(f"{fn} | {ctx(t, m.start(), max(1,m.end()-m.start()))}")

    print(f"files={nfile} chars={nchar}")
    print("\n=== totals ===")
    for name, _ in PATTERNS:
        print(f"{name}\t{cnt[name]}\tfiles={len([1 for (n,f) in filecnt if n==name])}")
    print("\n=== samples ===")
    for name, _ in PATTERNS:
        if not samples[name]: continue
        print(f"-- {name} (n={cnt[name]}) --")
        for s in samples[name][:5]: print(f"   {s}")

if __name__ == "__main__":
    main()
