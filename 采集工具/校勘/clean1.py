# -*- coding: utf-8 -*-
"""综合校勘 S0：净化 + 打码还原 + 专名统一
输出到 OUT_ROOT，不动原库。每层记录命中数。

层序（顺序不可换）：
  L1 广告域名串（先删，否则 | 删完会粘连正文）
  L2 竖线打码 | ｜
  L3 方框打码 囗 □
  L4 拼音打码 Rou/Gui/Jing/She/...
  L5 实体与分隔残留 &nbsp ＿
  L6 专名统一
"""
import os, re, sys, csv, collections, json

SRC = r"D:\article_tools\work\校对后文章"
OUT = r"D:\article_tools\out\clean1"
LEX = r"D:\article_tools\lexicon"

# ---------- 词表 ----------
conf = {}
with open(os.path.join(LEX, "confusion.txt"), encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = line.replace("\t", " ").split()
        if len(p) >= 2:
            conf[p[0]] = p[1]
# 长词优先，避免 萧薰儿 被拆
conf_keys = sorted(conf, key=len, reverse=True)

# ---------- 拼音打码映射 ----------
PINYIN = [
    (re.compile(r"Rou(?=棒|体|洞|穴|缝|唇|根|柱|壁|肉|身|具)"), "肉"),
    (re.compile(r"Gui(?=头)"), "龟"),
    (re.compile(r"Jing(?=液|子|水|华|气)"), "精"),
    (re.compile(r"She(?=精|了|出|进来)"), "射"),
    (re.compile(r"Nei(?=肉|壁|裤|衣|里|部)"), "内"),
    (re.compile(r"Ruan(?=肉|玉|语|嫩)"), "软"),
    (re.compile(r"Ru(?=鸽|房|峰|晕|头|尖|肉|白|汁)"), "乳"),
    (re.compile(r"ru(?=头|房|晕|尖|肉)"), "乳"),
    (re.compile(r"ShenYin"), "呻吟"),
    (re.compile(r"Jian(?=叫|硬|挺)"), "坚"),
    (re.compile(r"Di(?=头)"), "低"),
]

# ---------- 广告串（| 删除后形态）----------
ADS = [
    re.compile(r"\|?最\|?新\|?网['’\"]*\|?址[\|\\\s]*(?:找\|?回)?[\-\s]*[^\u4e00-\u9fff\s]{0,60}"),
    re.compile(r"[「『]?请记住[^」』\u4e00-\u9fff]{0,60}?找\|?回[」』]?"),
    re.compile(r"发送?\]?任意?(?:邮件|内容)?[^\u4e00-\u9fff]{0,60}?找\|?回[」』]?"),
    re.compile(r"[\\/]?[Gg]mail\.com[^\u4e00-\u9fff]{0,20}"),
    re.compile(r"(?i)https?://[^\s\u4e00-\u9fff]{4,80}"),
    re.compile(r"(?i)[a-z0-9\^\?\.\-]{4,}\.(?:co\^?m|com|net|cc|me|xyz|top|tv)[^\u4e00-\u9fff]{0,10}"),
    re.compile(r"LтｘＳ[bB][a-z]?[.．]?[^\u4e00-\u9fff]{0,12}"),
    re.compile(r"ㄈòМ|℃[OＯ]Ｍ|c〇[mM]"),
]

def main():
    os.makedirs(OUT, exist_ok=True)
    stat = collections.Counter()
    files = 0
    ledger = []
    detail = collections.Counter()

    for root, dirs, fs in os.walk(SRC):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        for fn in fs:
            if not fn.lower().endswith(".txt"):
                continue
            fp = os.path.join(root, fn)
            with open(fp, "r", encoding="utf-8", errors="replace", newline="") as fh:
                t0 = fh.read()
            t = t0
            c = collections.Counter()

            # L1 广告串
            for rx in ADS:
                t, n = rx.subn("", t)
                if n:
                    c["L1_ad"] += n

            # L2 竖线
            t, n = re.subn(r"[|｜][ \t]?", "", t)
            if n:
                c["L2_pipe"] = n

            # L3 方框
            t, n = re.subn(r"[囗□]", "口", t)
            if n:
                c["L3_box"] = n

            # L4 拼音
            for rx, rep in PINYIN:
                t, n = rx.subn(rep, t)
                if n:
                    c["L4_pinyin"] += n

            # L5 实体与残留
            t, n = re.subn(r"&(?:nbsp|amp|lt|gt|quot);?", "", t)
            if n:
                c["L5_entity"] = n
            t, n = re.subn(r"[_＿]{3,}", "", t)
            if n:
                c["L5_underscore"] = n
            t, n = re.subn(r"(?i)(qq\s*群|群号)\s*[:：]?\s*\d{4,}", "", t)
            if n:
                c["L5_qq"] = n

            # L6 专名
            for bad in conf_keys:
                good = conf[bad]
                if bad in t:
                    cnt = t.count(bad)
                    t = t.replace(bad, good)
                    c["L6_name"] += cnt
                    detail[bad] += cnt

            if t != t0:
                sub = os.path.relpath(root, SRC)
                dest_dir = os.path.join(OUT, sub)
                os.makedirs(dest_dir, exist_ok=True)
                with open(os.path.join(dest_dir, fn), "w", encoding="utf-8", newline="") as fh:
                    fh.write(t)
                files += 1
                for k, v in c.items():
                    stat[k] += v
                ledger.append([os.path.join(sub, fn), dict(c), len(t0), len(t)])

    with open(os.path.join(OUT, "_ledger.json"), "w", encoding="utf-8") as f:
        json.dump({"per_layer": dict(stat), "per_name": dict(detail),
                   "files": ledger}, f, ensure_ascii=False, indent=1)

    print(f"changed_files={files}")
    for k, v in sorted(stat.items()):
        print(f"{k}\t{v}")
    print("\n=== per name ===")
    for k, v in detail.most_common():
        print(f"{k}->{conf[k]}\t{v}")

if __name__ == "__main__":
    main()
