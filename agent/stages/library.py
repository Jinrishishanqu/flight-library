# -*- coding: utf-8 -*-
"""采集与文库环节（script）。

这一组的共同特征：脚本已经能做到「跑完能回归验证」，所以不花 token。
每个 Stage 的 check 就是它的验收标准 —— 不过就直接 failed，不许带病往下走。
判据是「换一批输入重跑，结果是否确定」：这里全为真（同一份原文切出来的章节数、
同一条 SQL 数出来的行数，每次都一样），所以不该交给模型。

依赖链（needs 只是给人看的顺序说明，真正的依赖在库里）：
    原文/ ──collect──> 待入库清单
              └─dedupe_source──> dupes.csv（只提示）
    校勘版/ ──build_db──> works + chapters
              ├─chapters──> 按原文「第N章」重划
              │     ├─dedupe_chapters  章级近重复
              │     ├─merge_works      同作异名整块合并
              │     └─fts               全量重灌索引
              ├─classify_source  待归类/ → 具体作品目录
              ├─meta             path_source / notes / description
              └─characters       hanlp 候选 + 清洗 + 主角判定
                                 └─check  一致性体检

注意 chapters / merge_works 的顺序：merge_works 会把子本内容整块插进主本，
而 rebuild_chapters 对「有子本的主本」是跳过的（否则会把合并内容抹掉），
所以两者互不覆盖，但顺序仍按声明来，先重建再合并。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..core.stage import Ctx, Stage, file_digest, tree_digest


# ────────────────────────────── 采集 ──────────────────────────────

def _collect_fp(ctx: Ctx) -> str:
    return tree_digest([ctx.root / "原文"])


def _run_collect(ctx: Ctx) -> str:
    """采集是半自动的（列表页 → 正文要人确认），这里只做「清点」：
    扫 原文/ 拿全部 txt，与库里 works.path_source 已登记的比对，报出未入库的。"""
    src_root = ctx.root / "原文"
    files = {str(p.relative_to(ctx.root)).replace("\\", "/"): p
             for p in src_root.rglob("*.txt")}
    known: set[str] = set()
    if _db(ctx).exists():
        con = sqlite3.connect(_db(ctx))
        try:
            for (ps,) in con.execute(
                    "SELECT path_source FROM works WHERE path_source IS NOT NULL AND path_source<>''"):
                for one in (ps or "").split("|"):
                    if one.strip():
                        known.add(one.strip().replace("\\", "/"))
        finally:
            con.close()
    new = [k for k in files if k not in known]
    listing = ctx.cfg.paths.state / "reports" / "collect_new.txt"
    listing.parent.mkdir(parents=True, exist_ok=True)
    listing.write_text("\n".join(sorted(new)), encoding="utf-8")
    return f"原文 {len(files)} 个 txt，已入库 {len(known)}，待入库 {len(new)}（清单 {listing.name}）"


def _check_collect(ctx: Ctx) -> tuple[bool, str]:
    src = ctx.root / "原文"
    n = len(list(src.rglob("*.txt")))
    return (n > 0, f"原文 {n} 个 txt")


collect = Stage(
    name="collect",
    kind="script",
    run=_run_collect,
    fingerprint=_collect_fp,
    check=_check_collect,
    description="扫描 原文/ 目录，把新文件登记进待入库清单",
)


def _dedupe_fp(ctx: Ctx) -> str:
    return tree_digest([ctx.root / "原文"])


def _run_dedupe_source(ctx: Ctx) -> str:
    out = ctx.cfg.paths.state / "reports" / "dupes.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    rc, o = ctx.script("dedupe.py", "--dir", str(ctx.root / "原文"), "--out", str(out),
                       cwd=ctx.py_dir)
    tail = (o or "").strip().splitlines()
    return f"{tail[-1] if tail else '查重完成'} → {out.name}"


def _check_dedupe_source(ctx: Ctx) -> tuple[bool, str]:
    p = ctx.cfg.paths.state / "reports" / "dupes.csv"
    if not p.exists():
        return True, "无报告（首次运行）"
    lines = p.read_text(encoding="utf-8", errors="replace").count("\n")
    return (True, f"疑似重复 {max(0, lines - 1)} 组（仅提示，不阻断）")


dedupe_source = Stage(
    name="dedupe_source",
    kind="script",
    run=_run_dedupe_source,
    needs=["collect"],
    fingerprint=_dedupe_fp,
    check=_check_dedupe_source,
    description="MinHash 查重，只提示不删除",
)


# ────────────────────────────── 文库 ──────────────────────────────

def _db(ctx: Ctx) -> Path:
    return ctx.cfg.paths.db


def _build_fp(ctx: Ctx) -> str:
    return file_digest(_db(ctx))


def _run_build_db(ctx: Ctx) -> str:
    rc, out = ctx.script("build_db.py")
    return out.strip().splitlines()[-1] if out.strip() else "入库完成"


def _check_build_db(ctx: Ctx) -> tuple[bool, str]:
    """验收：库存在且 works 非空。只数「有没有」，不数「对不对」——
    内容正确性由后面的 check_db.py 环节兜。"""
    if not _db(ctx).exists():
        return False, "数据库不存在"
    con = sqlite3.connect(_db(ctx))
    try:
        n = con.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    finally:
        con.close()
    return (n > 0, f"works {n}")


build_db = Stage(
    name="build_db",
    kind="script",
    run=_run_build_db,
    needs=["dedupe_source"],
    fingerprint=_build_fp,
    check=_check_build_db,
    description="校勘版/ → library.db（works + chapters）",
)


def _run_chapters(ctx: Ctx) -> str:
    rc, out = ctx.script("rebuild_chapters.py", "--apply")
    return out.strip().replace("\n", " · ")[-300:]


def _check_chapters(ctx: Ctx) -> tuple[bool, str]:
    """验收：可见作品里没有「有章节行但正文为空」的节。
    空正文说明切章把内容吃掉了（历史上 split_chapters 的 TITLE_JUNK 分支
    曾丢过 5.8 万字），所以这条必须硬性拦截。"""
    con = sqlite3.connect(_db(ctx))
    try:
        empty = con.execute(
            "SELECT COUNT(*) FROM chapters c JOIN works w ON w.id=c.work_id "
            "WHERE w.merged_into IS NULL AND length(trim(c.content))=0"
        ).fetchone()[0]
        total = con.execute("SELECT COUNT(*) FROM chapters").fetchone()[0]
    finally:
        con.close()
    return (empty == 0, f"章节 {total}，空正文 {empty}")


chapters = Stage(
    name="chapters",
    kind="script",
    run=_run_chapters,
    needs=["build_db"],
    check=_check_chapters,
    description="按原文「第N章」重划章节，脚本覆盖不了的部分保持按字数切",
)


def _run_dedupe_chapters(ctx: Ctx) -> str:
    rc, out = ctx.script("dedupe_chapters.py", "--apply")
    return out.strip().replace("\n", " · ")[-240:]


dedupe_chapters = Stage(
    name="dedupe_chapters",
    kind="script",
    run=_run_dedupe_chapters,
    needs=["chapters"],
    description="章级近重复（≥0.98 才删），0.85–0.98 视为作者改写保留",
)


def _run_merge(ctx: Ctx) -> str:
    rc, out = ctx.script("merge_works3.py", "--apply")
    return out.strip().replace("\n", " · ")[-240:]


merge_works = Stage(
    name="merge_works",
    kind="script",
    run=_run_merge,
    needs=["chapters"],
    description="同作异名整块合并（判同文只标 merged_into，不散插）",
)


def _run_classify(ctx: Ctx) -> str:
    rc, out = ctx.script("classify_source.py", "--apply")
    return out.strip().splitlines()[-1] if out.strip() else "归类完成"


classify_source = Stage(
    name="classify_source",
    kind="script",
    run=_run_classify,
    needs=["dedupe_source"],
    description="把待归类/ 的文件按关键词+人工覆盖表分到具体作品目录",
)


def _run_meta(ctx: Ctx) -> str:
    parts = []
    for name in ("fill_meta.py", "fill_notes.py", "fill_desc.py"):
        rc, out = ctx.script(name, "--apply")
        tail = out.strip().splitlines()[-1] if out.strip() else ""
        parts.append(f"{name}: {tail}")
    return " | ".join(parts)


def _check_meta(ctx: Ctx) -> tuple[bool, str]:
    """验收：可见作品都要有 path_source（原文出处）。
    这条是全库元数据的底线 —— 没有它就无法判断「某篇新文章是不是已有作品的续篇」。"""
    con = sqlite3.connect(_db(ctx))
    try:
        miss = con.execute(
            "SELECT COUNT(*) FROM works WHERE merged_into IS NULL AND "
            "(path_source IS NULL OR path_source='')"
        ).fetchone()[0]
    finally:
        con.close()
    return (miss == 0, f"缺 path_source 的可见作品 {miss}")


meta = Stage(
    name="meta",
    kind="script",
    run=_run_meta,
    needs=["build_db", "classify_source"],
    check=_check_meta,
    description="path_source / notes / description 三类元数据",
)


def _run_characters(ctx: Ctx) -> str:
    rc, out = ctx.script("build_characters.py", "--limit", "50")
    return out.strip().splitlines()[-1] if out.strip() else "角色卡完成"


def _check_characters(ctx: Ctx) -> tuple[bool, str]:
    """验收：每部作品的角色卡 ≤50 张（用户硬要求）。
    缺 bio 只报告不拦截 —— bio 是 AI 环节的事，脚本环节无权重跑它。"""
    con = sqlite3.connect(_db(ctx))
    try:
        bad = con.execute(
            "SELECT COUNT(*) FROM (SELECT work_id, COUNT(*) n FROM characters "
            "GROUP BY work_id HAVING n > 50)"
        ).fetchone()[0]
        nobio = con.execute(
            "SELECT COUNT(*) FROM characters WHERE bio IS NULL OR bio=''"
        ).fetchone()[0]
        total = con.execute("SELECT COUNT(*) FROM characters").fetchone()[0]
    finally:
        con.close()
    ok = bad == 0
    return (ok, f"角色 {total}，超 50 人的作品 {bad}，缺 bio {nobio}（bio 由 AI 环节补）")


characters = Stage(
    name="characters",
    kind="script",
    run=_run_characters,
    needs=["chapters", "meta"],
    check=_check_characters,
    description="hanlp 出候选 + 四层清洗 + 按出场范围判主角，每部 ≤50 张卡",
)


def _run_fts(ctx: Ctx) -> str:
    rc, out = ctx.script("refresh_fts.py")
    return out.strip().splitlines()[-1] if out.strip() else "索引完成"


def _check_fts(ctx: Ctx) -> tuple[bool, str]:
    con = sqlite3.connect(_db(ctx))
    try:
        n = con.execute("SELECT COUNT(*) FROM chapters_fts").fetchone()[0]
        total = con.execute(
            "SELECT COUNT(*) FROM chapters c JOIN works w ON w.id=c.work_id "
            "WHERE w.merged_into IS NULL"
        ).fetchone()[0]
    finally:
        con.close()
    return (n == total, f"FTS {n} / 可见章节 {total}")


fts = Stage(
    name="fts",
    kind="script",
    run=_run_fts,
    needs=["chapters"],
    check=_check_fts,
    description="全量重灌 FTS5（bigram + 拉丁词），带断言",
)


def _run_check(ctx: Ctx) -> str:
    rc, out = ctx.script("check_db.py")
    return out.strip().replace("\n", " · ")[-500:]


check = Stage(
    name="check",
    kind="script",
    run=_run_check,
    needs=["fts", "characters"],
    description="全库一致性体检（字数 / 空正文 / 索引 / 角色上限）",
)
