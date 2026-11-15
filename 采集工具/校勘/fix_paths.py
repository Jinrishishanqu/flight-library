# -*- coding: utf-8 -*-
r"""一次性路径迁移：把脚本里的 旧目录名 改成 归档\ 下的新位置。

旧结构（全部在项目根级）           新结构
_合并前备份（整合前源单章备份）  -> 归档\备份_整合前
校对后文章\_合并前备份（整合/重叠）-> 归档\备份_校对后
_重复版本                        -> 归档\重复_根级
校对后文章\_重复版本              -> 归档\重复_校对后
_临时                            -> 归档\临时
_非H同人_隔离                     -> 归档\隔离\非H同人
书目索引.csv（根级）              -> 文档\书目索引.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# (相对路径, 旧字面量, 新字面量)
RULES: list[tuple[str, str, str]] = [
    # ---- 查重 ----
    (r"采集工具\查重.ps1", r"Join-Path $root '_重复版本'", r"Join-Path $root '归档\重复_根级'"),
    (r"采集工具\查重.ps1", "把重复件（保留最长）移入 _重复版本", "把重复件（保留最长）移入 归档\\重复_根级"),
    # ---- 合并 ----
    (r"采集工具\合并.ps1", r"Join-Path $root '_合并前备份'", r"Join-Path $root '归档\备份_整合前'"),
    (r"采集工具\合并.ps1", "原文件移到 _合并前备份", "原文件移到 归档\\备份_整合前"),
    (r"采集工具\合并.ps1", r"Join-Path $root '_重复版本'", r"Join-Path $root '归档\重复_根级'"),
    (r"采集工具\合并.ps1", "同章多版本：只留最长的一份，其余进 _重复版本", "同章多版本：只留最长的一份，其余进 归档\\重复_根级"),
    (r"采集工具\合并.ps1", '"_重复版本"', '"归档\\重复_根级"'),
    # ---- 截图 ----
    (r"采集工具\截图.ps1", r"Join-Path $root '_临时\edgeprof'", r"Join-Path $root '归档\临时\edgeprof'"),
    (r"采集工具\截图.ps1", r"'_临时\shot\'", r"'归档\临时\shot\'"),
    (r"采集工具\截图.ps1", r'-OutFile "_临时\shot\a.png"', r'-OutFile "归档\临时\shot\a.png"'),
    (r"采集工具\截图.ps1", r'-OutDir "_临时\shot"', r'-OutDir "归档\临时\shot"'),
    (r"采集工具\截图.ps1", r'-OutDir "_临时\shot"', r'-OutDir "归档\临时\shot"'),
    # ---- 流水线 ----
    (r"采集工具\流水线.ps1", r'-Images "_临时\shot\某书"', r'-Images "归档\临时\shot\某书"'),
    (r"采集工具\流水线.ps1", r"Join-Path $root ('_临时\shot\'", r"Join-Path $root ('归档\临时\shot\'"),
    # ---- 男同删除 ----
    (r"采集工具\男同删除.ps1", r"'..\_合并前备份'", r"'..\归档\备份_整合前'"),
    (r"采集工具\男同删除.ps1", r"'..\_重复版本'", r"'..\归档\重复_根级'"),
    # ---- 清理再生 ----
    (r"采集工具\清理再生.ps1", r"Join-Path $Root '_重复版本'", r"Join-Path $Root '归档\重复_根级'"),
    (r"采集工具\清理再生.ps1", r"Join-Path $Root '_临时\再生件'", r"Join-Path $Root '归档\临时\再生件'"),
    (r"采集工具\清理再生.ps1", r"Join-Path $OutRoot '_合并前备份'", r"Join-Path $Root '归档\备份_校对后'"),
    (r"采集工具\清理再生.ps1", "移到 _临时\\再生件\\", "移到 归档\\临时\\再生件\\"),
    (r"采集工具\清理再生.ps1", "已被 查重.ps1 移入 _重复版本 的重复件", "已被 查重.ps1 移入 归档\\重复_根级 的重复件"),
    (r"采集工具\清理再生.ps1", "跳过 _合并前备份 / _重复版本 等下划线目录", "跳过 _校勘版 等下划线目录"),
    # ---- 章拼接 ----
    (r"采集工具\章拼接.ps1", r"'_合并前备份\重叠'", r"'归档\备份_校对后\重叠'"),
    # ---- 整合 ----
    (r"采集工具\整合.ps1", r"'校对后文章\_重复版本\整合\'", r"'归档\重复_校对后\整合\'"),
    (r"采集工具\整合.ps1", r"'校对后文章\_合并前备份\整合\'", r"'归档\备份_校对后\整合\'"),
    # ---- 重叠合并 ----
    (r"采集工具\重叠合并.ps1", r"'..\_合并前备份\重叠'", r"'..\归档\备份_校对后\重叠'"),
    # ---- 重建清单 ----
    (r"采集工具\重建清单.ps1", r"Join-Path $root '_合并前备份'", r"Join-Path $root '归档\备份_整合前'"),
    (r"采集工具\重建清单.ps1", "跳过 _合并前备份 / _重复版本", "跳过 _校勘版"),
    # ---- 入库 ----
    (r"采集工具\入库.ps1", r"Join-Path $Root '_临时\旧版备份'", r"Join-Path $Root '归档\临时\旧版备份'"),
    (r"采集工具\入库.ps1", "旧件备份到 _临时\\旧版备份", "旧件备份到 归档\\临时\\旧版备份"),
    # ---- OCR ----
    (r"采集工具\OCR.ps1", r"..\_临时\ocr", r"..\归档\临时\ocr"),
    # ---- py 层 ----
    (r"采集工具\py\apply_norm.py", '"_临时/norm"', '"归档/临时/norm"'),
    (r"采集工具\py\apply_norm.py", '"_临时/norm_bak"', '"归档/临时/norm_bak"'),
    (r"采集工具\py\apply_norm.py", "--norm _临时/norm", "--norm 归档/临时/norm"),
    (r"采集工具\py\apply_norm.py", "--bak _临时/norm_bak", "--bak 归档/临时/norm_bak"),
    (r"采集工具\py\build.py", 'SKIP_DIRS = {"_合并前备份", "_重复版本"}', 'SKIP_DIRS = {"_校勘版"}'),
    (r"采集工具\py\dedupe_apply.py", 'DST = ROOT / "_重复版本" / "去重"', 'DST = ROOT / "归档" / "重复_根级" / "去重"'),
    (r"采集工具\py\dedupe_apply.py", "移到 _重复版本/去重/", "移到 归档/重复_根级/去重/"),
    (r"采集工具\py\extract.py", '"归档/临时/txt"', '"归档/临时/txt"'),  # 占位，见下
    (r"采集工具\py\extract.py", '"_临时/txt"', '"归档/临时/txt"'),
    (r"采集工具\py\extract.py", "--dir _临时/html --outdir _临时/txt", "--dir 归档/临时/html --outdir 归档/临时/txt"),
    (r"采集工具\py\harvest_filters.py", '"_临时/sonovel/SoNovel/rules"', '"归档/参考项目/SoNovel/SoNovel/rules"'),
    (r"采集工具\py\harvest_filters.py", "--rules _临时/sonovel/SoNovel/rules", "--rules 归档/参考项目/SoNovel/SoNovel/rules"),
    (r"采集工具\py\ocr.py", "--dir _临时/shot --outdir _临时/ocr", "--dir 归档/临时/shot --outdir 归档/临时/ocr"),
    # ---- 校勘脚本自身排除表 ----
    (r"采集工具\校勘\classify.py", 'EXCLUDE_DIRS = {"_重复版本", "_合并前备份", "_临时", "_非H同人_隔离"}', 'EXCLUDE_DIRS = {"归档", "_校勘版", "_legacy"}'),
    (r"采集工具\校勘\preview_fix.py", 'EXCLUDE_DIRS = {"_重复版本", "_合并前备份", "_临时", "_非H同人_隔离"}', 'EXCLUDE_DIRS = {"归档", "_校勘版", "_legacy"}'),
    # ---- legacy ----
    (r"采集工具\_legacy\入库规范化.ps1", r"Join-Path $Root '书目索引.csv'", r"Join-Path $Root '文档\书目索引.csv'"),
]

# 需要真正写入的文件编码：全部 UTF-8 无 BOM
def main() -> int:
    missing: list[str] = []
    skipped: list[tuple[str, str]] = []
    touched: dict[str, int] = {}

    for rel, old, new in RULES:
        if old == new:
            continue
        p = ROOT / rel
        if not p.exists():
            missing.append(rel)
            continue
        raw = p.read_bytes()
        bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig")
        n = text.count(old)
        if n == 0:
            skipped.append((rel, old[:40]))
            continue
        text = text.replace(old, new)
        p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))
        touched[rel] = touched.get(rel, 0) + n

    print("=== 改动文件 ===")
    for rel, n in sorted(touched.items()):
        print(f"  {n:2d} 处  {rel}")
    print(f"\n共 {len(touched)} 个文件, {sum(touched.values())} 处替换")

    if skipped:
        print("\n=== 未命中（旧串不存在，需人工确认） ===")
        for rel, frag in skipped:
            print(f"  {rel}  << {frag}")
    if missing:
        print("\n=== 文件不存在 ===")
        for rel in missing:
            print(f"  {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
