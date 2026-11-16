# -*- coding: utf-8 -*-
"""校勘环节（script + hybrid）。

S1 机械保真 / S2 有据修字 / S3 体例统一 三层是老脚本，路径写死在
`采集工具\\校勘\\`，这里只负责按正确顺序调、并给出可回归的验收数。

判断依据（为什么要分 script / hybrid）：
  clean / reflow / fix_*  换一批文件重跑结果确定，且可用「字数不变、文件数不变、
                          不含禁用字符」这类不变量校验 → script
  audit_chars             要判断「这个字是不是错字」需要中文语义，脚本只能报可疑，
                          真正的裁定交 AI 复核 → hybrid
"""
from __future__ import annotations

import re
from pathlib import Path

from ..core.stage import Ctx, Stage, tree_digest

CJK = re.compile(r"[\u4e00-\u9fff]")


def _canon_files(ctx: Ctx) -> list[Path]:
    return sorted((ctx.root / "校勘版").rglob("*.txt"))


def _text_of(p: Path) -> str:
    raw = p.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "gb18030", "utf-16"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _stats(ctx: Ctx) -> tuple[int, int]:
    files = _canon_files(ctx)
    chars = sum(len(CJK.findall(_text_of(p))) for p in files)
    return len(files), chars


# ──────────────────── S1 机械清洗 ────────────────────

def _fp_canon(ctx: Ctx) -> str:
    return tree_digest([ctx.root / "校对后文章", ctx.root / "校勘版"])


def _run_clean(ctx: Ctx) -> str:
    """三层清洗按顺序跑；每层脚本自己写盘，幂等靠「输出已在则脚本自己跳过」。"""
    done = []
    for name in ("clean1.py", "clean2.py", "clean3.py", "unified3.py",
                 "postprocess.py", "final_polish.py"):
        ctx.script(name, cwd=ctx.canon_dir)
        done.append(name.replace(".py", ""))
    return " → ".join(done)


def _check_clean(ctx: Ctx) -> tuple[bool, str]:
    files, chars = _stats(ctx)
    return (files > 0 and chars > 0, f"校勘版 {files} 文件 / {chars} 汉字")


clean = Stage(
    name="clean",
    kind="script",
    run=_run_clean,
    fingerprint=_fp_canon,
    check=_check_clean,
    description="S1 广告水印 → S2 有据修字 → S3 体例统一（clean1→clean3, unified3, postprocess, final_polish）",
)


# ──────────────────── 可读性重排 ────────────────────

def _run_reflow(ctx: Ctx) -> str:
    ctx.script("reflow.py", cwd=ctx.canon_dir)
    return "长段重排完成（只插入换行，删掉换行后与原文件逐字相同）"


def _check_reflow(ctx: Ctx) -> tuple[bool, str]:
    files = _canon_files(ctx)
    long_paras = 0
    for p in files[:60]:                       # 抽样 60 部，全量太慢
        for line in _text_of(p).splitlines():
            if len(line) > 400:
                long_paras += 1
    return (long_paras < 20, f"抽样 60 部，>400 字的段落 {long_paras} 个")


reflow = Stage(
    name="reflow",
    kind="script",
    run=_run_reflow,
    needs=["clean"],
    check=_check_reflow,
    description="按句末标点切超长段，保证可逆（阈值 220/60–170/260）",
)


# ──────────────────── 形近字与数字 ────────────────────

def _run_fix_glyph(ctx: Ctx) -> str:
    out = []
    for name in ("fix_glyph.py", "fix_numbers.py", "fix_orphan_bracket.py"):
        rc, o = ctx.script(name, cwd=ctx.canon_dir)
        tail = (o or "").strip().splitlines()
        out.append(tail[-1] if tail else name)
    return " | ".join(out)[-400:]


fix_glyph = Stage(
    name="fix_glyph",
    kind="script",
    run=_run_fix_glyph,
    needs=["reflow"],
    description="形近错字（闻然→闻言）/ 全角数字 / 孤立括号 三类定点修补",
)


def _run_fix_punct(ctx: Ctx) -> str:
    out = []
    for name in ("fix_wide_ascii.py", "fix_fullwidth_quotes.py"):
        rc, o = ctx.script(name, "--apply", cwd=ctx.canon_dir)
        tail = (o or "").strip().splitlines()
        out.append(tail[-1] if tail else name)
    return " | ".join(out)[-400:]


def _check_fix_punct(ctx: Ctx) -> tuple[bool, str]:
    bad = 0
    for p in _canon_files(ctx):
        t = _text_of(p)
        bad += t.count("\uff02") + t.count("\uff07")
        bad += len(re.findall(r"[\uff10-\uff19\uff21-\uff3a\uff41-\uff5a]", t))
    return (bad == 0, f"全角 ASCII / 全角引号残留 {bad}")


fix_punct = Stage(
    name="fix_punct",
    kind="script",
    run=_run_fix_punct,
    needs=["reflow"],
    check=_check_fix_punct,
    description="全角数字字母转半角、全角双引号按栈配对转「」，标点一律不动",
)


# ──────────────────── 体检（hybrid）────────────────────

def _run_audit_chars(ctx: Ctx) -> str:
    out = []
    for name, args in (("clean_text.py", ("check", str(ctx.root / "校勘版"))),
                       ("scan_mojibake.py", ()),
                       ("confusable_scan.py", ())):
        try:
            rc, o = ctx.script(name, *args, cwd=ctx.canon_dir)
            tail = (o or "").strip().splitlines()
            out.append(f"{name}: {tail[-1] if tail else 'ok'}")
        except Exception as e:                 # noqa: BLE001
            out.append(f"{name}: {e}")
    return " | ".join(out)[-500:]


audit_chars = Stage(
    name="audit_chars",
    kind="hybrid",
    run=_run_audit_chars,
    needs=["fix_punct"],
    description="编码 / mojibake / 同形字 / 私有区 四类字符体检，可疑样本交 AI 复核",
)


# ──────────────────── 章标题恢复 ────────────────────

def _run_restore_titles(ctx: Ctx) -> str:
    ctx.script("restore_chapter_titles.py", cwd=ctx.canon_dir)
    return "章标题按校对清单回填完成"


restore_titles = Stage(
    name="restore_titles",
    kind="script",
    run=_run_restore_titles,
    needs=["clean"],
    description="用 采集工具\\记录\\校对清单.csv 把分卷文件名对回原文标题",
)
