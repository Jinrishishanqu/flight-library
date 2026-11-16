# -*- coding: utf-8 -*-
"""环节注册表。

每个 Stage 一个实例，runner 按 ALL 的声明顺序依次执行（needs 只用于说明与
`--dry` 展示，真正的数据依赖已经在库里 —— 见 core/runner.py 的说明）。
kind 说明这条环节为什么是脚本、为什么是 AI、或者为什么两者都要：

  script  规则能一遍覆盖、可回归验证 → 不花 token
  ai      要读语义才知道做对没做对 → 走 API，产物先落盘再 apply
  hybrid  脚本先跑，只把「脚本判不了」的疑难样本交 AI 复核

加新环节的步骤（三步，都在本目录内完成）：
  1. 在 library.py / canon.py / ai.py 里定义 Stage 实例（run 至少要能返回一句 detail）
  2. 在下面的 ALL 里按执行顺序插入
  3. `python -m agent list` 确认注册成功，`python -m agent run <pipeline> <新环节>` 单跑

改提示词时：把 ai.py 顶部的 PROMPT_VER 加一。它会进入 dedupe_key 的输入指纹，
旧结果自动失效、下次运行重算；不改版本号会导致「改了 prompt 但仍被幂等跳过」。
"""
from __future__ import annotations

from pathlib import Path

from . import library as lib
from . import ai as ai_stages
from . import canon as canon_stages

# pipelines/*.toml 所在目录（run 时若没点名环节，就从 <pipeline>.toml 读 stages）
PIPE_DIR = Path(__file__).resolve().parent.parent / "pipelines"

# 声明顺序即流水线顺序；needs 只写「必须先完成」的环节
ALL = [
    # ── 采集 ─────────────────────────────────────────────
    lib.collect,              # 原文/ 清点，产出待入库清单
    lib.dedupe_source,        # MinHash 查重（只提示）
    # ── 校勘（S1 机械 / S2 修字 / S3 体例）──────────────
    canon_stages.clean,       # clean1→clean3 + unified3 + postprocess + final_polish
    canon_stages.reflow,      # 长段重排（可逆）
    canon_stages.fix_glyph,   # 形近错字 / 全角数字 / 孤立括号
    canon_stages.fix_punct,   # 全角 ASCII 与全角引号
    canon_stages.audit_chars, # 编码 / mojibake / 同形字体检（hybrid）
    # ── 章结构 ───────────────────────────────────────────
    canon_stages.restore_titles,   # 用校对清单把分卷文件名对回原文标题
    # ── 文库 ─────────────────────────────────────────────
    lib.build_db,             # 校勘版/ → works + chapters
    lib.chapters,             # 按原文「第N章」重划章节
    lib.dedupe_chapters,      # 章级近重复（≥0.98 才删）
    lib.merge_works,          # 同作异名整块合并
    lib.classify_source,      # 待归类/ → 具体作品目录
    lib.meta,                 # path_source / notes / description
    lib.characters,           # hanlp 候选 + 清洗 + 主角判定
    lib.fts,                  # 全量重灌 FTS5
    lib.check,                # 一致性体检
    # ── AI 环节 ──────────────────────────────────────────
    ai_stages.text_proof,     # 文字复核（hybrid，只报疑似）
    ai_stages.bio,            # 角色小传
    ai_stages.summary,        # 书籍简介与标签
]

# 名字 → Stage，供 runner 与 --only 查找
BY_NAME = {s.name: s for s in ALL}
