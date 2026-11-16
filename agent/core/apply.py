# -*- coding: utf-8 -*-
"""AI 产物的入库层。

为什么单独一层：模型输出先落 `state/out/<stage>/`，入库是第二次独立动作。
这样 ①同一次生成可以反复 apply（调格式、补字段） ②出问题能分清是模型写错
还是入库写错 ③没配 API key 时也能把已有产物入进去。

三种产物对应三张表/一处差异：
  bio      → characters.bio（只填空值，不覆盖已有）
  summary  → works.summary_ai（覆盖）；tags 只在为空时写
  proof    → 文本报告，不回改正文（改正文要人看一眼）
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .config import Config


def _con(cfg: Config) -> sqlite3.Connection:
    """打开库。row_factory=Row 让结果能按列名取，别处代码依赖这一点。"""
    con = sqlite3.connect(cfg.paths.db)
    con.row_factory = sqlite3.Row
    return con


def apply_bio(cfg: Config, out_dir: Path, dry: bool = False) -> str:
    """把 state/out/bio/w<id>.json 里的角色小传写进 characters.bio。

    JSON 形状：{"work_id": 443, "items": [{"name": "张小凡", "bio": "..."}, ...]}
    三个刻意的约束：
      · `bio IS NULL OR bio=''` —— 只填空值。已有 bio 是花了很多 token 生成的，
        重复 apply 不该覆盖，也不该被更差的版本冲掉。
      · `len(bio) < 60` 视为无效 —— 模型偶尔只回一句「该角色信息不足」，
        这种写进库比不写更糟。
      · `(work_id, name)` 是 characters 的唯一键，所以按名字定位到具体那一行。
    """
    files = sorted(out_dir.glob("w*.json"))
    if not files:
        return "没有 bio 产物"
    n = miss = 0
    con = _con(cfg)
    try:
        for p in files:
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                # 单个文件坏了不影响其它文件；计数里体现出来方便回头查
                miss += 1
                continue
            wid = d.get("work_id")
            for it in d.get("items") or []:
                name = (it.get("name") or "").strip()
                bio = (it.get("bio") or "").strip()
                if not name or len(bio) < 60:
                    miss += 1
                    continue
                if dry:
                    n += 1
                    continue
                cur = con.execute(
                    "UPDATE characters SET bio=? , bio_at=datetime('now') "
                    "WHERE work_id=? AND name=? AND (bio IS NULL OR bio='')",
                    (bio, wid, name),
                )
                n += cur.rowcount      # rowcount=0 说明已有 bio，属正常跳过
        if not dry:
            con.commit()
    finally:
        con.close()
    return f"写入 bio {n} 条，跳过 {miss} 条" + ("（dry）" if dry else "")


def apply_summary(cfg: Config, out_dir: Path, dry: bool = False) -> str:
    """把 state/out/summary/w<id>.json 里的书籍简介写进 works.summary_ai。

    tags 的处理是有意保守的：库里现有标签来自脚本 + 人工整理，
    是有价值的资产；模型给的标签只在一处**全空**时才落进 tags，
    否则退到 keywords（模型标签更适合当检索词）。
    """
    files = sorted(out_dir.glob("w*.json"))
    if not files:
        return "没有 summary 产物"
    n = 0
    con = _con(cfg)
    try:
        for p in files:
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            wid = d.get("work_id")
            s = (d.get("summary") or "").strip()
            tags = d.get("tags") or []
            if not wid or len(s) < 60:
                continue
            if dry:
                n += 1
                continue
            con.execute("UPDATE works SET summary_ai=? WHERE id=?", (s, wid))
            # tags 只在为空时写：现有标签是脚本 + 人工整理的成果，不该被模型覆盖
            if tags:
                cur = con.execute(
                    "UPDATE works SET tags=? WHERE id=? AND (tags IS NULL OR tags='' OR tags='[]')",
                    (json.dumps(tags, ensure_ascii=False), wid))
                if cur.rowcount == 0:
                    # tags 已有内容 → 模型标签进 keywords，同样只在空时写
                    con.execute(
                        "UPDATE works SET keywords=? WHERE id=? AND "
                        "(keywords IS NULL OR keywords='')",
                        (",".join(tags), wid))
            n += 1
        if not dry:
            con.commit()
    finally:
        con.close()
    return f"写入简介 {n} 部" + ("（dry）" if dry else "")


def apply_proof(cfg, out_dir: Path, dry: bool = False) -> str:
    """文字复核只写报告，不回改正文 —— 改正文要人看一眼。

    产物是 state/reports/text_proof.tsv（六列：work_id / chapter_id / 标题 /
    原文 / 建议 / 理由），用 TSV 而不是写回库，是因为「模型说这里该改」只是
    候选，需要人逐条确认。以后要做自动回改，从这个报告读也方便。
    """
    files = sorted(out_dir.glob("c*.json"))
    rows = []
    for p in files:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for it in d.get("issues") or []:
            rows.append((d.get("work_id"), d.get("chapter_id"), d.get("title"),
                         it.get("before"), it.get("after"), it.get("why")))
    if not rows:
        return "没有复核报告"
    rpt = cfg.paths.state / "reports" / "text_proof.tsv"
    rpt.parent.mkdir(parents=True, exist_ok=True)
    if not dry:
        # newline="" 保证不把 \n 转成 \r\n —— TSV 的列分隔与行分隔必须原样
        with rpt.open("w", encoding="utf-8", newline="") as f:
            f.write("work_id\tchapter_id\t标题\t原文\t建议\t理由\n")
            for r in rows:
                f.write("\t".join(str(x or "") for x in r) + "\n")
    return f"{len(rows)} 处候选 → {rpt}" + ("（dry）" if dry else "")
