# -*- coding: utf-8 -*-
"""综合校勘 S1 精修：域名残片扩展删除 + HTML 残留 + 分页符 + 孤行标点 + 省略号规范化"""
import os, re, collections, json

SRC = r"D:\article_tools\out\clean1"
OUT = r"D:\article_tools\out\clean2"

CJK = r"\u4e00-\u9fff"
# 域名/广告特征串（含全角与特殊变体）
HINT = re.compile(
    r"(?i:ltx)|(?i:xs[fｆ]b)|(?i:4v4v4v)|(?i:gmail)|ＧＭＡＩＬ|Ｃ⊙|⊙㎡|㎡|"
    r"(?i:\.c[oｏ]m\b)|(?i:\.us\b)|(?i:\.m[eｅ]\b)|(?i:w[wｗ]{2})|℃|ㄈòМ|〇1Bz|wk\^zw"
)
# 那些词前后允许被一起吃掉的非汉字字符
EDGE = re.compile(r"[^\u4e00-\u9fff，。！？、；：「」『』（）《》…—～·\s]")

def scrub_domains(t, counter):
    out = []
    i = 0
    n = len(t)
    while i < n:
        m = HINT.search(t, i)
        if not m:
            out.append(t[i:])
            break
        a = m.start()
        b = m.end()
        # 向左扩展，吃掉连续的非汉字边缘字符
        while a > 0 and EDGE.match(t[a - 1]):
            a -= 1
        # 向右扩展
        while b < n and EDGE.match(t[b]):
            b += 1
        # 顺便吞掉紧随其后的空格
        while b < n and t[b] in " \t":
            b += 1
        out.append(t[i:a])
        counter["S1_domain"] += 1
        i = b
    return "".join(out)

RULES = [
    ("S1_center",   re.compile(r"</?center>", re.I), ""),
    ("S1_page",     re.compile(r"【\d{1,2}】"), ""),
    ("S1_qmark",    re.compile(r"[?]{3,}"), ""),
    ("S1_br",       re.compile(r"\[br/?\]|\[/?[biu]\]", re.I), ""),
    ("S1_bom",      re.compile(r"\ufeff"), ""),
]

def main():
    os.makedirs(OUT, exist_ok=True)
    stat = collections.Counter()
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
            c = collections.Counter()

            t = scrub_domains(t, c)

            for key, rx, rep in RULES:
                t, n = rx.subn(rep, t)
                if n:
                    c[key] += n

            # 省略号规范化
            t, n = re.subn(r"[.．]{3,}", "……", t)
            if n:
                c["S1_ellipsis"] = n

            # 孤行标点（整行只剩标点）
            t, n = re.subn(r"(?m)^[ \t]*[;；,，.。·、\u3000]+[ \t]*\r?\n", "", t)
            if n:
                c["S1_lonepunct"] = n

            # 章节分隔线规范化 ＊＊＊... -> ***
            t, n = re.subn(r"[*＊﹡]{3,}", "***", t)
            if n:
                c["S1_sep"] = n

            # 连续空行压缩到最多一个空行
            t, n = re.subn(r"(?:\r?\n)[ \t\u3000]*(?:\r?\n)+", "\r\n\r\n", t)
            if n:
                c["S1_blank"] = n

            if t != t0:
                sub = os.path.relpath(root, SRC)
                d = os.path.join(OUT, sub)
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, fn), "w", encoding="utf-8", newline="") as fh:
                    fh.write(t)
                files += 1
                for k, v in c.items():
                    stat[k] += v

    json.dump(dict(stat), open(os.path.join(OUT, "_ledger2.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"changed_files={files}")
    for k, v in sorted(stat.items()):
        print(f"{k}\t{v}")

if __name__ == "__main__":
    main()
