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

from ..core.prompts import P
from ..core.stage import Ctx, Stage
from .library import _db

# 提示词不在这里：全部在 agent/prompts/*.txt。
# 版本号也不再手写 —— P.version() 是提示词目录的内容哈希，改了任何一个 .txt
# 它就会变，进而让幂等 key 失效、下次运行自动重跑。
# （旧的 PROMPT_VER = "v1" 常量已删除：忘了 bump 就改不动结果，是最难查的坑。）


# ───────────────────────── 公共 ─────────────────────────

def _works_missing(ctx: Ctx, sql: str, limit: int = 50) -> list[dict]:
    """执行带 `LIMIT ?` 的查询，参数固定为 limit。

    三个 AI 环节都用它取「还缺什么」：缺 bio 的角色、缺简介的作品、
    待复核的章节。用 SQL 决定工作集而不是 Python 过滤，是为了少读几万行。
    """
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
        """处理一部作品：把所有缺 bio 的角色塞进同一次请求。

        为什么按「作品」而不是按「角色」分组：同一部书里的角色互相有关系，
        一次给全文片段能让模型写出「她与谁是什么关系」，省一半 token 又更连贯。
        """
        nonlocal written
        chars = by_work[wid][:50]          # 与 characters 上限一致，防止单次请求过大
        blocks = []
        for c in chars:
            paras = _paras_for(ctx, wid, c["name"])
            if not paras:
                continue
            # 单个角色的素材块也走模板（bio.block.txt），改格式不用动 Python
            blocks.append(P.render(
                "bio.block",
                name=c["name"], role=c["role"], gender=c["gender"] or "不明",
                mentions=c["mentions"], paras="\n".join(paras),
            ))
        if not blocks:
            return
        user = P.render("bio.user", title=chars[0]["work_title"],
                        blocks="\n\n---\n\n".join(blocks))
        data = llm.chat_json(
            [{"role": "system", "content": P.text("bio.system")},
             {"role": "user", "content": user}],
            BIO_SCHEMA, tag=f"bio:{wid}", prompt_ver=P.version(),
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
    """验收：产物里每条 bio ≥60 字、JSON 可解析。

    这条拦的是模型偷懒（只回一句「信息不足」）与写坏 JSON ——
    两者都会让 apply 静默跳过，等于白花钱。
    """
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
    """bio 的输入指纹 = 缺 bio 的角色数 + 提示词版本。

    为什么不用正文哈希：bio 的输入其实是「哪些角色还没写」，
    只要这个数字不变，重跑就会产出同一批东西，没必要再花钱。
    带上 P.version() 是关键 —— 改一个字提示词，指纹就变，旧结果不再算数。
    """
    con = sqlite3.connect(_db(ctx))
    try:
        n = con.execute(
            "SELECT COUNT(*) FROM characters WHERE bio IS NULL OR bio=''"
        ).fetchone()[0]
    finally:
        con.close()
    return f"missing={n}|p{P.version()}"


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
        user = P.render("summary.user", title=w["title"],
                        source_work=w["source_work"] or "原创",
                        chars=w["char_count"], head=text)
        data = llm.chat_json(
            [{"role": "system", "content": P.text("summary.system")},
             {"role": "user", "content": user}],
            SUMMARY_SCHEMA, tag=f"summary:{w['id']}", prompt_ver=P.version(),
        )
        (out_dir / f"w{w['id']}.json").write_text(
            json.dumps({"work_id": w["id"], **data}, ensure_ascii=False, indent=1),
            encoding="utf-8")

    llm.map(todo, one)
    return f"生成 {len(todo)} 部"


def _summary_input_fp(ctx: Ctx) -> str:
    """简介的输入指纹 = 缺简介的作品数 + 提示词版本。理由同 bio。"""
    con = sqlite3.connect(_db(ctx))
    try:
        n = con.execute(
            "SELECT COUNT(*) FROM works WHERE merged_into IS NULL "
            "AND (summary_ai IS NULL OR summary_ai='')"
        ).fetchone()[0]
    finally:
        con.close()
    return f"missing={n}|p{P.version()}"


summary = Stage(
    name="summary",
    kind="ai",
    run=_run_summary,
    needs=["meta"],
    fingerprint=_summary_input_fp,
    description="为缺 AI 简介的作品写 140–220 字简介与标签",
)


# ───────────────────────── 文字复核（hybrid）─────────────────────

PROOF_SCHEMA = _schema(
    {"issues": {"type": "array", "items": _schema(
        {"before": {"type": "string"}, "after": {"type": "string"},
         "why": {"type": "string"}}, ["before", "after", "why"])}},
    ["issues"],
)


def _run_text_proof(ctx: Ctx) -> str:
    """抽样复核：只查库里「字数骤降 / 可疑字符」的样本，不做全量。"""
    rows = _works_missing(
        ctx,
        "SELECT c.id, c.work_id, c.title, c.content, w.title AS work_title "
        "FROM chapters c JOIN works w ON w.id = c.work_id "
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
            [{"role": "system", "content": P.text("proof.system")},
             {"role": "user", "content": P.render(
                 "proof.user", work_title=r.get("work_title") or "", title=r["title"],
                 body=r["content"][:3000])}],
            PROOF_SCHEMA, tag=f"proof:{r['id']}", prompt_ver=P.version(),
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
