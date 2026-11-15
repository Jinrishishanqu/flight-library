#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新章节归户：判断一段文本属于库里哪部作品，并可按需追加为补充章节。

判定顺序（与 文档/阅读站说明.md 一致，逐级加权，不满足就降级）：
  1. sha256 全文相同            -> 直接定案
  2. 开篇 200 字 sha256 相同    -> 直接定案
  3. 书名归一后完全匹配         -> 强候选
  4. 专名共现 Jaccard           -> 打分
  5. 全文 bigram 余弦近似        -> 兜底

用法：
  python import_chapter.py 新章.txt                 # 只诊断，打印候选
  python import_chapter.py 新章.txt --apply         # 归户并追加章节
  python import_chapter.py 目录/ --apply --min-score 6
  python import_chapter.py 新章.txt --work-id 12 --apply   # 指定作品，跳过匹配

--apply 的行为：
  按 split_chapters() 切分（有 >=3 处「第N章」就用真标题），
  追加到该作品 max(idx) 之后，重建 body_bi，更新计数，写 import_log。
  不覆盖、不删除任何已有章节。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DB = HERE / "data" / "library.db"
LEX = ROOT / "采集工具" / "词库" / "guard.txt"

CHAPTER_RE = re.compile(r"第[0-9零一二三四五六七八九十百千两]+[章节回]")


# ---------- 文本处理 ----------

def read_text(p: Path) -> str:
    raw = p.open("rb").read()
    for enc in ("utf-8", "gb18030", "utf-16"):
        try:
            return raw.decode(enc).replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace").replace("\r\n", "\n")


def bigram_cn(text: str) -> str:
    out = []
    for seg in re.split(r"[^\u4e00-\u9fff]+", text):
        n = len(seg)
        if n < 2:
            continue
        out.extend(seg[i:i + 2] for i in range(n - 1))
    return " ".join(out)


def split_long(seg: str, target: int) -> list[str]:
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


def split_chapters(text: str, target: int = 6000) -> list[tuple[str, int, str]]:
    marks = list(CHAPTER_RE.finditer(text))
    if len(marks) >= 3:
        chunks = []
        for i, m in enumerate(marks):
            start = m.end()
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            body = text[start:end].strip()
            if body:
                chunks.append((m.group(0).strip(), 1, body))
        if len(chunks) >= 3:
            return chunks

    chunks, buf, size, idx = [], [], 0, 0
    for ln in text.split("\n"):
        s = ln.strip()
        if not s:
            continue
        pieces = split_long(s, target) if len(s) > target else [s]
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


def parse_name(p: Path) -> dict:
    """从文件名抽书名/副标题。"""
    stem = p.stem
    m = re.match(r"《([^》]+)》\s*(.*)", stem)
    if m:
        title, rest = m.group(1).strip(), m.group(2).strip()
    else:
        title, rest = stem, ""
    rest = re.sub(r"-?全篇-?|-?合集-?|\d+(?:\.\d+)?[wW万]字?|\d+字", "", rest).strip("-_ ")
    return {"title": title, "subtitle": rest or None}


def norm_title(s: str) -> str:
    s = re.sub(r"[《》〈〉“”\"'《》\s\-_—–·、,，.。:：;；!！?？()（）\[\]【】]", "", s or "")
    return s.lower()


def opening_hash(text: str, n: int = 200) -> str:
    body = re.sub(r"\s+", "", text)[:n]
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_guard() -> list[str]:
    if not LEX.exists():
        return []
    words = [ln.strip() for ln in LEX.read_text("utf-8").splitlines()]
    return [w for w in words if w and not w.startswith("#")]


# ---------- 匹配 ----------

