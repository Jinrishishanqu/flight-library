# -*- coding: utf-8 -*-
"""S2 精修：用归一化字串识别一切域名变体 + 分隔线归一

思路：抓「连续非汉字非标点片段」→ NFKC 归一 → 只保留 alnum → 命中域名特征则整段删除
这样 lтｘＳb / LīxSBǎ@ＧＭＡＩＬ．ｃＯＭ / w}ww. / ωωω．lTxsfｂ．Ｃ⊙㎡ 全部一网打尽
"""
import os, re, json, collections, unicodedata

SRC = r"D:\article_tools\out\clean2"
OUT = r"D:\article_tools\out\clean3"

CJK_CLASS = r"[^\u4e00-\u9fff，。！？、；：「」『』（）《》…—～·\s]"
SEG = re.compile(CJK_CLASS + r"{2,}")
FEATURE = re.compile(r"(?i)ltx|txs|xsb|xsf|gmail|www|4v4|com|cn\b|net\b|us\b|bz|〇|1bz")

# 白名单：正文里合法的拉丁串
KEEP = {"level", "duang", "sm", "jk", "av", "txt", "h", "bj", "3p", "np", "yy", "np",
        "pc", "xp", "usa", "hk", "tv", "ip", "ok", "k", "mm", "cm", "kg"}

SEP = re.compile(r"(?m)^[ \t]*[─━═=~～\-—_]{5,}[ \t]*$")
NAMEDATES = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")

def main():
    os.makedirs(OUT, exist_ok=True)
    stat = collections.Counter()
    removed = collections.Counter()
    files = 0

    for root, dirs, fs in os.walk(SRC):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        for fn in fs:
            if not fn.lower().endswith(".txt"):
                continue
            fp = os.path.join(root, fn)
            with open(fp, "r", encoding="utf-8", errors="replace", newline="") as f:
                t0 = f.read()
            t = t0
            pieces = []
            last = 0
            for m in SEG.finditer(t):
                seg = m.group()
                norm = unicodedata.normalize("NFKC", seg)
                alnum = "".join(ch for ch in norm if ch.isalnum()).lower()
                if len(alnum) < 2:
                    continue
                if alnum in KEEP:
                    continue
                if FEATURE.search(alnum):
                    pieces.append(t[last:m.start()])
                    last = m.end()
                    removed[seg] += 1
                    stat["S2_domain"] += 1
            pieces.append(t[last:])
            t = "".join(pieces)

            # 分隔线归一
            t, n = SEP.subn("***", t)
            if n:
                stat["S2_sep"] = n

            # 删除后产生的空行/行首空格修整
            t, n = re.subn(r"(?m)^[ \t\u3000]+(?=\S)", "", t)
            if n:
                stat["S2_leadspace"] = n
            t, n = re.subn(r"(?:\r?\n)[ \t\u3000]*(?:\r?\n){2,}", "\r\n\r\n", t)
            if n:
                stat["S2_blank"] = n

            if t != t0:
                sub = os.path.relpath(root, SRC)
                d = os.path.join(OUT, sub)
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, fn), "w", encoding="utf-8", newline="") as fh:
                    fh.write(t)
                files += 1

    os.makedirs(OUT, exist_ok=True)
    json.dump({"stat": dict(stat), "removed_top": removed.most_common(120)},
              open(os.path.join(OUT, "_ledger3.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"changed_files={files}")
    for k, v in sorted(stat.items()):
        print(f"{k}\t{v}")
    print("\n=== removed samples ===")
    for s, n in removed.most_common(25):
        print(f"{n}\t{s!r}")

if __name__ == "__main__":
    main()
