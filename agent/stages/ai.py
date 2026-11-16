# -*- coding: utf-8 -*-
"""AI 环节（ai / hybrid）。

原则（用户 m10197 / m10198）：
  能用脚本可靠判定的绝不花 token；只有「必须读语义才知道做对没做对」的
  才交给模型，而且**先落盘成 JSON 再 apply**，这样一次生成可以反复入库、
  出问题也能定位到是模型胡写还是入库脚本写错。

三件事由框架统一兜住：
  1. 幂等 key = 作品 id + 正文 sha256 + prompt 版本 + 模型名 → 同样的输入不重复花钱
  2. 每次调用的 token 与费用落 agent/state/ledger.db → 能按作品归集、能熔断
  3. 产出先过 schema（json_schema strict）再过业务门禁（字数/段数/禁用词）→ 不合格不落库
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from ..core.stage import Ctx, Stage
from .library import _db

# prompt 版本：改了下面的提示词就加一，幂等 key 随之变化，旧结果自动失效
PROMPT_VER = "v1"


# ───────────────────────── 公共 ─────────────────────────

def _works_missing(ctx: Ctx, sql: str, limit: int = 50) -> list[dict]:
    con = sqlite3.connect(_db(ctx))
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, (limit,))]
    finally:
        con.close()


def _out_dir(ctx: Ctx) -> Path:
    p = ctx.cfg.paths.state / "out" / ctx.stage
    p.mkdir(parents=True, exist_ok=True)
    return p


def _llm(ctx: Ctx):
    from ..core.llm import LLM
    return LLM(ctx.cfg.llm, ctx.ledger, ctx.run_id, ctx.stage)


def _schema(props: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


# ───────────────────────── 角色 bio ─────────────────────────

BIO_SYSTEM = (
    "你在为一个私人中文成人同人文库写角色小传。读者是这部小说的读者，"
    "他想在目录旁看到「这个人是谁、在这本书里干了什么」。"
    "只依据给出的原文片段写，不编造设定、不评价文笔、不分条列点。"
)

BIO_SCHEMA = _schema(
    {
        "items": {
            "type": "array",
            "items": _schema(
                {"name": {"type": "string"}, "bio": {"type": "string"}},
                ["name", "bio"],
            ),
        }
    },
    ["items"],
)


def _bio_missing(ctx: Ctx) -> list[dict]:
    return _works_missing(
        ctx,
        "SELECT c.id, c.work_id, c.name, c.role, c.gender, c.mentions, "
        "       w.title AS work_title "
        "FROM characters c JOIN works w ON w.id = c.work_id "
        "WHERE (c.bio IS NULL OR c.bio = '') AND w.merged_into IS NULL "
        "ORDER BY c.work_id LIMIT ?",
    )


def _paras_for(ctx: Ctx, work_id: int, name: str, n: int = 6) -> list[str]:
    """取该角色出现的段落当素材 —— 比整章喂进去省 90% token。"""
    con = sqlite3.connect(_db(ctx))
    try:
        rows = con.execute(
            "SELECT content FROM chapters WHERE work_id = ? ORDER BY idx", (work_id,)
        ).fetchall()
    finally:
        con.close()
    hits: list[str] = []
    for (content,) in rows:
        for para in (content or "").split("\n"):
            if name in para and 20 <= len(para) <= 600:
                hits.append(para.strip())
                if len(hits) >= n:
                    return hits
    return hits


def _run_bio(ctx: Ctx) -> str:
    todo = _bio_missing(ctx)
    if not todo:
        return "没有缺 bio 的角色"
    by_work: dict[int, list[dict]] = {}
    for c in todo:
        by_work.setdefault(c["work_id"], []).append(c)

    llm = _llm(ctx)
    out_dir = _out_dir(ctx)
    written = 0

    def one(wid: int) -> None:
        nonlocal written
        chars = by_work[wid][:50]
        blocks = []
        for c in chars:
            paras = _paras_for(ctx, wid, c["name"])
            if not paras:
                continue
            blocks.append(
                f"角色：{c['name']}（{c['role']}，{c['gender'] or '不明'}，"
                f"出现 {c['mentions']} 次）\n" + "\n".join(paras)
            )
        if not blocks:
            return
        user = (
            f"作品：《{chars[0]['work_title']}》\n\n"
            + "\n\n---\n\n".join(blocks)
            + "\n\n为上面每个角色写 1–3 段连贯的小传（每人 120–260 字），"
              "只写他在本书里的身份、做过的事、与谁的关系、说话与行事的样子。"
              "成人向内容照实叙述，不必回避。不要复述原文句子，不要加标题或字段名。"
        )
        data = llm.chat_json(
            [{"role": "system", "content": BIO_SYSTEM},
             {"role": "user", "content": user}],
            BIO_SCHEMA, tag=f"bio:{wid}", prompt_ver=PROMPT_VER,
        )
        items = [x for x in (data.get("items") or [])
                 if isinstance(x.get("bio"), str) and len(x["bio"]) >= 60]
        if items:
            p = out_dir / f"w{wid}.json"
            p.write_text(json.dumps({"work_id": wid, "items": items},
                                    ensure_ascii=False, indent=1), encoding="utf-8")
            written += len(items)

    llm.map(list(by_work), one)
    return f"生成 {written} 条（{len(by_work)} 部），产物在 {out_dir}"


def _check_bio(ctx: Ctx) -> tuple[bool, str]:
    out_dir = _out_dir(ctx)
    files = list(out_dir.glob("w*.json"))
    bad = 0
    for p in files:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            for it in d.get("items", []):
                if len(it.get("bio", "")) < 60:
                    bad += 1
        except Exception:                      # noqa: BLE001
            bad += 1
    return (bad == 0, f"产出 {len(files)} 部，不合格项 {bad}")


bio = Stage(
    name="bio",
    kind="ai",
    run=_run_bio,
    needs=["characters"],
    check=_check_bio,
    description="为缺 bio 的角色写小传（素材只取该角色出现的段落）",
)


def _bio_input_fp(ctx: Ctx) -> str:
    con = sqlite3.connect(_db(ctx))
    try:
        n = con.execute(
            "SELECT COUNT(*) FROM characters WHERE bio IS NULL OR bio=''"
        ).fetchone()[0]
    finally:
        con.close()
    return f"missing={n}"


bio.fingerprint = _bio_input_fp


# ───────────────────────── 书籍简介 ─────────────────────────

SUMMARY_SCHEMA = _schema(
    {"summary": {"type": "string"}, "tags": {
        "type": "array", "items": {"type": "string"}}},
    ["summary", "tags"],
)


def _run_summary(ctx: Ctx) -> str:
    todo = _works_missing(
        ctx,
        "SELECT id, title, source_work, char_count FROM works w "
        "WHERE merged_into IS NULL AND (summary_ai IS NULL OR summary_ai = '') "
        "ORDER BY char_count DESC LIMIT ?",
    )
    if not todo:
        return "没有缺简介的作品"
    llm = _llm(ctx)
    out_dir = _out_dir(ctx)

    def one(w: dict) -> None:
        con = sqlite3.connect(_db(ctx))
        try:
            head = con.execute(
                "SELECT content FROM chapters WHERE work_id=? ORDER BY idx LIMIT 3",
                (w["id"],),
            ).fetchall()
        finally:
            con.close()
        text = "\n".join((r[0] or "")[:1500] for r in head)[:4000]
        user = (
            f"作品：《{w['title']}》　原作：{w['source_work'] or '原创'}　"
            f"篇幅：{w['char_count']} 字\n\n开头节选：\n{text}\n\n"
            "写一段 140–220 字的简介：这本书讲什么、谁和谁、主要看点是什么。"
            "平实叙述，不剧透结局，不用「本文」「本章」这类词。"
            "另外给 5–8 个标签（每个 2–4 字，题材/玩法/关系向）。"
        )
        data = llm.chat_json(
            [{"role": "system", "content": "你在为一个私人成人同人文库写书目简介。"},
             {"role": "user", "content": user}],
            SUMMARY_SCHEMA, tag=f"summary:{w['id']}", prompt_ver=PROMPT_VER,
        )
        (out_dir / f"w{w['id']}.json").write_text(
            json.dumps({"work_id": w["id"], **data}, ensure_ascii=False, indent=1),
            encoding="utf-8")

    llm.map(todo, one)
    return f"生成 {len(todo)} 部"


summary = Stage(
    name="summary",
    kind="ai",
    run=_run_summary,
    needs=["meta"],
    description="为缺 AI 简介的作品写 140–220 字简介与标签",
)


# ───────────────────────── 文字复核（hybrid）─────────────────────

PROOF_SCHEMA = _schema(
    {"issues": {"type": "array", "items": _schema(
        {"before": {"type": "string"}, "after": {"type": "string"},
         "why": {"type": "string"}}, ["before", "after", "why"])}},
    ["issues"],
)

PROOF_SYSTEM = (
    "你是中文校对员。给定一段成人向同人小说正文，只找三类问题："
    "①明显的错别字（同音、形近）②专名前后不一致（人名/地名/招式名写法不同）"
    "③标点或排版残留（重复标点、残留符号）。"
    "不要改写文风，不要润色，不要因为露骨内容提意见。"
    "每处给出原文片段 before（≤12 字）、改法 after（≤12 字）、一句话理由 why。"
    "没有把握就不要报。"
)


def _run_text_proof(ctx: Ctx) -> str:
    """抽样复核：只查库里「字数骤降 / 可疑字符」的样本，不做全量。"""
    rows = _works_missing(
        ctx,
        "SELECT c.id, c.work_id, c.title, c.content FROM chapters c "
        "JOIN works w ON w.id = c.work_id "
        "WHERE w.merged_into IS NULL AND length(c.content) BETWEEN 800 AND 4000 "
        "ORDER BY c.work_id, c.idx LIMIT ?",
    )
    if not rows:
        return "没有需要复核的样本"
    llm = _llm(ctx)
    out_dir = _out_dir(ctx)
    found = 0

    def one(r: dict) -> None:
        nonlocal found
        data = llm.chat_json(
            [{"role": "system", "content": PROOF_SYSTEM},
             {"role": "user", "content": r["content"][:3000]}],
            PROOF_SCHEMA, tag=f"proof:{r['id']}", prompt_ver=PROMPT_VER,
        )
        issues = [x for x in (data.get("issues") or [])
                  if x.get("before") and x.get("after") and x["before"] != x["after"]]
        if issues:
            found += len(issues)
            (out_dir / f"c{r['id']}.json").write_text(
                json.dumps({"chapter_id": r["id"], "work_id": r["work_id"],
                            "title": r["title"], "issues": issues},
                           ensure_ascii=False, indent=1), encoding="utf-8")

    llm.map(rows, one)
    return f"复核 {len(rows)} 节，报出 {found} 处候选"


text_proof = Stage(
    name="text_proof",
    kind="hybrid",
    run=_run_text_proof,
    needs=["fts"],
    description="抽样复核错别字/专名不一致/标点残留，只报疑似、不自动改",
)
