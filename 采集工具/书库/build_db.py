# -*- coding: utf-8 -*-
"""从「校勘版」目录构建书库数据库。

用法：
    python build_db.py            # 增量：已存在的 slug 跳过
    python build_db.py --rebuild  # 删库重建

设计要点：
- 作品 = 一个 txt 文件（原文没有稳定章节，483/486 文件无章标题）
- 章节 = 阅读单元，按 6000 字就近段落边界切分
- 检索 = bigram + unicode61（trigram 查不了 2 字词，实测 薰儿 MATCH 返回 0）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "校勘版"
DB_PATH = Path(__file__).resolve().parent / "data" / "library.db"
SCHEMA = Path(__file__).resolve().parent / "schema.sql"
sys.path.insert(0, str(ROOT / "采集工具" / "词库"))
from lib import Lexicon  # noqa: E402

LX = Lexicon()
sys.stdout.reconfigure(encoding="utf-8")

# ---------- 原作映射 ----------
SOURCE_MAP = {
    "斗破": "斗破苍穹",
    "斗罗": "斗罗大陆",
    "大主宰": "大主宰",
    "武动乾坤": "武动乾坤",
    "凡人修仙传": "凡人修仙传",
    "元尊": "元尊",
    "仙逆": "仙逆",
    "诛仙": "诛仙",
    "神印王座": "神印王座",
    "遮天": "遮天",
    "完美世界": "完美世界",
    "神墓": "神墓",
    "不死不灭": "不死不灭",
}

# 「回」后面紧跟这些字时是普通词而非章标记：
#   第三回合了 / 第一回答 / 第二回顾 / 这第三回来 / 第一回家 / 第二回头 / 第三回事 / 第一回身
NOT_CHAPTER_AFTER = r"(?![合答顾忆家来头事身])"

CHAPTER_RE = re.compile(
    r"(?m)^[ \t]*(第[0-9零一二三四五六七八九十百千两]+[章节回]" + NOT_CHAPTER_AFTER +
    r"|第[0-9零一二三四五六七八九十百千两]+卷"
    r"|序章|楔子|序言|前言|后记|尾声|终章|番外)"
    r"[^\r\n]{0,40}\r?$"
)

# 章节划分的判定阈值
MIN_AVG = 30000        # 平均每章超过这个字数 → 认为原文标记只覆盖局部，不采用
GAP_RATIO = 12.0       # 最大间隔超过中位间隔的这个倍数 → 判定标记断裂
GAP_ABS = 60000        # 无论如何，出现这么长的一段没有章标记，就认定标记不完整
MAX_REAL_CHAPTER = 12000  # 真章超过这个长度 → 再按 6000 字细分并打「·续N」
CHAP_HEAD = re.compile(
    r"(第[0-9零一二三四五六七八九十百千两]+[章节回]" + NOT_CHAPTER_AFTER + r"|第[0-9零一二三四五六七八九十百千两]+卷)"
    r"(.*)$"
)
# 「第N卷」= 分卷标记；卷内章号各自从 1 开始，排序时必须先看卷号
VOL_RE = re.compile(r"第[0-9零一二三四五六七八九十百千两]+卷")
MIN_BODY = 200        # 任何一节正文短于这个字数 → 视为目录行/章尾注，并入相邻节
MAX_SPLIT = 8         # 一个真章最多细分几节；超出说明「这一章」其实是多章合体
GAP_MIN_COVER = 0.55  # 章标记覆盖的正文比例 ≥ 此值 → 部分采用（洞里的正文按字数切）
# 章标记行里出现这些词，说明那是正文句而不是标题：
#   「第三回的时候他忍不住了」「第四回的时候嘴角溢出一条白的」
TITLE_JUNK = re.compile(r"的时候|之后|以前|忍不住|起来了|却发现|才知道|[的了着过]了$|[，,、]$")
# 题材关键词 → 标签
TROPE_HINTS = {
    "双修": "双修", "调教": "调教", "绿帽": "NTR", "ntr": "NTR", "NTR": "NTR",
    "后宫": "后宫", "母女": "母女", "师生": "师生", "姐弟": "姐弟", "兄妹": "兄妹",
    "催眠": "催眠", "药": "春药", "触手": "触手", "兽": "兽交", "淫纹": "淫纹",
    "契约": "契约", "奴隶": "奴役", "足交": "足交", "口交": "口交", "肛": "肛交",
    "三飞": "三人行", "双飞": "三人行", "群交": "群交", "轮奸": "轮奸",
    "足": "恋足", "丝袜": "丝袜", "旗袍": "制服", "护士": "制服", "教师": "制服",
    "女神": "女神", "女帝": "女帝", "圣洁": "堕落", "纯爱": "纯爱",
}


def load_text(p: Path) -> str:
    raw = p.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("gb18030", "replace")


def parse_name(p: Path) -> dict:
    """从文件名解析书名与后缀标签。"""
    stem = p.stem
    m = re.match(r"^《(.+?)》(.*)$", stem)
    if m:
        title, rest = m.group(1), m.group(2)
    else:
        title, rest = stem, ""

    suffix = []
    for part in rest.split("-"):
        part = part.strip()
        if part:
            suffix.append(part)

    status = "完"
    if any("合集" in s for s in suffix) or "合集" in title:
        status = "合集"
    if any("未完" in s or "连载" in s for s in suffix):
        status = "未完"

    # 书名里带（字数）或（作者）的括号补充
    sub = None
    bm = re.search(r"[（(]([^）)]{1,20})[）)]$", title)
    if bm:
        sub = bm.group(1)
        title = title[: bm.start()].strip()

    return {"title": title.strip(), "subtitle": sub, "status": status, "suffix": suffix}


def guess_author(text: str) -> tuple[str | None, str | None]:
    head = text[:3000]
    m = re.search(r"作\s*者\s*[:：]?\s*([^\s\r\n，。、]{2,12})", head)
    if m:
        return m.group(1), None
    m = re.search(r"(?:by|BY)\s*[:：]?\s*([A-Za-z0-9_\u4e00-\u9fff]{2,16})", head)
    if m:
        return m.group(1), None
    return None, "佚名（原文未标注）"


def split_long(seg: str, target: int) -> list[str]:
    """超长段落按句末标点切。"""
    parts = re.split(r"(?<=[。！？…」』])", seg)
    out, buf = [], ""
    for s in parts:
        if len(buf) + len(s) > target and buf:
            out.append(buf)
            buf = s
        else:
            buf += s
    if buf:
        out.append(buf)
    return out


def split_title(line: str) -> tuple[str, str]:
    """把「第61章升魂丹翌日清晨，阳光……」这样粘连的一行拆成 (标题, 还给正文的余下部分)。

    标题最多取到第一个标点或 24 个字，剩下的必须回到正文，
    否则正文章节会凭空少掉一段。
    """
    m = re.match(
        r"(第[0-9零一二三四五六七八九十百千两]+[章节回卷][：:、.．\s]*"
        r"|序章[：:、\s]*|楔子[：:、\s]*|序言[：:、\s]*|前言[：:、\s]*"
        r"|后记[：:、\s]*|尾声[：:、\s]*|终章[：:、\s]*|番外[：:、\s]*)",
        line,
    )
    head = m.group(1) if m else ""
    tail = line[len(head):].strip() if head else line.strip()
    if not tail:
        return line.strip(), ""
    cut = re.search(r"[。！？；，、]", tail)
    if cut:
        t = tail[: cut.start()].strip()
        rest = tail[cut.start():].strip()
    elif len(tail) > 24:
        t, rest = tail[:24].strip(), tail[24:].strip()
    else:
        t, rest = tail.strip(), ""
    # 「第三回的时候他忍不住了」这类是正文句被行首截断当成标题 —— 退回正文
    if TITLE_JUNK.search(t) or len(t) > 30:
        return "", line.strip()
    return (head + t).strip(), rest


CN_DIGIT = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNIT = {"十": 10, "百": 100, "千": 1000}


def chap_no(title: str) -> int | None:
    """从「第十二章xxx」里取章号；取不到返回 None。"""
    m = CHAP_HEAD.match(title or "")
    if not m:
        return None
    num = m.group(1)[1:-1]          # 去掉开头「第」和结尾「章」
    if num.isdigit():
        return int(num)
    total, cur = 0, 0
    for ch in num:
        if ch in CN_DIGIT:
            cur = CN_DIGIT[ch]
        elif ch in CN_UNIT:
            total += (cur or 1) * CN_UNIT[ch]
            cur = 0
        else:
            return None
    return total + cur


def regressions(nos: list[int | None]) -> int:
    """章号序列里「后一个比前一个小」的次数。"""
    return sum(1 for a, b in zip(nos, nos[1:])
               if a is not None and b is not None and b < a)


def base_title(t: str) -> str:
    """去掉 split_long 追加的「·续N」后缀 —— 它不改变所属章号。"""
    return re.sub(r"·续\d+$", "", t or "")


def order_by_chapter(chunks: list[tuple[str, int, str]]) -> list[tuple[str, int, str]]:
    """只在「排序确实能修好顺序」时排序，其余一律保持原文顺序。

    护栏（都踩过坑才加）：
    1) 出现「第N卷」→ 原文是分卷结构，每卷章号各自从 1 开始，排序会把各卷
       的同号章交错拼在一起（《诛仙之青云淫徒》曾因此被搅成六本）。
    2) 本来就没有回退 → 不需要动。
    3) 试排之后仍然有回退（如「第三回」这类非章标记混入、或两套序列并存）
       → 说明章号不可信，放弃排序、保持原文顺序。
    只有「排序能把回退清零」才是真的需要且可以修的情形。
    """
    nos = [chap_no(base_title(t)) if r else None for t, r, _ in chunks]
    known = [n for n in nos if n]
    if len(known) < 3:
        return chunks
    if any(VOL_RE.search(t) for t, _, _ in chunks):
        return chunks                # 分卷结构，原文顺序即正确
    if regressions(nos) == 0:
        return chunks                # 已经有序
    idx = sorted(range(len(chunks)), key=lambda i: _sort_key(nos, chunks, i))
    if regressions([nos[i] for i in idx]) > 0:
        return chunks                # 排了也修不好，说明章号本身不可信
    return [chunks[i] for i in idx]


PRE_HEAD = re.compile(r"开篇|序章|楔子|前言|序言|引子")
POST_HEAD = re.compile(r"后记|尾声|终章|番外|完本")


def _sort_key(nos, chunks, i):
    """开篇类排最前、后记类排最后，无章号的居中靠后。"""
    n = nos[i]
    t = chunks[i][0] or ""
    if n is None:
        if PRE_HEAD.search(t):
            return (-2, 0, i)
        if POST_HEAD.search(t):
            return (10 ** 9, 0, i)
        return (10 ** 8, 0, i)
    return (0, n, i)


def compact_short(chunks: list[tuple[str, int, str]]) -> list[tuple[str, int, str]]:
    """把过短的「章节」（目录行、章尾注如「第二章结束」）并进相邻节。

    这类节的内容通常只有十几到几十个字，单独成节会让目录出现一堆空壳。
    并进下一节开头；若是最后一节则接到上一节末尾。

    例外：「第N卷……」这类纯卷名行不丢，而是变成下一节标题的前缀
    （`第二卷天书和美人 · 第1章神秘美妇`），否则分卷结构就看不见了。
    """
    out: list[tuple[str, int, str]] = []
    carry = ""
    vol = ""
    last_no: int | None = None
    for title, is_real, body in chunks:
        if is_real and VOL_RE.search(title) and len(body) < MIN_BODY:
            vol = title.strip()
            # 卷名行本身不建节，但它脚下那点正文不能丢（实测 #443 每卷丢几十字）
            if body:
                carry += ("\n" + body) if carry else body
            continue                      # 卷名挂起，等下一节
        if len(body) < MIN_BODY:
            # 不分真假章节：硬切出来的空壳节同样该并掉
            carry += ("\n" + body) if carry else body
            continue
        if carry:
            body = carry + "\n" + body
            carry = ""
        no = chap_no(title) if is_real else None
        if vol and no is not None and last_no is not None and no < last_no:
            # 章号回退 → 已进入下一卷，但卷名行还没出现（原文常把卷名
            # 放在该卷第一章之后），此时不硬标上一卷的名字
            vol = ""
        if vol and not title.startswith(vol):
            # 标题本身已带卷名时不重复叠加（实测 #189
            # 「第五卷、三大龙王驭龙皇 · 第五卷、三大龙王驭龙皇」）
            title = f"{vol} · {title}" if title else vol
            # 卷名不在此清空：同一卷内的后续章节继续带前缀，
            # 直到出现下一个「第N卷」行（原文常有卷名行重复，自然无害）
        if no is not None:
            last_no = no
        out.append((title, is_real, body))
    if carry:
        if out:
            t, r, b = out[-1]
            out[-1] = (t, r, b + "\n" + carry)
        else:
            out.append(("正文", 0, carry))
    return out


def split_real(title: str, body: str, target: int) -> list[tuple[str, int, str]]:
    """真章过长时细分。续节标题带「（i/n）」，让目录能看出同属一章。

    一个章被切出超过 MAX_SPLIT 节，说明原文这一「章」其实是多章合体
    （实测 #220 第12章切出 17 节，每节 5000+ 字）—— 那样按章读已经无意义，
    仍保留标题但标明序号，读者至少知道自己在第几段。
    """
    if len(body) <= MAX_REAL_CHAPTER:
        return [(title, 1, body)]
    parts = split_long(body, target)
    n = len(parts)
    if n <= 1:
        return [(title, 1, body)]
    if n > MAX_SPLIT:
        return [(f"{title}（{i + 1}/{n}）", 1, p) for i, p in enumerate(parts)]
    return [(title if i == 0 else f"{title}（{i + 1}/{n}）", 1, p) for i, p in enumerate(parts)]


def split_chapters(text: str, target: int = 6000) -> list[tuple[str, int, str]]:
    """返回 [(title, is_real, content)]。

    三段式判定：
    1) 标记完整（complete）→ 全部按原文真标题切
    2) 标记只覆盖一部分（partial）→ 有标记处用真标题，洞里的正文按字数切，
       插回原来的位置（实测 #185 有 49 处行首「第N章」却因一处大洞被整本否掉）
    3) 标记不足 → 全按字数切，但**行首的章标记仍然认**，不再被吞进上一节
       （实测 #303 第2节末尾吊着「第58章生命重塑与深泉极乐（下）」）
    """
    marks = list(CHAPTER_RE.finditer(text))
    if len(marks) >= 3:
        gaps = [marks[i + 1].start() - marks[i].end() for i in range(len(marks) - 1)]
        body_len = len(text) - marks[0].end()
        avg = body_len / len(marks)
        med = sorted(gaps)[len(gaps) // 2] if gaps else 0
        complete = avg <= MIN_AVG and (not gaps or max(gaps) <= max(GAP_RATIO * med, GAP_ABS))
        covered = sum(
            (marks[i + 1].start() if i + 1 < len(marks) else len(text)) - marks[i].end()
            for i in range(len(marks))
        )
        # 平均章长必须仍像「章」（≤ MIN_AVG），否则说明那些标记是卷级的：
        # 实测 #303 有 20 个标记、138 万字，平均 6.9 万字，覆盖虽满但不是章
        partial = (
            (not complete)
            and avg <= MIN_AVG
            and covered / max(1, body_len) >= GAP_MIN_COVER
        )
        if complete or partial:
            out: list[tuple[str, int, str]] = []
            # 第一个章标记之前的内容（卷首语、简介、残缺前言）不能丢
            pre = text[: marks[0].start()].strip()
            if len(pre) > 80:
                if len(pre) <= MAX_REAL_CHAPTER:
                    out.append(("开篇", 0, pre))
                else:
                    parts = split_long(pre, target)
                    n = len(parts)
                    for k, part in enumerate(parts):
                        t = "开篇" if n == 1 else f"开篇（{k + 1}/{n}）"
                        out.append((t, 0, part))
            for i, m in enumerate(marks):
                start = m.end()
                end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
                raw_line = m.group(0).strip()
                body = text[start:end]
                # 标题可能和正文粘在一行，split_title 会把多余部分还给正文
                title, rest = split_title(raw_line)
                if not title:
                    # 「第三回的时候他忍不住了…」这类正文句：整行连同这一章的正文
                    # 一起挂到上一节末尾，不新建章。**必须把 text[start:end] 一并带上**
                    # —— 否则这一整章的正文被 continue 吃掉（实测 #220 丢 5.8 万字）。
                    junk = (raw_line + "\n" + text[start:end]).strip()
                    if out:
                        t, r, b = out[-1]
                        out[-1] = (t, r, (b + "\n" + junk).strip())
                    else:
                        out.append(("开篇", 0, junk))
                    continue
                if rest:
                    body = rest + "\n" + body
                body = body.strip()
                if not body:
                    # 卷名行后面常常直接跟下一章标题，正文为空 —— 不能丢，
                    # 交给 compact_short 挂到下一节标题上
                    if VOL_RE.search(title):
                        out.append((title, 1, ""))
                    continue
                out.extend(split_real(title, body, target))
            if len(out) >= 3:
                return order_by_chapter(compact_short(out))

    return by_words(text, target)


def by_words(text: str, target: int = 6000) -> list[tuple[str, int, str]]:
    """按字数切；行首出现章标记时保留为节标题，不再被吞进上一节。"""
    chunks: list[tuple[str, int, str]] = []
    buf: list[str] = []
    size = 0
    idx = 0
    pending = ""

    def flush() -> None:
        nonlocal buf, size, idx, pending
        if not buf:
            pending = ""
            return
        body = "\n".join(buf).strip()
        if pending:
            t, rest = split_title(pending)
            if t:
                if rest:
                    body = rest + "\n" + body
                chunks.append((t, 1, body))
            else:
                idx += 1
                chunks.append((f"第{idx}节", 0, (rest + "\n" + body).strip() if rest else body))
            pending = ""
        else:
            idx += 1
            chunks.append((f"第{idx}节", 0, body))
        buf, size = [], 0

    for ln in text.split("\n"):
        s = ln.strip()
        if not s:
            continue
        if CHAPTER_RE.match(ln):
            flush()
            pending = s
            continue
        for piece in (split_long(s, target) if len(s) > target else [s]):
            if size + len(piece) > target and buf:
                flush()
            buf.append(piece)
            size += len(piece)
    flush()
    return compact_short(chunks)


TOKEN_RE = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z0-9]+")


def bigram_cn(text: str) -> str:
    """汉字 bigram + 拉丁数字词，用于 FTS。

    必须把「汉字串」与「字母数字串」分开取词，不能用一个字符类混着切：
    `[^\\u4e00-\\u9fffA-Za-z0-9]+` 会把「NTR情节」当成一整段（首字符不是汉字），
    结果输出 "ntr情节" 这种既不是 bigram 也不是词的 token —— 实测 22 章正文含
    NTR 却只有 3 章能搜到，其余 19 章全是这种粘连。

    单字不进索引（每章都存会让 token 数翻倍），查询侧用前缀 `乳*` 命中「乳房」等。
    """
    out = []
    for m in TOKEN_RE.finditer(text or ""):
        seg = m.group(0)
        if "\u4e00" <= seg[0] <= "\u9fff":
            n = len(seg)
            if n >= 2:
                out.extend(seg[i : i + 2] for i in range(n - 1))
        else:
            out.append(seg.lower())
    return " ".join(out)


def extract_tags(text: str, source_work: str | None) -> list[str]:
    tags = []
    if source_work:
        tags.append(source_work)
    low = text[:200000]
    for kw, tag in TROPE_HINTS.items():
        if tag in tags:
            continue
        if kw in low:
            tags.append(tag)
    # 词表类别粗判
    kind_hit = Counter()
    for w, k in LX.sex_terms.items():
        c = low.count(w)
        if c:
            kind_hit[k] += c
    if kind_hit.get("act", 0) > 50 and "调教" not in tags:
        tags.append("情色")
    return tags[:12]


NON_CHAR = {
    # 势力 / 地名 / 学院宗门
    "萧家", "魂族", "云岚宗", "迦南学院", "史莱克学院", "魔兽山脉", "七宝琉璃宗",
    "斗气大陆", "塔戈尔沙漠", "唐门", "昊天宗", "武魂殿", "蓝电霸王龙家族",
    # 等级 / 称号
    "斗者", "斗师", "斗王", "斗皇", "斗宗", "斗尊", "斗帝", "封号斗罗", "魂师",
    # 物什 / 概念
    "魂天帝", "冰帝", "雪帝", "银月", "橘子",
}


def extract_characters(text: str) -> list[tuple[str, int]]:
    """专名词表命中计数。只保留出现 ≥3 次的，排除势力/等级等非人物条目。"""
    hits = []
    for w in LX.guard:
        if w in NON_CHAR:
            continue
        c = text.count(w)
        if c >= 3:
            hits.append((w, c))
    hits.sort(key=lambda x: -x[1])
    return hits[:15]


def make_summary(text: str, limit: int = 220) -> str:
    body = re.sub(r"\s+", " ", text).strip()
    body = re.sub(r"^.*?内容简介[:：]?", "", body)
    return body[:limit].strip()


def slugify(rel: Path) -> str:
    s = str(rel.with_suffix("")).replace("\\", "/")
    s = re.sub(r"[^\w\u4e00-\u9fff/-]+", "_", s)
    return s.strip("_").lower()


# ---------- 主流程 ----------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if args.rebuild and DB_PATH.exists():
        DB_PATH.unlink()

    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.commit()

    files = sorted(BASE.rglob("*.txt"))
    print(f"发现 {len(files)} 个文件，数据库 {DB_PATH}")

    t0 = time.time()
    added = skipped = 0
    total_chars = total_chapters = 0

    for i, p in enumerate(files, 1):
        rel = p.relative_to(BASE)
        slug = slugify(rel)
        if con.execute("SELECT 1 FROM works WHERE slug=?", (slug,)).fetchone():
            skipped += 1
            continue

        text = load_text(p)
        if not text.strip():
            continue

        info = parse_name(p)
        folder = rel.parts[0] if len(rel.parts) > 1 else ""
        source_work = SOURCE_MAP.get(folder)
        genre = "同人" if source_work else ("短篇集" if len(text) < 6000 else "原创")

        author, author_note = guess_author(text)
        chapters = split_chapters(text)
        chars = [c for c in extract_characters(text)]
        tags = extract_tags(text, source_work)
        summary = make_summary(text)

        # 原文 / 校对版路径（按同名推测）
        proof = ROOT / "校对后文章" / rel
        src_guess = ROOT / "原文" / folder / p.name

        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()

        cur = con.execute(
            """INSERT INTO works
               (slug,title,subtitle,author,author_note,genre,source_work,series,tags,
                keywords,summary,description,notes,rating,status,char_count,chapter_count,
                reading_minutes,path_canon,path_proof,path_source,sha256,imported_from)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                slug, info["title"], info["subtitle"], author, author_note, genre,
                source_work, None, json.dumps(tags, ensure_ascii=False),
                json.dumps([w for w, _ in chars[:8]], ensure_ascii=False),
                summary, None, None, "成人向", info["status"], len(text),
                len(chapters), max(1, len(text) // 500),
                str(rel).replace("\\", "/"),
                str(proof.relative_to(ROOT)).replace("\\", "/") if proof.exists() else None,
                str(src_guess.relative_to(ROOT)).replace("\\", "/") if src_guess.exists() else None,
                sha, "build_db.py",
            ),
        )
        wid = cur.lastrowid

        con.executemany(
            "INSERT INTO chapters (work_id,idx,title,is_real_title,content,body_bi,char_count)"
            " VALUES (?,?,?,?,?,?,?)",
            [
                (wid, n, title, real, body, bigram_cn(body), len(body))
                for n, (title, real, body) in enumerate(chapters, 1)
            ],
        )
        con.execute(
            "INSERT INTO chapters_fts (rowid,title,body_bi,work_title) "
            "SELECT id, title, body_bi, ? FROM chapters WHERE work_id=?",
            (info["title"], wid),
        )

        for rank, (name, cnt) in enumerate(chars):
            role = "主角" if rank < 3 and cnt > 20 else ("配角" if cnt > 20 else "提及")
            con.execute(
                "INSERT OR IGNORE INTO characters (work_id,name,role,mentions) VALUES (?,?,?,?)",
                (wid, name, role, cnt),
            )

        for t in tags:
            con.execute("INSERT OR IGNORE INTO tags (name,kind) VALUES (?,?)", (t, "auto"))
            con.execute("UPDATE tags SET count=count+1 WHERE name=?", (t,))
            tid = con.execute("SELECT id FROM tags WHERE name=?", (t,)).fetchone()[0]
            con.execute("INSERT OR IGNORE INTO work_tags (work_id,tag_id) VALUES (?,?)", (wid, tid))

        # 指纹：供未来新章节归入
        for kind, val in (("title", info["title"]), ("filename", p.name), ("sha256", sha)):
            con.execute(
                "INSERT OR IGNORE INTO fingerprints (work_id,kind,value) VALUES (?,?,?)",
                (wid, kind, val),
            )
        opening = re.sub(r"\s+", "", text[:60])
        if opening:
            con.execute(
                "INSERT OR IGNORE INTO fingerprints (work_id,kind,value) VALUES (?,?,?)",
                (wid, "opening", opening),
            )

        added += 1
        total_chars += len(text)
        total_chapters += len(chapters)
        if i % 50 == 0:
            con.commit()
            done = len(text)
            print(f"  [{i}/{len(files)}] {added} added, {time.time()-t0:.0f}s")

    con.commit()
    # FTS 优化
    con.execute("INSERT INTO chapters_fts(chapters_fts) VALUES('optimize')")
    con.commit()

    n_works = con.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    n_ch = con.execute("SELECT COUNT(*) FROM chapters").fetchone()[0]
    n_char = con.execute("SELECT SUM(char_count) FROM works").fetchone()[0] or 0
    size = DB_PATH.stat().st_size / 1024 / 1024
    print(f"\n完成：新增 {added}，跳过 {skipped}")
    print(f"库内：{n_works} 作品 / {n_ch} 章节 / {n_char:,} 字符")
    print(f"数据库：{DB_PATH}  {size:.0f} MB  用时 {time.time()-t0:.0f}s")
    con.close()


if __name__ == "__main__":
    main()
