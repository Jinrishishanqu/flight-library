# -*- coding: utf-8 -*-
"""为 AI 摘要准备素材包：每部作品一个 .txt，供 agent 读取。

输出目录：采集工具\\书库\\data\\bio_in\\<work_id>.txt
内容结构：
    # 作品
    书名 / 原作 / 字数 / 节数 / 现有标签
    ## 开头片段（前 1200 字，去掉换行）
    ## 角色素材
    ### 名字（性别 / 提及次数 / 首现节）
    - 若干条含该名字的代表句（去重、限长）
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"
OUT = HERE / "data" / "bio_in"

SENT_SPLIT = re.compile(r"(?<=[。！？…」』])")
SEX_HINT = re.compile(
    r"肉棒|龟头|精液|射精|小穴|肉穴|淫穴|蜜穴|花穴|穴口|淫水|爱液|高潮|泄身|呻吟|娇喘|"
    r"抽插|抽送|插进|挺进|顶进|撞击|舔|吸吮|乳头|乳尖|阴蒂|阴唇|阴道|后庭|菊门|破处|"
    r"处女|初夜|敏感|淫荡|口交|肛交|足交|调教|捆绑|春药|发情|欲火|痉挛|夹紧|摩擦|揉搓"
)


def main() -> int:
    only = None
    if "--limit" in sys.argv:
        pass
    ids = None
    if "--ids" in sys.argv:
        ids = {int(x) for x in sys.argv[sys.argv.index("--ids") + 1].split(",")}
    maxw = 60
    if "--max" in sys.argv:
        maxw = int(sys.argv[sys.argv.index("--max") + 1])
    # 只给「还没有 bio」的角色出素材（角色集重建后补写用）
    only_missing = "--only-missing" in sys.argv

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    OUT.mkdir(parents=True, exist_ok=True)

    if only_missing:
        works = con.execute(
            "SELECT DISTINCT w.id,w.title,w.source_work,w.char_count,w.chapter_count,w.tags,w.summary "
            "FROM works w JOIN characters c ON c.work_id=w.id "
            "WHERE c.bio IS NULL OR c.bio='' ORDER BY w.char_count DESC"
        ).fetchall()
    else:
        works = con.execute(
            "SELECT id,title,source_work,char_count,chapter_count,tags,summary FROM works ORDER BY char_count DESC"
        ).fetchall()
    if ids:
        works = [w for w in works if w["id"] in ids]
    works = works[:maxw]

    n = 0
    for w in works:
        chs = con.execute(
            "SELECT idx,title,content FROM chapters WHERE work_id=? ORDER BY idx LIMIT 3", (w["id"],)
        ).fetchall()
        if not chs:
            continue
        opening = "\n".join(c["content"] for c in chs)
        opening = re.sub(r"\s+", "", opening)[:1200]

        chars = con.execute(
            "SELECT name,role,gender,mentions,first_chapter,bio FROM characters WHERE work_id=? "
            "ORDER BY mentions DESC", (w["id"],)
        ).fetchall()
        if only_missing:
            chars = [c for c in chars if not (c["bio"] or "").strip()]
        if not chars and "--all" not in sys.argv:
            continue

        lines = [
            "# 作品",
            f"书名：{w['title']}",
            f"原作：{w['source_work'] or '无'}",
            f"字数：{w['char_count']}  节数：{w['chapter_count']}",
            f"现有标签：{w['tags'] or ''}",
            "",
            "## 开头片段",
            opening,
            "",
            "## 角色素材",
        ]

        full = "\n".join(c["content"] for c in chs)
        allch = con.execute("SELECT content FROM chapters WHERE work_id=?", (w["id"],)).fetchall()
        full = "\n".join(r["content"] for r in allch)
        sents = [s.strip() for s in SENT_SPLIT.split(full) if s.strip()]

        for c in chars:
            nm = c["name"]
            got = []
            for s in sents:
                if nm not in s:
                    continue
                if len(s) < 12 or len(s) > 110:
                    continue
                if s.startswith("「") and s.count("「") > 1:
                    continue
                got.append(s)
                if len(got) >= 28:
                    break
            # 优先收性相关句与描写句
            sex = [s for s in got if SEX_HINT.search(s)]
            rest = [s for s in got if s not in sex]
            picked = sex[:8] + rest[:10]
            lines.append(f"### {nm}｜{c['role']}｜{c['gender']}｜提及{c['mentions']}次｜首现第{c['first_chapter']}节")
            for s in picked:
                lines.append(f"- {s}")
            lines.append("")

        fp = OUT / f"{w['id']}.txt"
        fp.write_text("\n".join(lines), encoding="utf-8")
        n += 1

    print(f"写出 {n} 个素材包 -> {OUT}")
    (OUT / "_index.json").write_text(
        json.dumps([{"id": w["id"], "title": w["title"], "chars": w["char_count"]} for w in works],
                   ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
