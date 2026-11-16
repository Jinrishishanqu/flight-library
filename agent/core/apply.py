# -*- coding: utf-8 -*-
"""AI 产物的入库层。

为什么单独一层：模型输出先落 `state/out/<stage>/`，入库是第二次独立动作。
这样 ①同一次生成可以反复 apply（调格式、补字段） ②出问题能分清是模型写错
还是入库写错 ③没配 API key 时也能把已有产物入进去。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .config import Config


def _con(cfg: Config) -> sqlite3.Connection:
    con = sqlite3.connect(cfg.paths.db)
    con.row_factory = sqlite3.Row
    return con


def apply_bio(cfg: Config, out_dir: Path, dry: bool = False) -> str:
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
                n += cur.rowcount
        if not dry:
            con.commit()
    finally:
        con.close()
    return f"写入 bio {n} 条，跳过 {miss} 条" + ("（dry）" if dry else "")


def apply_summary(cfg: Config, out_dir: Path, dry: bool = False) -> str:
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


def apply_proof(cfg: Config, out_dir: Path, dry: bool = False) -> str:
    """文字复核只写报告，不回改正文 —— 改正文要人看一眼。"""
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
        with rpt.open("w", encoding="utf-8", newline="") as f:
            f.write("work_id\tchapter_id\t标题\t原文\t建议\t理由\n")
            for r in rows:
                f.write("\t".join(str(x or "") for x in r) + "\n")
    return f"{len(rows)} 处候选 → {rpt}" + ("（dry）" if dry else "")
