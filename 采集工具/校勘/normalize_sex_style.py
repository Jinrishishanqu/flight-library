# -*- coding: utf-8 -*-
"""成人语汇还原 + 符号风格统一 + 行内水印清理（final7 -> final9）"""
import os, re, collections

SRC = r"D:\article_tools\out\final15"
OUT = r"D:\article_tools\out\final17"

BASE = ["肉棒", "龟头", "精液", "射精", "阴道", "阴茎", "阴唇", "子宫", "奶子",
        "乳头", "屁股", "鸡巴", "骚逼", "小穴", "淫水", "高潮", "淫穴", "肉穴",
        "肉洞", "阳具", "阴蒂", "睾丸", "乳房", "淫荡", "骚穴", "肉屌", "大屌"]

GAP_RES = []
GAP_HARD = re.compile(r"[#＊*\-–—―~～`'·^！？]{1,3}")
for w in BASE:
    body = r"[^\u4e00-\u9fff\r\n]{1,3}".join(map(re.escape, list(w)))
    GAP_RES.append((w, re.compile(body)))

# 明确自审变形：内部插入非标点符号 —— 强制还原
HARD_RES = []
for w in BASE:
    body = GAP_HARD.pattern.join(map(re.escape, list(w)))
    HARD_RES.append((w, re.compile(body)))

# 内部只可能插符号、绝无正常断句的词 —— 无论插什么都还原（浪叫拖音 … 除外）
PUNCT_WORDS = ["春药", "爱液", "淫叫", "婊子", "骚货", "骚屄", "豪乳", "巨乳", "足交",
               "口交", "肛交", "屁眼", "呻吟", "乳晕", "阴户", "阴核", "蜜穴", "骚穴",
               "菊穴", "春囊", "淫液", "爱抚", "抽插", "舔弄", "口爆"]
PUNCT_GAP = r"(?:(?![…])[^\u4e00-\u9fff\r\n]){1,3}"
PUNCT_RES = []
for w in PUNCT_WORDS:
    body = PUNCT_GAP.join(map(re.escape, list(w)))
    PUNCT_RES.append((w, re.compile(body)))

# 连续「单字+逗号」的字词割裂（防和谐写法），如「操，你，丫，的，婊，子」
CHAR_ISOLATE = re.compile(r"(?m)(?:^|(?<=[，。！？…“\r\n]))(?:[\u4e00-\u9fff]，){3,}[\u4e00-\u9fff]")
DOUBLE_COMMA = re.compile(r"内，，射")

STAR_MASK = re.compile(r"(?<=[\u4e00-\u9fff])[*＊]{1,6}(?=[\u4e00-\u9fff])")
# 汉字间夹非中文符号 = 自审打码，一律删（# 不是中文标点，可盲删；～「」等另有语义，不在此列）
HASH_MASK = re.compile(r"(?<=[\u4e00-\u9fff])[#＃](?=[\u4e00-\u9fff])")
TICK_MASK = re.compile(r"(?<=[\u4e00-\u9fff])[`'^](?=[\u4e00-\u9fff])")
BSLASH_MASK = re.compile(r"(?<![A-Za-z0-9:/\\])\\(?![A-Za-z0-9:/\\])")
# 日文异体/形近单字归一
CHAR_FIX = {"黒": "黑", "髙": "高", "﨑": "崎", "冨": "富", "曻": "升"}
CHAR_BREAK = re.compile(r"[\u4e00-\u9fff][…。，；！？][\u4e00-\u9fff][…。，；！？][\u4e00-\u9fff]")

LEAD_DASH = re.compile(r"(?m)^-{3,}[ \t]*")
TRAIL_DASH = re.compile(r"(?m)[ \t]*-{3,}\r?$")
DASH = re.compile(r"(?<!—)--+(?!—)|(?<!—)—(?!—)")

Q_ASCII = re.compile(r'"([^"\r\n]{0,200})"')
WAVE = re.compile(r"~")
ELLIP_DOT = re.compile(r"\.{2,}")
ELLIP_ONE = re.compile(r"(?<!…)…(?!…)")
PAREN = re.compile(r"\(([^()\r\n]{0,60})\)")
BRACKET = re.compile(r"\[([^\[\]\r\n]{0,60})\]")

