# -*- coding: utf-8 -*-
"""统一校勘 v2：从原始全量重放，修正 CRLF 锚点 + 撤销问号压缩 + 补 HTML/水印规则"""
import os, re, json, collections, unicodedata

SRC = r"D:\article_tools\work\校对后文章"
OUT = r"D:\article_tools\out\final4"
LEX = r"D:\article_tools\lexicon"

def load_conf():
    d = {}
    with open(os.path.join(LEX, "confusion.txt"), "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if not line.strip() or line.startswith("#"):
                continue
            parts = re.split(r"[\t ]+", line.strip())
            if len(parts) >= 2:
                d[parts[0]] = parts[1]
    return d

CONF = load_conf()
CONF_KEYS = sorted(CONF, key=len, reverse=True)
CONF_RE = re.compile("|".join(map(re.escape, CONF_KEYS))) if CONF_KEYS else None

PINYIN = {
    "Rou": "肉", "rou": "肉", "Gui": "龟", "gui": "龟", "Jing": "精", "jing": "精",
    "She": "射", "she": "射", "Nei": "内", "nei": "内", "Ru": "乳", "ru": "乳",
    "Ruan": "软", "ruan": "软", "Jian": "坚", "jian": "坚", "Di": "低", "di": "低",
    "ShenYin": "呻吟", "shenyin": "呻吟", "Shenyin": "呻吟",
}
PINYIN_RE = re.compile("|".join(sorted(map(re.escape, PINYIN), key=len, reverse=True)))

AD_EN = re.compile(r"(?i)depiler|dwnlad|saved\s*using|\bversin\b|powered\s*by|\bureed\b|\buploade")
FEATURE = re.compile(r"(?i)ltx|txs|xsb|xsf|gmail|www|4v4|1bz|bz|com|admin|hxsoft")
SEG = re.compile(r"[^\u4e00-\u9fff，。！？、；：「」『』（）《》…—～·\s]{2,}")
KEEP = {"level", "duang", "duanduang", "sm", "jk", "av", "txt", "bj", "3p", "np",
        "pc", "xp", "hk", "tv", "ip", "ok", "mm", "cm", "kg", "player", "error",
        "party", "fucker", "debuff", "rank"}

PIPE = re.compile(r"[|｜]")
BOX = re.compile(r"[囗□]")
ENTITY = re.compile(r"&(?:nbsp|amp|lt|gt|quot|#\d+);?", re.I)
HTMLTAG = re.compile(r"(?i)</?(?:center|p|br|font|span|div|html|body|table|tr|td|b|i|u|strong|em)[^>]{0,40}>")
QQ = re.compile(r"(?i)q{2}\s*群?\s*[:：]?\s*\d{6,12}")
UNDERSCORE_ART = re.compile(r"(?m)^[ \t]*[_＿]{3,}[ \t]*\r?$")

PAGE_MARK = re.compile(r"】?【\d+】")
CENTER = re.compile(r"(?m)^[ \t]*[)\]}>】」』]+[ \t]*\r?$")
ELLIPSIS = re.compile(r"[.．]{3,}|…{2,}")
SEP_LINE = re.compile(r"(?m)^[ \t\u3000]*[─━═\-—_~～*＊#★☆※·]{4,}[ \t\u3000]*\r?$")
LONE_PUNCT = re.compile(r"(?m)^[ \t]*[，。！？、；：,.;:!?]+[ \t]*\r?$")
QMARK_HALF = re.compile(r"\?{3,}")
WATER_SYM = re.compile(r"[★☆╗╒╕╘╙℃⊙㎡〓]")

def norm_alnum(s):
    n = unicodedata.normalize("NFKC", s)
    return "".join(ch for ch in n if ch.isalnum()).lower()

def process(t, c):
    lines = t.split("\n")
    keep = []
    for ln in lines:
        raw = ln.rstrip("\r")
        a = norm_alnum(raw)
        if AD_EN.search(raw):
            c["L1_ad_en"] += 1
            continue
        if a and len(a) >= 4:
            han = sum(1 for ch in raw if "\u4e00" <= ch <= "\u9fff")
            if han <= 8 and FEATURE.search(a):
                c["L1_ad_cn"] += 1
                continue
        keep.append(ln)
    t = "\n".join(keep)

    # L2 行内归一化域名碎片
    pieces, last = [], 0
    for m in SEG.finditer(t):
        seg = m.group()
        a = norm_alnum(seg)
        if len(a) < 2 or a in KEEP:
            continue
        if FEATURE.search(a):
            pieces.append(t[last:m.start()]); last = m.end()
            c["L2_domain"] += 1
    pieces.append(t[last:])
    t = "".join(pieces)

    # L3 打码还原
    t, n = PIPE.subn("", t); c["L3_pipe"] = n
    t, n = BOX.subn("口", t); c["L3_box"] = n
    def py_replace(m):
        c["L3_pinyin"] += 1
        return PINYIN[m.group()]
    t = PINYIN_RE.sub(py_replace, t)

    # L4 实体/HTML/QQ
    t, n = HTMLTAG.subn("", t); c["L4_html"] = n
    t, n = ENTITY.subn("", t); c["L4_entity"] = n
    t, n = QQ.subn("", t); c["L4_qq"] = n
    t, n = UNDERSCORE_ART.subn("", t); c["L4_underscore"] = n
    t, n = WATER_SYM.subn("", t); c["L4_sym"] = n

    # L5 排版（注意 CRLF 锚点已修）
    t, n = PAGE_MARK.subn("", t); c["L5_page"] = n
    t, n = SEP_LINE.subn("***", t); c["L5_sep"] = n
    t, n = CENTER.subn("", t); c["L5_center"] = n
    t, n = ELLIPSIS.subn("……", t); c["L5_ellipsis"] = n
    t, n = QMARK_HALF.subn("？", t); c["L5_qmark"] = n
    t, n = LONE_PUNCT.subn("", t); c["L5_lonepunct"] = n

    # L6 专名
    if CONF_RE:
        def rep(m):
            c["L6_name"] += 1
            return CONF[m.group()]
        t = CONF_RE.sub(rep, t)

    # L7 空白
    t, n = re.subn(r"[ \t\u3000]+(?=\r?$)", "", t); c["L7_trail"] = n
    t, n = re.subn(r"(?:\r?\n)[ \t\u3000]*(?:\r?\n){2,}", "\r\n\r\n", t); c["L7_blank"] = n
    t, n = re.subn(r"(?:\r?\n){3,}", "\r\n\r\n", t); c["L7_blank3"] = n
    return t

def main():
    os.makedirs(OUT, exist_ok=True)
    tot = collections.Counter()
    nfiles = changed = 0
    for root, dirs, fs in os.walk(SRC):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
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
            nfiles += 1
            if t != t0:
                changed += 1
            tot.update(c)

    json.dump({"files": nfiles, "changed": changed, "stat": dict(tot)},
              open(os.path.join(OUT, "_ledger_all.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"files={nfiles} changed={changed}")
    for k in sorted(tot):
        if tot[k]:
            print(f"{k}\t{tot[k]}")

if __name__ == "__main__":
    main()
