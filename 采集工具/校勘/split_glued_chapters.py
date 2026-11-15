# -*- coding: utf-8 -*-
"""切分「原文本身就粘连」的章标题（第N章标题正文连成一行）。

覆盖不到的一律不动，只出清单 —— 破句的代价远高于不切。

用法：
    python split_glued_chapters.py --dry            # 只看统计与样本
    python split_glued_chapters.py --dry --file 绝世唐门
    python split_glued_chapters.py                  # 写 校勘版_chap2，并从 校勘版_chap 全量镜像
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"F:\新建文件夹\read - 副本")
SRC = ROOT / "校勘版_chap"
OUT = ROOT / "校勘版_chap2"
REPORT = ROOT / "采集工具" / "记录" / "章标题切分.json"

CHAP = re.compile(r"第[0-9零一二三四五六七八九十百千两]{1,6}[章节回]")

# 双字句首（强信号）
START2 = (
    "这是 那是 他是 她是 它是 他们 她们 它 我们 你们 新的一天 一阵 一声 一股 一位 一个 一片 一缕 一丝 "
    "一双 一只 一场 一群 一具 一名 一道 一切 一天 一日 当下 此时 此刻 随后 接着 正当 位于 时间 自从 "
    "原来 话说 却说 闻言 看见 听到 感觉 感受 只见 天空 空气 夜色 月光 阳光 清晨 傍晚 夜里 次日 翌日 "
    "数日 半月 次日一早 与此 同时 与此同 与此同 与此同"
).split()

# 单字句首（弱信号，只在没有强信号时用）
START1 = set("他她它我你此这在当随于位每从自就而可但接正")

# 明显属于标题的字（标题里常见）
TITLE_HINT = set("之丶·录篇记传序章回")

BAD_TAIL = set("的了着过和与及而则就都也又还且并但却是在被把让给对向从于之其此很更最")

MAX_TITLE = 26
MIN_TITLE = 3


def find_cut(line: str, off: int):
    """line[off:] 是紧跟在「第N章」后面的文本。返回切点相对 off 的长度，或 None。"""
    seg = line[off:]
    if len(seg) <= MIN_TITLE:
        return None
    lo, hi = MIN_TITLE, min(MAX_TITLE, len(seg) - 2)
    strong = []
    weak = []
    for k in range(lo, hi + 1):
        head = seg[:k]
        nxt2 = seg[k:k + 2]
        nxt1 = seg[k]
        # 标题不该以虚词收尾
        if head[-1] in BAD_TAIL:
            continue
        # 标题内标点不超过 1 个
        if sum(1 for c in head if c in "，。！？；：") > 1:
            continue
        if any(s and seg.startswith(s, k) for s in START2):
            strong.append(k)
        elif nxt1 in START1:
            weak.append(k)
    if strong:
        return strong[0]
    if weak:
        return weak[0]
    return None


def main() -> int:
    dry = "--dry" in sys.argv
    only = None
    if "--file" in sys.argv:
        only = sys.argv[sys.argv.index("--file") + 1]

    if not dry:
        shutil.copytree(SRC, OUT, dirs_exist_ok=True)

    stats = Counter()
    files = []
    samples = []

    for p in sorted(SRC.rglob("*.txt")):
        rel = p.relative_to(SRC)
        if only and only not in str(rel):
            continue
        raw = p.open("r", encoding="utf-8", errors="replace", newline="").read()
        lines = raw.split("\n")
        out_lines = []
        n_cut = 0
        n_skip = 0
        for ln in lines:
            m = CHAP.match(ln)
            if not m or len(ln) <= 40:
                out_lines.append(ln)
                continue
            off = m.end()
            k = find_cut(ln, off)
            if k is None:
                n_skip += 1
                if len(samples) < 40:
                    samples.append({"file": str(rel), "kind": "NO_CUT", "text": ln[:90]})
                out_lines.append(ln)
                continue
            head = ln[:off + k].rstrip()
            tail = ln[off + k:]
            n_cut += 1
            if len(samples) < 40:
                samples.append({"file": str(rel), "kind": "CUT",
                                "title": head, "body": tail[:60]})
            out_lines.append(head)
            out_lines.append("")
            out_lines.append(tail)

        if n_cut:
            files.append({"file": str(rel), "cut": n_cut, "skip": n_skip})
            if not dry:
                dst = OUT / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.open("w", encoding="utf-8", newline="").write("\n".join(out_lines))
        stats["cut"] += n_cut
        stats["skip"] += n_skip
        stats["files"] += 1

    print(f"{'[DRY] ' if dry else ''}files={len(files)} cut={stats['cut']} skip={stats['skip']}")
    files.sort(key=lambda x: -x["cut"])
    for f in files[:10]:
        print(f"  {f['cut']:4d} 切 skip={f['skip']:3d}  {f['file']}")
    for s in samples:
        if s["kind"] == "CUT":
            print(f"\n  [切] {s['file']}\n      标题 |{s['title']}|\n      正文 |{s['body']}|")
    if not dry:
        REPORT.write_text(json.dumps({"stats": dict(stats), "files": files,
                                      "samples": samples}, ensure_ascii=False, indent=1),
                          encoding="utf-8")
        print(f"\n输出 -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