# ---------- 行内盗版站水印 ----------
DECO = r"(?:[^\u4e00-\u9fff\r\n]|[页址网布发邮箱最寻回记到]){0,4}"

def wm(s):
    parts = [re.escape(ch) for ch in s]
    return DECO.join(parts)

WM_PARTS = [
    "地址发布邮箱", "地址发布", "地址发", "发布邮箱地址", "发布邮箱", "地址", "邮箱",
    "发新地址", "最新地址", "最新发布", "最新网址", "最新网", "网址",
    "寻回", "找回", "更多精彩内容", "更多精彩", "记住发邮件到", "发送任意内容到", "发邮件到",
    "先到这里", "原始地址", "Nordfx书库", "龙腾小说", "书库",
]
WM_RE = re.compile("|".join(wm(p) for p in sorted(WM_PARTS, key=len, reverse=True)))
WM_CHAPTER = re.compile(r"(?m)^[ \t]*chapter[:：][^\r\n\]]{0,80}\][ \t]*\r?$")
ORPHAN = re.compile(r"[╒╗╜╞╡∷↑↓★☆]")
WM_QMARK = re.compile(r"(?<=[。，！？…”])\?(?=[\u4e00-\u9fff])")
WM_AT = re.compile(r"(?<![A-Za-z0-9])@(?![A-Za-z0-9])")
WM_AMP = re.compile(r"&#;?|&;")
WM_DQ = re.compile(r"'{2,}")
WM_CARET = re.compile(r"(?:\^\.?|\.\^)+")
HASH_JUNK = re.compile(r"#{2,}|#%|%#")
# 被拆散的邮件水印碎片 / 字面转义序列 / 引号包裹的整段水印 / 「发布邮」半截
WM_ESCAPE = re.compile(r"(?:\\[nrt][ \t]*)+")
WM_MAILFRAG = re.compile(r"(?i)sba\s*@?\s*g\s*ma\s*il\.?\s*c\s*o\s*m")
WM_REMEMBER = re.compile(r"[“\"]?请记住[^”\"\r\n]{0,24}[”\"]?")
WM_POSTPART = re.compile(r"[/\\]?发布邮(?![箱件])[^\u4e00-\u9fff\r\n]{0,10}")
WM_QUOTE_TAIL = re.compile(r"[”\"](?=[”\"])")
WM_FABU = re.compile(r"发[\]\s]?布页[^\u4e00-\u9fff\r\n]{0,12}")
WM_FAANY = re.compile(r"[/\\]\s*发(?:任意)?内容[^\u4e00-\u9fff\r\n]{0,3}")

def fix_orphan_quote(t, c):
    """落单的半角引号：按上一个引号的开/闭状态判定"""
    out = []
    last = None
    for ch in t:
        if ch == '"':
            if last == "\u201c":
                out.append("\u201d"); last = "\u201d"
            else:
                out.append("\u201c"); last = "\u201c"
            c["B1_quote_orphan"] += 1
        else:
            out.append(ch)
            if ch in "\u201c\u201d":
                last = ch
    return "".join(out)

PROTECT = ["家里的地址", "联系地址", "具体地址", "确切的联系地址", "告诉您家里的地址"]

def strip_wm(t, c):
    ph = {}
    for i, p in enumerate(PROTECT):
        k = f"\x00P{i}\x00"
        if p in t:
            t = t.replace(p, k)
            ph[k] = p
    # 只在含「地址/邮箱/网址」等词、且该词前后带装饰符或与其他水印词共现时删除
    def rep(m):
        s = m.group()
        core = re.sub(r"[^地址发布邮箱最新网址寻回找更多精彩记发送任意内容先到原始书库龙腾小说Nordfx]", "", s)
        c["W_wm"] += 1
        return ""
    t = WM_RE.sub(rep, t)
    t, n = WM_CHAPTER.subn("", t); c["W_chapter"] = n
    t, n = ORPHAN.subn("", t); c["W_orphan"] = n
    t, n = WM_AMP.subn("", t); c["W_amp"] = n
    t, n = WM_AT.subn("", t); c["W_at"] = n
    t, n = WM_QMARK.subn("", t); c["W_qmark"] = n
    t, n = WM_DQ.subn("", t); c["W_dq"] = n
    t, n = WM_CARET.subn("", t); c["W_caret"] = n
    for k, v in ph.items():
        t = t.replace(k, v)
    return t