def db():
    if not DB.exists():
        sys.exit(f"数据库不存在：{DB}\n先跑 build_db.py --rebuild")
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def find_candidates(conn, path: Path, text: str, guard: list[str]) -> list[dict]:
    cands: dict[int, dict] = {}
    sha = sha256_text(text)
    op = opening_hash(text)
    meta = parse_name(path)
    ntitle = norm_title(meta["title"])

    def bump(wid: int, score: float, why: str):
        c = cands.setdefault(wid, {"work_id": wid, "score": 0.0, "why": []})
        c["score"] += score
        c["why"].append(why)

    # 1) sha256 全文
    for r in conn.execute("SELECT id, title FROM works WHERE sha256=?", (sha,)):
        bump(r["id"], 100.0, "sha256 全文相同")

    # 2) 开篇指纹
    for r in conn.execute(
        "SELECT work_id, title FROM fingerprints f JOIN works w ON w.id=f.work_id"
        " WHERE f.kind='opening' AND f.value=?", (op,)):
        bump(r["work_id"], 90.0, "开篇 200 字相同")

    # 3) 书名归一匹配
    for r in conn.execute("SELECT id, title FROM works"):
        if ntitle and norm_title(r["title"]) == ntitle:
            bump(r["id"], 20.0, f"书名完全匹配《{r['title']}》")
        elif ntitle and (ntitle in norm_title(r["title"]) or norm_title(r["title"]) in ntitle):
            if min(len(ntitle), len(norm_title(r["title"]))) >= 4:
                bump(r["id"], 8.0, f"书名包含《{r['title']}》")

    # 4) 专名共现
    txt_hits = {w: text.count(w) for w in guard if len(w) >= 2 and w in text}
    txt_hits = {w: c for w, c in txt_hits.items() if c}
    if txt_hits:
        rows = conn.execute(
            "SELECT work_id, name, mentions FROM characters WHERE mentions>=3").fetchall()
        by_work: dict[int, set[str]] = {}
        for r in rows:
            by_work.setdefault(r["work_id"], set()).add(r["name"])
        mine = set(txt_hits)
        pool = [(wid, names) for wid, names in by_work.items() if names]
        # 只在书名/指纹已有候选里算，避免全库 486 次集合运算太散
        focus = set(cands) if cands else {wid for wid, _ in pool}
        for wid, names in pool:
            if wid not in focus:
                continue
            inter = mine & names
            if not inter:
                continue
            jac = len(inter) / len(mine | names)
            bump(wid, 10.0 * jac, f"角色共现 {len(inter)} 个（{','.join(sorted(inter)[:4])}）")

    # 5) bigram 余弦（仅当上面都没结果时用，代价高）
    if not cands:
        q = Counter(bigram_cn(text).split())
        if q:
            qn = sum(v * v for v in q.values()) ** 0.5
            best = []
            for r in conn.execute(
                "SELECT id, title, char_count FROM works"
                " WHERE char_count>0 ORDER BY abs(char_count-?) LIMIT 40",
                (len(text),)):
                sample = conn.execute(
                    "SELECT body_bi FROM chapters WHERE work_id=? LIMIT 8", (r["id"],)
                ).fetchall()
                doc = Counter()
                for s in sample:
                    doc.update(s["body_bi"].split())
                if not doc:
                    continue
                dn = sum(v * v for v in doc.values()) ** 0.5
                dot = sum(min(q[w], doc[w]) for w in q.keys() & doc.keys())
                cos = dot / (qn * dn) if qn and dn else 0
                if cos > 0.05:
                    best.append((cos, r["id"], r["title"]))
            for cos, wid, title in sorted(best, reverse=True)[:3]:
                bump(wid, 20.0 * cos, f"bigram 余弦 {cos:.3f}")

    out = sorted(cands.values(), key=lambda c: -c["score"])
    for c in out:
        r = conn.execute("SELECT id,title,author,source_work,char_count,chapter_count"
                         " FROM works WHERE id=?", (c["work_id"],)).fetchone()
        c["title"] = r["title"]
        c["author"] = r["author"]
        c["source_work"] = r["source_work"]
        c["char_count"] = r["char_count"]
        c["chapter_count"] = r["chapter_count"]
    return out


# ---------- 写入 ----------

