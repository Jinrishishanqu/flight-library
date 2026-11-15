# -*- coding: utf-8 -*-
"""收尾：clean2 -> final，含 clean3/4 全部规则，全量镜像输出（未改动文件也复制）"""
import os, re, json, collections, unicodedata, shutil

BASE = r"D:\article_tools\out\clean2"       # 已含 clean1 成果
SRC_ORIG = r"D:\article_tools\work\校对后文章"
OUT = r"D:\article_tools\out\final"

SEG = re.compile(r"[^\u4e00-\u9fff，。！？、；：「」『』（）《》…—～·\s]{2,}")
FEATURE = re.compile(r"(?i)ltx|txs|xsb|xsf|gmail|www|4v4|com\b|1bz|〇")
FEATURE2 = re.compile(r"(?i)l[tт].{0,4}[sc].{0,2}[co]|zw[._]?m[._]?e|ww\.?l")
KEEP = {"level", "duang", "duanduang", "sm", "jk", "av", "txt", "bj", "3p", "np",
        "pc", "xp", "hk", "tv", "ip", "ok", "mm", "cm", "kg", "player", "error",
        "party", "fucker", "debuff", "cm", "rank"}

PIXIV = re.compile(r"\[(?:pixivimage|jump|pixiv):?\d+\]")
SEP = re.compile(r"(?m)^[ \t]*[─━═=~～\-—_【】\[\]]{5,}[ \t]*$")
LEFTOVER_SEP = re.compile(r"-{5,}【|-{5,}$|】-{5,}")

def main():
    os.makedirs(OUT, exist_ok=True)
    stat = collections.Counter()
    n_out = n_copy = 0

    for root, dirs, fs in os.walk(SRC_ORIG):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        for fn in fs:
            if not fn.lower().endswith(".txt"):
                continue
            rel = os.path.relpath(os.path.join(root, fn), SRC_ORIG)
            src_clean = os.path.join(BASE, rel)
            src = src_clean if os.path.exists(src_clean) else os.path.join(root, fn)
            with open(src, "r", encoding="utf-8", errors="replace", newline="") as f:
                t0 = f.read()
            t = t0
            c = collections.Counter()

            # 域名（归一化识别）
            pieces, last = [], 0
            for m in SEG.finditer(t):
                seg = m.group()
                alnum = "".join(ch for ch in unicodedata.normalize("NFKC", seg) if ch.isalnum()).lower()
                if len(alnum) < 2 or alnum in KEEP:
                    continue
                if FEATURE.search(alnum) or FEATURE2.search(alnum):
                    pieces.append(t[last:m.start()])
                    last = m.end()
                    c["domain"] += 1
            pieces.append(t[last:])
            t = "".join(pieces)

            t, n = PIXIV.subn("", t); c["pixiv"] = n
            t, n = SEP.subn("***", t); c["sep"] = n
            t, n = LEFTOVER_SEP.subn("", t); c["leftover_sep"] = n
            t, n = re.subn(r"(?:\r?\n)[ \t\u3000]*(?:\r?\n){2,}", "\r\n\r\n", t); c["blank"] = n
            t, n = re.subn(r"(?m)^[ \t\u3000]+(?=\r?$)", "", t); c["spaceline"] = n

            dest = os.path.join(OUT, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8", newline="") as fh:
                fh.write(t)
            n_out += 1
            if t != t0:
                for k, v in c.items():
                    stat[k] += v
            else:
                n_copy += 1

    json.dump(dict(stat), open(os.path.join(OUT, "_ledger_final.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"written={n_out} unchanged_vs_clean2={n_copy}")
    for k, v in sorted(stat.items()):
        if v:
            print(f"{k}\t{v}")

if __name__ == "__main__":
    main()