def fix_gap(t, c):
    def walk(m, canon):
        s = m.group()
        if s == canon:
            return s
        a, b = m.start(), m.end()
        win = t[max(0, a - 24):min(len(t), b + 24)]
        if len(CHAR_BREAK.findall(win)) >= 2:
            c["A2_skip_style"] += 1
            return s
        c["A1_restore"] += 1
        return canon
    for canon, pat in GAP_RES:
        t = pat.sub(lambda m, cn=canon: walk(m, cn), t)
    return t

def fix_isolate(t, c):
    # CHAR_ISOLATE 已停用：正常浪叫/动作列举（「啊，唔，啊」「吹，舔，吸，啜」「好，好，好」）
    # 与防和谐割裂同形，删除逗号会破坏作者原笔，改为只由 A6_punctword 处理词内割裂
    t, n = DOUBLE_COMMA.subn("内射", t); c["A5_dblcomma"] = n
    return t

def fix_punct(t, c):
    def walk(m, canon):
        s = m.group()
        if s == canon:
            return s
        c["A6_punctword"] += 1
        return canon
    for canon, pat in PUNCT_RES:
        t = pat.sub(lambda m, cn=canon: walk(m, cn), t)
    return t

def process(t, c):
    t = fix_isolate(t, c)
    t = fix_gap(t, c)
    t = fix_punct(t, c)
    t, n = STAR_MASK.subn("", t); c["A3_star"] = n
    t, n = HASH_MASK.subn("", t); c["A3_hash"] = n
    t, n = TICK_MASK.subn("", t); c["A3_tick"] = n
    t, n = BSLASH_MASK.subn("", t); c["A3_bslash"] = n
    for k, v in CHAR_FIX.items():
        n = t.count(k)
        if n:
            t = t.replace(k, v); c["A3_charfix"] += n

    t = strip_wm(t, c)

    t, n = LEAD_DASH.subn("", t); c["B2_lead"] = n
    t, n = TRAIL_DASH.subn("", t); c["B2_trail"] = n

    # 『』：仅当出现「…『 嵌套结构时才作内层引号
    if re.search(r"「[^」\r\n]{0,300}『", t):
        pairs = [("『", "‘"), ("』", "’")]
    else:
        pairs = [("『", "“"), ("』", "”")]
    for a, b in pairs + [("「", "“"), ("」", "”")]:
        n = t.count(a)
        if n:
            t = t.replace(a, b)
            c["B1_quote"] += n

    def ascii_q(m):
        c["B1_quote_ascii"] += 1
        return "“" + m.group(1) + "”"
    t = Q_ASCII.sub(ascii_q, t)
    t = fix_orphan_quote(t, c)
    t, n = HASH_JUNK.subn("", t); c["A3_hashjunk"] = n
    t, n = WM_ESCAPE.subn("\n", t); c["W_escape"] = n
    t, n = WM_MAILFRAG.subn("", t); c["W_mailfrag"] = n
    t, n = WM_REMEMBER.subn("", t); c["W_remember"] = n
    t, n = WM_POSTPART.subn("", t); c["W_postpart"] = n
    t, n = WM_QUOTE_TAIL.subn("", t); c["W_quotetail"] = n
    t, n = WM_FABU.subn("", t); c["W_fabu"] = n
    t, n = WM_FAANY.subn("", t); c["W_faany"] = n

    t, n = DASH.subn("——", t); c["B2_dash"] = n
    t, n = WAVE.subn("～", t); c["B3_wave"] = n
    t = ELLIP_DOT.sub("……", t)
    t, n = ELLIP_ONE.subn("……", t); c["B4_ellip"] = n
    t, n = PAREN.subn(lambda m: "（" + m.group(1) + "）", t); c["B5_paren"] = n
    t, n = BRACKET.subn(lambda m: "【" + m.group(1) + "】", t); c["B6_bracket"] = n

    # 水印删除后留下的悬空标点 / 双空格
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"(?m)[ \t]+\r?$", "", t)
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

