# -*- coding: utf-8 -*-
"""后处理：对 final5 收尾，输出 final6（最终交付版）"""
import os, re, json, collections, unicodedata

SRC = r"D:\article_tools\out\final5"
OUT = r"D:\article_tools\out\final6"

SEPSET = set("─━═-—_~～*＊#★☆※·=－ ")
UNDERSCORE_ART = re.compile(r"(?m)^[ \t]*[_＿]{3,}[ \t]*\r?$")
QMARK = re.compile(r"\?{3,}")
DASH_BRACKET = re.compile(r"[-─━＊*]{3,}【|】[-─━＊*]{3,}")
AD_LINE = re.compile(r"(?i)chapter\s*:|\bwk\^|\bdup\b|↑|↓")
ZWSEG = re.compile(r"[^\u4e00-\u9fff\s]{2,}")

def is_sep_line(ln):
    s = ln.strip()
    if len(s) < 3:
        return False
    body = [ch for ch in s if ch not in " \t\u3000"]
    if len(body) < 3:
        return False
    if all(ch in SEPSET for ch in body):
        return True
    # 同一分隔符重复
    if len(set(body)) == 1 and body[0] in SEPSET:
        return True
    return False

def norm_alnum(s):
    n = unicodedata.normalize("NFKC", s)
    return "".join(ch for ch in n if ch.isalnum()).lower()

def process(t, c):
    out = []
    for ln in t.split("\n"):
        if is_sep_line(ln):
            out.append("***")
            c["sep"] += 1
            continue
        out.append(ln)
    t = "\n".join(out)

    t, n = UNDERSCORE_ART.subn("", t); c["underscore"] = n
    t, n = DASH_BRACKET.subn("***", t); c["dashbrk"] = n
    t, n = QMARK.subn("？", t); c["qmark"] = n

    # zw 残片
    pieces, last = [], 0
    for m in ZWSEG.finditer(t):
        a = norm_alnum(m.group())
        if "zw" in a and len(a) <= 12:
            pieces.append(t[last:m.start()]); last = m.end()
            c["zw"] += 1
    pieces.append(t[last:])
    t = "".join(pieces)

    t, n = re.subn(r"(?:\r?\n){3,}", "\r\n\r\n", t); c["blank"] = n
    return t

def main():
    os.makedirs(OUT, exist_ok=True)
    tot = collections.Counter()
    nf = ch = 0
    for root, dirs, fs in os.walk(SRC):
        for fn in fs:
            if not fn.lower().endswith(".txt"):
                continue
            fp = os.path.join(root, fn)
            rel = os.path.relpath(fp, SRC)
            with open(fp, "r", encoding="utf-8", errors="replace", newline="") as f:
                t0 = f.read()
            c = collections.Counter()
            t = process(t0, c)
            dest = os.path.join(OUT, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8", newline="") as fh:
                fh.write(t)
            nf += 1
            if t != t0:
                ch += 1
            tot.update(c)
    print(f"files={nf} changed={ch}")
    for k in sorted(tot):
        if tot[k]:
            print(f"{k}\t{tot[k]}")

if __name__ == "__main__":
    main()
