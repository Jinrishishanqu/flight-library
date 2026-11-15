# -*- coding: utf-8 -*-
"""按具体作品归类 辰东/ 下的文件；判不出的留在 待归类/。

三棵树的子目录一律是具体作品，不允许「辰东」这种作者合集目录；
「待归类」是唯一允许的兜底目录。

判定顺序：人工裁定表 OVERRIDE（文件名关键词）优先 → pixiv 名单 → 关键词打分。
用法：python classify_source.py [--apply]
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"F:\新建文件夹\read - 副本")
TREES = ["原文", "校对后文章", "校勘版"]
FOLDERS = ["辰东", "待归类"]

# 人工裁定：文件名包含 key → 作品（逐个读过开头 300 字确认，见 文档\校对规则.md）
OVERRIDE = [
    ("天璇喋血", "神墓"),          # 辰南与澹台璇
    ("狠人大帝(1)", "完美世界"),   # 石昊身旁的神秘女子、俞陀古祖
    ("妖妖成奴", "遮天"),          # 屠圣的年轻强者、二百多位神子圣女拍卖
    ("海豚的尾巴", "遮天"),        # 天皇子不灭天皇、青诗仙子、伊轻舞
    ("清月无边", "完美世界"),      # 月婵 / 清漪 主身之争
    ("清月之难", "完美世界"),      # 九天十地、帝关、石昊、孟天正
    ("曲墨封枪挑颜如玉", "遮天"),  # 叶凡、颜如玉、谢晓峰
    ("丝袜美腿的完美世界", "待归类"),  # 林方、宇宙创始淫神 —— 挂名原创
    ("路人英雄", "待归类"),          # pixiv 原创
    ("被卖到柳青坊", "待归类"),      # pixiv 原创
    ("东厂督主", "待归类"),          # 「只手遮天」误命中「遮天」
    ("石村", "完美世界"),          # 石村是完美世界地名
    ("光影迷局", "待归类"),
    ("深宫龙椅残雪怨", "待归类"),
]

WORKS = {
    "遮天": ["遮天", "叶凡", "姬紫月", "庞博", "黑皇", "段德", "秦瑶", "梵仙",
             "李小曼", "华云飞", "伊轻舞", "姜洛神", "颜如玉", "天璇", "姬皓月",
             "涂飞", "老疯子", "姬家", "紫月", "瑶池", "北斗", "天皇子", "青诗"],
    "完美世界": ["完美世界", "石昊", "火灵儿", "清漪", "王曦", "叶倾仙", "补天", "柳神",
                 "云曦", "月婵", "天角蚁", "荒奴", "石村", "上苍", "孟天正", "帝关"],
    "神墓": ["神墓", "辰南", "雨馨", "龙舞", "紫金神龙", "古天路", "回龙饮露", "澹台璇"],
    "不死不灭": ["不死不灭", "不死凤王", "醉品双娇"],
}


def read_head(p: Path, n: int = 4000) -> str:
    for enc in ("utf-8", "gb18030", "utf-16"):
        try:
            with p.open("r", encoding=enc, errors="strict", newline="") as f:
                return f.read(n)
        except (UnicodeDecodeError, UnicodeError):
            continue
    with p.open("r", encoding="utf-8", errors="replace", newline="") as f:
        return f.read(n)


def override_of(name: str) -> str | None:
    for key, work in OVERRIDE:
        if key in name:
            return work
    return None


def classify(p: Path) -> tuple[str, str]:
    name = p.stem
    hit = override_of(name)
    if hit:
        return hit, "人工裁定"
    text = name + "\n" + read_head(p)
    scores = {w: sum(text.count(k) for k in kws) for w, kws in WORKS.items()}
    best = max(scores, key=lambda k: scores[k])
    detail = " ".join(f"{k}={v}" for k, v in sorted(scores.items(), key=lambda x: -x[1]))
    if scores[best] < 2:
        return "待归类", f"无匹配（{detail}）"
    return best, detail


def main() -> int:
    apply = "--apply" in sys.argv
    plan: list[tuple[str, str, str]] = []
    for tree in TREES:
        for folder in FOLDERS:
            d = ROOT / tree / folder
            if not d.exists():
                continue
            for p in sorted(d.glob("*.txt")):
                target, why = classify(p)
                plan.append((f"{tree}\\{folder}\\{p.name}", target, why))

    for rel, target, why in plan:
        print(f"{target:<6} | {rel} | {why}")
    print()
    print("统计:", Counter(t for _, t, _ in plan))

    if apply:
        moved = 0
        for rel, target, _ in plan:
            src = ROOT / rel
            if not src.exists():
                continue
            tree = rel.split("\\")[0]
            dest_dir = ROOT / tree / target
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / src.name
            if dest.exists():
                print("已存在，跳过:", dest)
                continue
            src.rename(dest)
            moved += 1
        print("已移动", moved, "个文件")
        for tree in TREES:
            for folder in FOLDERS:
                d = ROOT / tree / folder
                if d.exists() and not any(d.iterdir()):
                    d.rmdir()
                    print("删空目录", d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
