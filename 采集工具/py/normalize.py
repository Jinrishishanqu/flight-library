# -*- coding: utf-8 -*-
"""
校对引擎 v2 —— 用经过验证的外部库替代自研启发式。

组件：
  charset_normalizer  编码探测（替代 Get-Encoding 猜测）
  ftfy                mojibake / 半角乱码修复（替代手写替换表）
  opencc              t2s / s2t 繁简统一（替代自研映射）
  regex               Unicode 属性正则（中文语境判定）
  rapidfuzz           近似行比对（用于重复行/重复段检测）

只做「清洗 + 版式」：文字内容与先后顺序保持原样（README 规则 1-4）。
输出：UTF-8 BOM + CRLF，段间一个空行。

用法：
  python normalize.py --in FILE --out FILE [--stats FILE] [--no-t2s] [--keep-indent]
  python normalize.py --dir DIR --outdir DIR2 [--glob *.txt]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from dataclasses import dataclass, field

import regex
import ftfy
from charset_normalizer import from_bytes

try:
    import opencc
    _CC_T2S = opencc.OpenCC("t2s")
except Exception:  # pragma: no cover
    _CC_T2S = None


# ---------------------------------------------------------------- 编码与解码
def decode_bytes(raw: bytes) -> tuple[str, str]:
    """返回 (text, encoding)。BOM 优先，其次 charset_normalizer，最后 gb18030。"""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", "replace"), "utf-8-sig"
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", "replace"), "utf-16"
    best = from_bytes(raw).best()
    if best is not None and best.encoding:
        try:
            return str(best), best.encoding
        except Exception:
            pass
    for enc in ("utf-8", "gb18030", "big5", "gbk"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace"), "utf-8/replace"


# ---------------------------------------------------------------- 噪声清除
HTML_ENT = regex.compile(r"&(?:nbsp|amp|lt|gt|quot|#\d+|#x[0-9a-fA-F]+|ldquo|rdquo|hellip|mdash|middot);")
HTML_TAG = regex.compile(r"</?(?:br|p|div|span|font|b|i|u|em|strong|a|img|table|tr|td|hr|h[1-6])\b[^>]*>", regex.I)

# 整行推广/站方噪声（只在整行命中时删除，正文里出现这些词不受影响）
AD_LINE = [
    regex.compile(r"^(?:https?://|www\.)\S+$", regex.I),
    regex.compile(r"^[a-zA-Z0-9\-]+\.[a-zA-Z]{2,6}(?:/\S*)?$"),
    regex.compile(r"请记住本站|记住本站域名|本站域名|本站地址|最新网址|地址发布页|发布页|防走失|永久域名"),
    regex.compile(r"圈--儿|两条杠|阅读记录功能|备用网址|发布地址|最新地址"),
    regex.compile(r"最新章节|全文阅读|无弹窗|免费阅读|手机阅读|手机用户请浏览|天才一秒记住|一秒记住"),
    regex.compile(r"第一版主|66acg|laowang|sis001|色城|草榴|1024社区|老王论坛|萌の领域|维咔|VikACG", regex.I),
    regex.compile(r"本章未完|点击下一页|点击翻页|加入书签|投推荐票|求月票|求订阅|求收藏|求推荐"),
    regex.compile(r"^\[?\s*(?:数字分页|分页)\s*\]?|继续阅读\s*-+>>"),
    regex.compile(r"^【?\s*(?:待续|未完待续|全文完|本书完)\s*】?$"),
    regex.compile(r"^(?:作者|字数|更新时间|发布时间)\s*[:：]\s*\S*$"),
    # 论坛发帖元数据
    regex.compile(r"^\s*是否(?:本站|首发|原创|太监)\s*[:：]"),
    regex.compile(r"^\s*(?:[0-9０-９]{2,4}\s*年\s*[/／-]?\s*[0-9０-９]{1,2}\s*月\s*[/／-]?\s*[0-9０-９]{1,2}\s*日)?\s*发表于"),
    regex.compile(r"^\s*(?:本帖最后由|本帖最后由|最后由)\s"),
    regex.compile(r"^\s*(?:转帖|转自|出处)\s*[:：]"),
    regex.compile(r"^\s*(?:字数|约)\s*[0-9０-９]+\s*字\s*$"),
]

# 行内碎片：从一行中挖掉，不影响其余正文
AD_INLINE = [
    regex.compile(r"本章未完\s*[，,]?\s*点击?\s*[\[【]\s*数字分页\s*[\]】]\s*继续阅读\s*-*>>\s*(?:[\[【]\d+[\]】])*"),
    regex.compile(r"本章未完\s*[，,]?\s*点击?下一页[^\n]{0,10}"),
    regex.compile(r"最新章节请访问\s*\S*"),
    regex.compile(r"手机用户请浏览\s*\S*"),
    regex.compile(r"天才一秒记住\s*\S*"),
    # 蓝色书吧 / 第一版主系站点的地址发布页广告（含西里尔字母伪装）
    regex.compile(r"发布\s*\\?\s*页地址\s*\{?[^\u4e00-\u9fff，。！？]{0,90}"),
    regex.compile(r"地址发布页[^\u4e00-\u9fff，。！？]{0,60}"),
    regex.compile(r"[\u0448\u0449\u0445]{2,}[.．]?[A-Za-z\uFF41-\uFF5A.]{0,20}[^\s。]{0,15}"),
    regex.compile(r"(?:Ltxs|ltxs|LTXS)[^\s。\n]{0,25}"),
    regex.compile(r"[\uFF48\uFF54hHtTｈｔ][\uFF54tTｔ][\uFF54tTｔ][\uFF50\uFF55pPｐ]\s*[:：]?\s*[^\u4e00-\u9fff]{0,50}"),
    regex.compile(r"[\uFF57wWｗ]{3}\s*[.．][^\u4e00-\u9fff]{0,40}"),
    regex.compile(r"\(function\s*\(\s*\)\s*\{[^\n]{0,400}?\}\)\(\);?"),
    regex.compile(r"(?:https?://|www\.)[^\s，。！？、）】」』]{2,}"),
    regex.compile(r"\b(?:nbsp|amp|quot|lt|gt|ldquo|rdquo|hellip|mdash|middot);"),
    regex.compile(r"<\s*/?\s*(?:p|br|div|span|font|b|i|u|em|strong|a|img|table|tr|td|hr|h[1-6])\b[^>]*>", regex.I),
    regex.compile(r"(?<![\w<>])/?P>\s*"),
    regex.compile(r"^(?:\[\s*)|\s*$"),
]

# 章节标题：第X章 / 第X回 / 【第X回：…】 / 序章 / 楔子 / 番外
CHAP_HEAD = regex.compile(
    r"^\s*(?:【)?\s*(?:第\s*[0-9一二三四五六七八九十百千万零〇两]+\s*[章回节幕话]|序章|序言|楔子|引子|尾声|后记|番外|终章|大结局)"
)


def strip_html(text: str) -> str:
    text = HTML_ENT.sub(lambda m: _ent(m.group(0)), text)
    text = HTML_TAG.sub("\n", text)
    text = text.replace("\u00a0", " ").replace("\u3000\u3000", "\u3000\u3000")
    return text


_ENT_MAP = {
    "nbsp": " ", "amp": "&", "lt": "<", "gt": ">", "quot": '"',
    "ldquo": "“", "rdquo": "”", "hellip": "…", "mdash": "—", "middot": "·",
}


def _ent(tok: str) -> str:
    body = tok[1:-1]
    if body.startswith("#x") or body.startswith("#X"):
        try:
            return chr(int(body[2:], 16))
        except ValueError:
            return tok
    if body.startswith("#"):
        try:
            return chr(int(body[1:]))
        except ValueError:
            return tok
    return _ENT_MAP.get(body.lower(), tok)


def drop_noise_lines(lines: list[str]) -> tuple[list[str], list[str]]:
    """先挖行内碎片，再删整行噪声。"""
    kept, dropped = [], []
    for ln in lines:
        s = ln
        for p in AD_INLINE:
            s = p.sub("", s)
        for p in NOISE_DB:
            s = p.sub("", s)
        s2, killed = despace_spam(s)
        if killed:
            dropped.append(ln.strip()[:80])
            kept.append("")
            continue
        s = s2.strip()
        if not s:
            if ln.strip():
                dropped.append(ln.strip()[:80])
            kept.append("")
            continue
        if any(p.search(s) for p in AD_LINE):
            dropped.append(s[:80])
            continue
        kept.append(s)
    return kept, dropped


def dedup_head_lines(lines: list[str], window: int = 14, sim: int = 85) -> tuple[list[str], int]:
    """删掉开头重复出现的章节抬头（论坛常常同一标题贴两遍）。"""
    from rapidfuzz import fuzz

    head_idx = [i for i, ln in enumerate(lines[:window]) if ln.strip()]
    seen: list[str] = []
    kill: set[int] = set()
    for i in head_idx:
        s = lines[i].strip()
        if CHAP_HEAD.match(s) or regex.search(r"[（(]\s*第.{1,6}[章回]", s):
            if any(fuzz.ratio(s, t) >= sim for t in seen):
                kill.add(i)
            else:
                seen.append(s)
    if not kill:
        return lines, 0
    return [ln for i, ln in enumerate(lines) if i not in kill], len(kill)


# ---------------------------------------------------------------- 标点规范化
# 中文语境下的半角标点转全角（跳过数字千分位、URL、英文缩写、时间 12:30）
_HALF2FULL = {",": "，", ";": "；", "?": "？", "!": "！", ":": "："}
_CN = r"\u4e00-\u9fff\u3400-\u4dbf“”‘’《》「」『』（）—…·"


def normalize_punct(text: str, stats: dict) -> str:
    n = 0

    def ok(tok: str, pre: str, post: str) -> bool:
        if tok == ":" and regex.search(r"\d\s*$", pre) and regex.match(r"\s*\d", post):
            return False
        if tok == "," and regex.search(r"\d$", pre) and regex.match(r"\d{3}", post):
            return False
        return True

    def repl_a(m: regex.Match) -> str:
        """中文 + 半角标点 + 中文/数字/括号。"""
        nonlocal n
        pre, tok, post = m.group(1), m.group(2), m.group(3)
        if not ok(tok, pre, post):
            return m.group(0)
        n += 1
        return pre + _HALF2FULL[tok] + post

    def repl_b(m: regex.Match) -> str:
        """前置中文（lookbehind）+ 半角标点 + 中文。"""
        nonlocal n
        tok = m.group(1)
        if not ok(tok, "x", "x"):
            return m.group(0)
        n += 1
        return _HALF2FULL[tok]

    text = regex.sub(rf"([{_CN}])\s*([,;?!:])\s*([{_CN}0-9（(])", repl_a, text)
    text = regex.sub(rf"(?<=[{_CN}])\s*([,;?!:])(?=[{_CN}])", repl_b, text)
    # 中文后紧跟半角句点（非省略号、非小数、非网址）
    def dot_repl(m: regex.Match) -> str:
        nonlocal n
        n += 1
        return m.group(1) + "。"

    text = regex.sub(rf"([{_CN}])\s*\.\s*(?=[{_CN}])", dot_repl, text)
    # 中文里的半角括号转全角
    text = regex.sub(rf"(?<=[{_CN}])\(", "（", text)
    text = regex.sub(rf"(?<=[{_CN}])\)", "）", text)
    # 中文里的半角引号
    text = regex.sub(rf'(?<=[{_CN}])"', "”", text)
    stats["punct_fixed"] = n
    return text


def tidy_space(text: str) -> str:
    text = regex.sub(r"\r\n?|\n", "\n", text)                            # 统一换行，清掉 \r\r\n
    text = text.replace("\u3000", "\u3000")  # 保留全角空格（首行缩进）
    text = regex.sub(r"[ \t\u00a0]+$", "", text, flags=regex.M)          # 行尾空白
    text = regex.sub(r"\u3000+$", "", text, flags=regex.M)                # 行尾全角空格
    text = regex.sub(r"(?<=[\u4e00-\u9fff])\s{2,}(?=[\u4e00-\u9fff])", "", text)  # 汉字间多余空格
    text = regex.sub(r"\n{3,}", "\n\n", text)                              # 连续空行压一
    # 分隔线压缩成 3 个字符，保留结构
    text = regex.sub(r"(?m)^([=\-*_~·])\1{3,}$", lambda m: m.group(1) * 3, text)
    return text


def fix_lookalike(text: str, stats: dict) -> str:
    """明显的形近/异体替换（只处理无歧义的）。"""
    n = 0
    pairs = [("ㄧ", "一"), ("\uFFFD", ""), ("\u25A1", "")]
    for a, b in pairs:
        c = text.count(a)
        if c:
            n += c
            text = text.replace(a, b)
    stats["lookalike_fixed"] = n
    return text


# ---------------------------------------------------------------- 段落重建
END_PUNCT = "。！？…”』」』）】!?.\"'"
_INDENT = regex.compile(r"^(?:\u3000{2,}| {2,}|\t)")


@dataclass
class Layout:
    fixed_width: int = 0          # 固定行宽众数（0 = 无）
    end_ratio: float = 0.0        # 行尾终止标点比例
    blank_ratio: float = 0.0      # 空行比例
    dialogue_heavy: bool = False


def analyze_layout(lines: list[str]) -> Layout:
    body = [ln for ln in lines if ln.strip()]
    if not body:
        return Layout()
    widths: dict[int, int] = {}
    ends = 0
    for ln in body:
        s = ln.rstrip()
        widths[len(s)] = widths.get(len(s), 0) + 1
        if s and s[-1] in END_PUNCT:
            ends += 1
    top = max(widths.items(), key=lambda kv: kv[1])
    fixed = top[0] if top[1] >= max(3, len(body) * 0.15) and top[0] >= 20 else 0
    quote_lines = sum(1 for ln in body if ln.strip().startswith(("“", '"', "「")))
    return Layout(
        fixed_width=fixed,
        end_ratio=ends / len(body),
        blank_ratio=1 - len(body) / max(1, len(lines)),
        dialogue_heavy=quote_lines > len(body) * 0.35,
    )


def rebuild(lines: list[str], lay: Layout, stats: dict) -> list[str]:
    """把折行接回段落。返回段落列表（不含空行）。"""
    paras: list[str] = []
    buf = ""
    joins = 0
    for raw in lines:
        ln = raw.rstrip("\r\n")
        s = ln.strip()
        if not s:
            if buf:
                paras.append(buf)
                buf = ""
            continue
        if CHAP_HEAD.match(s):
            if buf:
                paras.append(buf)
                buf = ""
            paras.append(s)
            continue
        indented = bool(_INDENT.match(ln))
        prev_open = bool(buf) and buf[-1] not in END_PUNCT
        if not buf:
            buf = s
            continue
        # 上一段没有终止标点 → 继续接
        cont = prev_open
        # 固定行宽排版：上一行长度接近众数，且本行无缩进
        if not cont and lay.fixed_width and not indented:
            if abs(len(buf) - lay.fixed_width) <= 3 and lay.end_ratio < 0.75:
                cont = True
        # 上一行以引号内逗号等结尾，本行以引号收尾 → 接
        if not cont and regex.search(r"[，、；：]$", buf) and not indented:
            cont = True
        if cont:
            buf += s if not s[:1].isascii() or s[:1] in "，。！？" else " " + s
            joins += 1
        else:
            paras.append(buf)
            buf = s
    if buf:
        paras.append(buf)
    stats["joins"] = joins
    return paras


# ---------------------------------------------------------------- 主流程
def load_noise_db(path: str | None = None) -> list[regex.Pattern]:
    """加载从 SoNovel 书源规则提取的成熟过滤正则（噪声词库）。"""
    import json
    import pathlib

    cand = pathlib.Path(path) if path else pathlib.Path(__file__).resolve().parents[1] / "噪声词库.json"
    if not cand.exists():
        return []
    try:
        data = json.loads(cand.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for item in data.get("patterns", []):
        rule = item.get("rule", "")
        try:
            out.append(regex.compile(rule, regex.I | regex.S))
        except Exception:
            continue
    return out


NOISE_DB: list[regex.Pattern] = load_noise_db()

# 反过滤符号广告：如「最⊥新⊥小⊥说⊥在⊥六⊥9⊥书⊥吧⊥首⊥发！」
SYMBOL_INTERLEAVE = regex.compile(r"[⊥◇◆★☆■□●○※¤§¶‖∣/\\|_~^*+]{1,3}")


def despace_spam(line: str) -> tuple[str, bool]:
    """若一行被符号穿插成广告，去掉符号后能命中噪声库 → 整行丢弃。"""
    if not NOISE_DB:
        return line, False
    syms = len(SYMBOL_INTERLEAVE.findall(line))
    if syms < 3 or syms < len(line) * 0.08:
        return line, False
    flat = SYMBOL_INTERLEAVE.sub("", line)
    if any(p.search(flat) for p in NOISE_DB):
        return "", True
    return line, False


@dataclass
class Result:
    text: str = ""
    stats: dict = field(default_factory=dict)


def normalize_text(raw: bytes | str, do_t2s: bool = True, keep_indent: bool = True) -> Result:
    stats: dict = {}
    if isinstance(raw, str):
        text, enc = raw, "str"
    else:
        text, enc = decode_bytes(raw)
    stats["encoding"] = enc

    fixed = ftfy.fix_text(
        text,
        fix_character_width=False,   # 不要把全角标点压成半角
        uncurl_quotes=False,         # 不要把 “ ” 变成 " "
        unescape_html=False,         # HTML 实体自己处理
        fix_line_breaks=False,       # 保留原始换行，交给段落重建
    )
    if fixed != text:
        stats["ftfy_changed"] = True
    text = fixed

    if do_t2s and _CC_T2S is not None:
        conv = _CC_T2S.convert(text)
        if conv != text:
            stats["t2s_chars"] = sum(1 for a, b in zip(text, conv) if a != b)
            text = conv

    text = strip_html(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    lines, dropped = drop_noise_lines(lines)
    lines, head_dups = dedup_head_lines(lines)
    stats["noise_lines"] = len(dropped)
    stats["head_dups"] = head_dups
    if dropped:
        stats["noise_sample"] = dropped[:5]

    text = "\n".join(lines)
    text = normalize_punct(text, stats)
    text = fix_lookalike(text, stats)

    lay = analyze_layout(text.split("\n"))
    stats["fixed_width"] = lay.fixed_width
    stats["end_ratio"] = round(lay.end_ratio, 3)

    paras = rebuild(text.split("\n"), lay, stats)

    out_paras = []
    for p in paras:
        if keep_indent and _INDENT.match(p):
            p = "\u3000\u3000" + p.lstrip(" \t\u3000").rstrip()
        else:
            p = p.lstrip(" \t\u3000").rstrip()
        if p:
            out_paras.append(p)
    body = "\n\n".join(out_paras)
    body = tidy_space(body)
    stats["paras"] = len(out_paras)
    stats["chars"] = len(regex.sub(r"\s", "", body))
    return Result(text=body + "\n", stats=stats)


def write_out(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as fh:
        fh.write(text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src")
    ap.add_argument("--out", dest="dst")
    ap.add_argument("--dir", dest="srcdir")
    ap.add_argument("--outdir", dest="dstdir")
    ap.add_argument("--glob", default="*.txt")
    ap.add_argument("--stats", dest="stats")
    ap.add_argument("--no-t2s", action="store_true")
    ap.add_argument("--no-indent", action="store_true")
    args = ap.parse_args(argv)

    do_t2s = not args.no_t2s
    if args.src and args.dst:
        raw = open(args.src, "rb").read()
        res = normalize_text(raw, do_t2s, (not args.no_indent))
        write_out(args.dst, res.text)
        if args.stats:
            json.dump(res.stats, open(args.stats, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(json.dumps(res.stats, ensure_ascii=False))
        return 0

    if args.srcdir and args.dstdir:
        import glob as _glob
        import pathlib
        src = pathlib.Path(args.srcdir)
        dst = pathlib.Path(args.dstdir)
        files = [
            f for f in sorted(src.rglob(args.glob))
            if not any(part.startswith("_") for part in f.relative_to(src).parts[:-1])
        ]
        rows = []
        for f in files:
            rel = f.relative_to(src)
            out = dst / rel
            try:
                res = normalize_text(f.read_bytes(), do_t2s, (not args.no_indent))
                write_out(str(out), res.text)
                rows.append({"file": str(rel), **{k: v for k, v in res.stats.items() if k != "noise_sample"}})
            except Exception as e:  # pragma: no cover
                rows.append({"file": str(rel), "error": f"{type(e).__name__}: {e}"})
        if args.stats:
            json.dump(rows, open(args.stats, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"done {len(rows)} files -> {dst}")
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