def apply_to_work(conn, work_id: int, path: Path, text: str, chunks) -> dict:
    row = conn.execute("SELECT MAX(idx) m FROM chapters WHERE work_id=?", (work_id,)).fetchone()
    base = row["m"] or 0

    # 过短尾节并入前一节，避免出现 100 来字的孤立小节
    merged: list[list] = []
    for title, is_real, body in chunks:
        if merged and len(body) < 400 and not is_real and not merged[-1][1]:
            merged[-1][2] += "\n" + body
            merged[-1][0] = f"{merged[-1][0]}"  # 标题沿用前一节
        else:
            merged.append([title, is_real, body])

    added = 0
    for i, (title, is_real, body) in enumerate(merged, start=1):
        # 自动切的假标题要接续全书的节号，否则会出现两个「第1节」
        if not is_real and re.fullmatch(r"第\d+节", title):
            title = f"第{base + i}节"
        conn.execute(
            "INSERT INTO chapters (work_id, idx, title, is_real_title, content, body_bi, char_count)"
            " VALUES (?,?,?,?,?,?,?)",
            (work_id, base + i, title, is_real, body, bigram_cn(body), len(body)))
        added += 1

    conn.execute("""UPDATE works SET
        char_count    = (SELECT COALESCE(SUM(char_count),0) FROM chapters WHERE work_id=?),
        chapter_count = (SELECT COUNT(*) FROM chapters WHERE work_id=?),
        reading_minutes = (SELECT COALESCE(SUM(char_count),0)/450 FROM chapters WHERE work_id=?),
        updated_at = datetime('now')
        WHERE id=?""", (work_id, work_id, work_id, work_id))

    conn.execute("INSERT OR IGNORE INTO fingerprints (work_id, kind, value, extra)"
                 " VALUES (?,?,?,?)",
                 (work_id, "sha256", sha256_text(text), str(path)))
    conn.execute("INSERT OR IGNORE INTO fingerprints (work_id, kind, value, extra)"
                 " VALUES (?,?,?,?)",
                 (work_id, "opening", opening_hash(text), str(path)))
    conn.execute("INSERT OR IGNORE INTO fingerprints (work_id, kind, value, extra)"
                 " VALUES (?,?,?,?)",
                 (work_id, "filename", path.name, str(path)))
    conn.execute("INSERT INTO import_log (action, path, work_id, detail) VALUES (?,?,?,?)",
                 ("append_chapter", str(path), work_id,
                  json.dumps({"added": added, "chars": len(text)}, ensure_ascii=False)))
    conn.commit()
    return {"added": added, "base_idx": base}


# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="txt 文件或目录")
    ap.add_argument("--apply", action="store_true", help="写入数据库")
    ap.add_argument("--work-id", type=int, default=None, help="指定作品，跳过匹配")
    ap.add_argument("--min-score", type=float, default=6.0, help="自动归户的最低分")
    ap.add_argument("--top", type=int, default=5)
    args = ap.parse_args()

    p = Path(args.target)
    files = sorted(p.rglob("*.txt")) if p.is_dir() else [p]
    if not files:
        sys.exit("没有找到 txt")

    conn = db()
    guard = load_guard()
    total = {"files": 0, "applied": 0, "skipped": 0}

    for f in files:
        text = read_text(f)
        if len(text.strip()) < 200:
            print(f"[跳过] {f.name} 太短（{len(text)} 字）")
            total["skipped"] += 1
            continue
        total["files"] += 1
        print(f"\n=== {f.name}  {len(text):,} 字 ===")

        if args.work_id:
            wid = args.work_id
            r = conn.execute("SELECT title FROM works WHERE id=?", (wid,)).fetchone()
            if not r:
                print(f"[跳过] work_id={wid} 不存在")
                total["skipped"] += 1
                continue
            print(f"→ 指定靶标：#{wid}《{r['title']}》")
            chunks = split_chapters(text)
            if args.apply:
                got = apply_to_work(conn, wid, f, text, chunks)
                print(f"[已写入] 追加 {got['added']} 节，起始 idx={got['base_idx']+1}")
                total["applied"] += 1
            else:
                print(f"[预览] 将追加 {len(chunks)} 节：{[c[0] for c in chunks[:6]]}"
                      f"{' …' if len(chunks) > 6 else ''}")
            continue

        cands = find_candidates(conn, f, text, guard)
        if not cands:
            print("→ 无候选，可能是新作品；放进 校勘版\\ 后用 build_db.py 增量导入")
            total["skipped"] += 1
            continue
        for i, c in enumerate(cands[:args.top], 1):
            print(f"  {i}. #{c['work_id']:<4} 《{c['title']}》"
                  f"  {c['char_count']:,}字/{c['chapter_count']}节"
                  f"  分数 {c['score']:.1f}")
            for w in c["why"]:
                print(f"       · {w}")

        best = cands[0]
        if args.apply:
            if best["score"] < args.min_score:
                print(f"[跳过] 最高分 {best['score']:.1f} < 阈值 {args.min_score}，人工确认后加 --work-id")
                total["skipped"] += 1
                continue
            chunks = split_chapters(text)
            got = apply_to_work(conn, best["work_id"], f, text, chunks)
            print(f"[已写入] → #{best['work_id']}《{best['title']}》"
                  f" 追加 {got['added']} 节，起始 idx={got['base_idx']+1}")
            total["applied"] += 1
        else:
            print(f"→ 建议归入 #{best['work_id']}《{best['title']}》"
                  f"（{best['score']:.1f} 分）；确认后加 --apply")

    print(f"\n合计：{total['files']} 个文件，写入 {total['applied']}，未写入 {total['skipped']}")
    conn.close()


if __name__ == "__main__":
    main()
