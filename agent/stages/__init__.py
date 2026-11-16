# -*- coding: utf-8 -*-
"""环节注册表。

每个 Stage 一个实例，runner 按 needs 自动排序。kind 说明这条环节为什么是脚本、
为什么是 AI、或者为什么两者都要：

  script  规则能一遍覆盖、可回归验证 → 不花 token
  ai      要读语义才知道做对没做对 → 走 API，产物先落盘再 apply
  hybrid  脚本先跑，只把「脚本判不了」的疑难样本交 AI 复核

命名规则：`<域>.<动作>`，域与采集/校勘/文库三段对应。
"""
from __future__ import annotations

from pathlib import Path

from . import library as lib
from . import ai as ai_stages
from . import canon as canon_stages

PIPE_DIR = Path(__file__).resolve().parent.parent / "pipelines"

# 声明顺序即流水线顺序；needs 只写「必须先完成」的环节
ALL = [
    # ── 采集 ─────────────────────────────────────────────
    lib.collect,
    lib.dedupe_source,
    # ── 校勘（S1 机械 / S2 修字 / S3 体例）──────────────
    canon_stages.clean,
    canon_stages.reflow,
    canon_stages.fix_glyph,
    canon_stages.fix_punct,
    canon_stages.audit_chars,
    # ── 章结构 ───────────────────────────────────────────
    canon_stages.restore_titles,
    # ── 文库 ─────────────────────────────────────────────
    lib.build_db,
    lib.chapters,
    lib.dedupe_chapters,
    lib.merge_works,
    lib.classify_source,
    lib.meta,
    lib.characters,
    lib.fts,
    lib.check,
    # ── AI 环节 ──────────────────────────────────────────
    ai_stages.text_proof,
    ai_stages.bio,
    ai_stages.summary,
]

BY_NAME = {s.name: s for s in ALL}
