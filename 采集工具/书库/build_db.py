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

CHAPTER_RE = re.compile(
    r"(?m)^[ \t]*(第[0-9零一二三四五六七八九十百千两]+[章节回卷]|序章|楔子|序言|前言|后记|尾声|终章|番外)"
    r"[^\r\n]{0,40}\r?$"
)

# 章节划分的判定阈值
MIN_AVG = 30000        # 平均每章超过这个字数 → 认为原文标记只覆盖局部，不采用
GAP_RATIO = 12.0       # 最大间隔超过中位间隔的这个倍数 → 判定标记断裂
GAP_ABS = 60000        # 无论如何，出现这么长的一段没有章标记，就认定标记不完整
MAX_REAL_CHAPTER = 12000  # 真章超过这个长度 → 再按 6000 字细分并打「·续N」
CHAP_HEAD = re.compile(r"(第[0-9零一二三四五六七八九十百千两]+[章节回卷])(.*)$")
MIN_BODY = 200        # 真章正文短于这个字数 → 视为目录行/章尾注，并入下一节
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


def order_by_chapter(chunks: list[tuple[str, int, str]]) -> list[tuple[str, int, str]]:
    """文件内章号乱序时按章号稳定排序；本来单调递增就原样返回。"""
    nos = [chap_no(t) if r else None for t, r, _ in chunks]
    known = [n for n in nos if n]
    if len(known) < 3:
        return chunks
    if all(a is None or b is None or a <= b for a, b in zip(nos, nos[1:])):
        return chunks                # 已经有序
    idx = sorted(range(len(chunks)), key=lambda i: (nos[i] is None, nos[i] or 0, i))
    return [chunks[i] for i in idx]


def compact_short(chunks: list[tuple[str, int, str]]) -> list[tuple[str, int, str]]:
    """把过短的「章节」（目录行、章尾注如「第二章结束」）并进相邻节。

    这类节的内容通常只有十几到几十个字，单独成节会让目录出现一堆空壳。
    并进下一节开头；若是最后一节则接到上一节末尾。
    """
    out: list[tuple[str, int, str]] = []
    carry = ""
    for title, is_real, body in chunks:
        if is_real and len(body) < MIN_BODY:
            carry += ("\n" + body) if carry else body
            continue
        if carry:
            body = carry + "\n" + body
            carry = ""
        out.append((title, is_real, body))
    if carry:
        if out:
            t, r, b = out[-1]
            out[-1] = (t, r, b + "\n" + carry)
        else:
            out.append(("正文", 0, carry))
    return out


def split_chapters(text: str, target: int = 6000) -> list[tuple[str, int, str]]:
    """返回 [(title, is_real, content)]。

    优先按原文自带的「第N章」等标记切分；只有当标记覆盖不完整
    （平均章长过大、或最大间隔远超中位间隔）时才退化为按字数切。
    """
    marks = list(CHAPTER_RE.finditer(text))
    if len(marks) >= 3:
        gaps = [marks[i + 1].start() - marks[i].end() for i in range(len(marks) - 1)]
        body_len = len(text) - marks[0].end()
        avg = body_len / len(marks)
        med = sorted(gaps)[len(gaps) // 2] if gaps else 0
        complete = avg <= MIN_AVG and (not gaps or max(gaps) <= max(GAP_RATIO * med, GAP_ABS))
        if complete:
            out: list[tuple[str, int, str]] = []
            # 第一个章标记之前的内容（卷首语、简介、残缺前言）不能丢
            pre = text[: marks[0].start()].strip()
            if len(pre) > 80:
                if len(pre) <= MAX_REAL_CHAPTER:
                    out.append(("开篇", 0, pre))
                else:
                    for k, part in enumerate(split_long(pre, target)):
                        out.append(("开篇" if k == 0 else f"开篇·续{k + 1}", 0, part))
            for i, m in enumerate(marks):
                start = m.end()
                end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
                raw_line = m.group(0).strip()
                body = text[start:end]
                # 标题可能和正文粘在一行，split_title 会把多余部分还给正文
                title, rest = split_title(raw_line)
                if rest:
                    body = rest + "\n" + body
                body = body.strip()
                if not body:
                    continue
                if len(body) <= MAX_REAL_CHAPTER:
                    out.append((title, 1, body))
                else:
                    for k, part in enumerate(split_long(body, target)):
                        t = title if k == 0 else f"{title}·续{k + 1}"
                        out.append((t, 1, part))
            if len(out) >= 3:
                return order_by_chapter(compact_short(out))

    lines = text.split("\n")
    chunks, buf, size, idx = [], [], 0, 0
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if len(s) > target:
            pieces = split_long(s, target)
        else:
            pieces = [s]
        for piece in pieces:
            if size + len(piece) > target and buf:
                idx += 1
                chunks.append((f"第{idx}节", 0, "\n".join(buf)))
                buf, size = [], 0
            buf.append(piece)
            size += len(piece)
    if buf:
        idx += 1
        chunks.append((f"第{idx}节", 0, "\n".join(buf)))
    return chunks


def bigram_cn(text: str) -> str:
    """汉字 bigram，用于 FTS。非汉字作分隔，避免标点组合污染索引。"""
    out = []
    for seg in re.split(r"[^\u4e00-\u9fff]+", text):
        n = len(seg)
        if n < 2:
            continue
        out.extend(seg[i : i + 2] for i in range(n - 1))
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
