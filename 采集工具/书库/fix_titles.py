# -*- coding: utf-8 -*-
"""整理书名：去掉分卷序号前缀、合集篇数后缀、商业标记、残缺字数标注等。

用法：
    python fix_titles.py --dry     看前后对照
    python fix_titles.py --apply   写回 works.title（并重灌 FTS）
"""
import re, sqlite3, sys, io
from pathlib import Path

DB = Path(__file__).resolve().parent / "data" / "library.db"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 1) 商业/合集标记前缀（【】里的内容按白名单决定留还是丢）
BIZ_MARKS = {"客单展示", "约稿作品", "付费", "免费", "预览", "完结", "全本",
             "合集", "全篇", "番外", "短篇", "连载", "校对版", "精校版"}
P_MARK = re.compile(r"^【([^】]{1,20})】\s*")
P_PAREN_TAG = re.compile(
    r"^[（(]\s*(?:付费|免费|独立\s*[0-9一-十两]+\s*篇|纯爱短文\s*[0-9]+\s*篇|短篇\s*[0-9]+\s*篇)\s*[)）]\s*"
)
# 2) 分卷序号前缀：1~6 / 5- / 2- / 7～9
P_VOL_HEAD = re.compile(r"^[0-9]{1,3}\s*[-~～_—至]\s*[0-9]{0,3}\s*[-~～_—、.·:：]?\s*")
# 3) 紧跟的（斗1）（1）这类卷标记
P_PAREN_NUM = re.compile(r"^[（(][^（()）]{0,8}[0-9][^（()）]{0,6}[)）]\s*")
# 4) 尾部「-独立N篇」
CN_NUM = "0-9一二三四五六七八九十两"
P_INDEP = re.compile(r"\s*[-_—]?\s*独立\s*[" + CN_NUM + r"]+\s*篇\s*$")
P_INDEP_HEAD = re.compile(r"^独立\s*[" + CN_NUM + r"]+\s*篇\s*[-_—·]?\s*")
# 5) 残缺的字数标注（括号没闭合）：（6千5字，医仙
P_BROKEN_SIZE = re.compile(r"[（(][^（()）]{0,8}[0-9]\s*(?:千|万|k|K)?\s*字[^)）]*$")
# 6) 下划线之后的作者求支持话
P_AUTHOR_TALK = re.compile(r"_([^_]{6,})$")
AUTHOR_HINTS = ("各位", "老板", "支持一下", "动力", "订阅", "求订阅", "求票", "求打赏", "感谢", "购买支持", "点赞", "收藏")
# 7) 尾部孤立的分卷数字：…-2 / …38（>10 才认，避免吃掉「斗罗大陆2」）
P_TAIL_NUM = re.compile(r"[-_—]\s*([0-9]{1,3})\s*$")
P_TAIL_BARE = re.compile(r"(?<=[\u4e00-\u9fff])([0-9]{2,3})\s*$")
# 8) 尾部「N卷」
P_TAIL_VOL = re.compile(r"\s+([0-9]{1,3})\s*卷\s*$")
# 9) 中间夹的章节序号：… 时停系统 0894 美杜莎…
P_MID_NUM = re.compile(r"\s+[0-9]{3,4}\s+")


def strip_mark(s: str) -> str:
    """处理开头的【…】：商业标记丢掉，原作/角色名保留并降为前缀。"""
    m = P_MARK.match(s)
    if not m:
        return s
    inner = m.group(1).strip()
    rest = s[m.end():].strip()
    if inner in BIZ_MARKS or len(inner) <= 2 or not re.search(r"[\u4e00-\u9fff]", inner):
        return rest
    return inner + ("·" + rest if rest else "")


def clean_title(raw: str) -> str:
    s = (raw or "").strip()
    orig = s
    s = strip_mark(s)
    s = P_PAREN_TAG.sub("", s)
    s = P_VOL_HEAD.sub("", s)
    s = P_PAREN_NUM.sub("", s)
    s = P_INDEP_HEAD.sub("", s)
    s = P_INDEP.sub("", s)
    s = P_BROKEN_SIZE.sub("", s)
    m = P_AUTHOR_TALK.search(s)
    if m and any(h in m.group(1) for h in AUTHOR_HINTS):
        s = s[: m.start()]
    else:
        s = s.replace("_", "·")
    s = P_MID_NUM.sub("·", s)
    s = s.replace("丶", "·")
    m = P_TAIL_VOL.search(s)
    if m:
        s = s[: m.start()].strip()
    m = P_TAIL_NUM.search(s)
    if m and int(m.group(1)) > 10:
        s = s[: m.start()].strip()
    else:
        m = P_TAIL_BARE.search(s)
        if m:
            s = s[: m.start()].strip()
    s = re.sub(r"\s{2,}", " ", s).strip(" -_—·,，、")
    if s.startswith("之") and len(s) <= 6:
        s = s[1:].strip("·")
    if len(s) < 2:
        return orig
    return s


def main():
    apply = "--apply" in sys.argv
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT id,title FROM works ORDER BY id").fetchall()

    existing = {r["title"] for r in rows}
    plan, clash = [], []
    for r in rows:
        new = clean_title(r["title"])
        if new == r["title"]:
            continue
        if new in existing:
            # 撞名时保留原编号做区分：…（38）/ …（2篇）
            tail = re.search(r"([0-9]{1,3})\s*$", r["title"]) or re.search(r"独立\s*([0-9]+)\s*篇", r["title"])
            if tail:
                cand = f"{new}（{tail.group(1)}）"
                if cand not in existing:
                    plan.append((r["id"], r["title"], cand))
                    existing.add(cand)
                    continue
            clash.append((r["id"], r["title"], new))
            continue
        plan.append((r["id"], r["title"], new))

    print(f"会改名 {len(plan)} 部，因重名跳过 {len(clash)} 部\n")
    for wid, old, new in plan:
        print(f"  {wid:>4}  {old}")
        print(f"        -> {new}")
    if clash:
        print("\n重名跳过：")
        for wid, old, new in clash:
            print(f"  {wid:>4}  {old}   (清洗后为「{new}」，已存在同名书)")

    if not apply:
        print("\n（--dry：未写库）")
        con.close()
        return

    con.executemany("UPDATE works SET title=? WHERE id=?", [(n, i) for i, _, n in plan])
    con.commit()
    # 书名进了 FTS 的 work_title 列，必须重灌
    try:
        from build_db import bigram_cn
        con.execute("DROP TABLE IF EXISTS chapters_fts")
        con.execute(
            "CREATE VIRTUAL TABLE chapters_fts USING fts5("
            "title, body_bi, work_title, content='', tokenize='unicode61 remove_diacritics 0')"
        )
        fts = con.execute(
            "SELECT c.id, c.title, c.body_bi, w.title FROM chapters c JOIN works w ON w.id=c.work_id"
        ).fetchall()
        con.executemany(
            "INSERT INTO chapters_fts(rowid,title,body_bi,work_title) VALUES (?,?,?,?)",
            [(r[0], bigram_cn(r[1] or ""), r[2], bigram_cn(r[3] or "")) for r in fts],
        )
        con.execute("INSERT INTO chapters_fts(chapters_fts) VALUES('optimize')")
        con.commit()
        print(f"\n已写回 {len(plan)} 条，FTS 重灌 {len(fts)} 条")
    except Exception as e:
        print("FTS 重灌失败（不影响书名）:", e)
    con.close()


if __name__ == "__main__":
    main()
