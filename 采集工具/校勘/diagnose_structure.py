# -*- coding: utf-8 -*-
"""诊断结构问题：章标题粘连、过长句、过长段、章开头重复。

用法：
    python diagnose_structure.py [目录] [--top N]
默认目录 = 校勘版
输出：采集工具\记录\结构诊断.json + 控制台摘要
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"F:\新建文件夹\read - 副本")
DEFAULT_DIR = ROOT / "校勘版"
OUT = ROOT / "采集工具" / "记录" / "结构诊断.json"

CHAP = re.compile(r"第[0-9零一二三四五六七八九十百千两]+[章节回]")
SENT_END = "。！？…！?」』\"'"
# 正文常见的段落/章节起点词（用于判断「标题在这里结束、正文从这里开始」）
BODY_START = (
    "自从", "自从", "当", "这", "那", "在", "此", "第二", "翌日", "次日", "次日",
    "故事", "话说", "话说", "原来", "却说", "却说", "不", "有", "据", "不知",
    "时间", "三年", "十年", "百", "千", "万", "一", "二", "三", "四", "五",
    "六", "七", "八", "九", "十", "老", "小", "他", "她", "我", "你", "众",
    "众", "众", "所", "但", "而", "随", "到", "从", "自", "突", "忽", "猛",
)


def read(p: Path) -> str:
    return p.open("r", encoding="utf-8", errors="replace", newline="").read()


def classify_chapter_lines(text: str):
    """返回 (分类计数, 粘连样本)"""
    stat = Counter()
    samples = []
    lines = text.split("\n")
    for ln, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue
        for m in CHAP.finditer(stripped):
            pos = m.start()
            after = stripped[m.end():]
            head = stripped[:pos]
            if pos == 0:
                # 行首
                if len(stripped) <= 40 and not any(c in stripped for c in SENT_END[:-2]):
                    stat["line_alone"] += 1
                else:
                    stat["line_glued"] += 1
                    if len(samples) < 40:
                        samples.append({
                            "file": None, "line": ln,
                            "text": stripped[:80],
                            "tail_after_chap": after[:40],
                        })
            else:
                stat["inline"] += 1
                if len(samples) < 40:
                    samples.append({
                        "file": None, "line": ln,
                        "text": stripped[max(0, pos - 20):pos + 40],
                        "tail_after_chap": after[:40],
                    })
    return stat, samples


def sentence_stats(text: str):
    """按句末标点切句，统计过长句"""
    c = Counter()
    longest = (0, "")
    for para in text.split("\n"):
        if not para.strip():
            continue
        buf = []
        for ch in para:
            buf.append(ch)
            if ch in SENT_END:
                s = "".join(buf).strip()
                buf = []
                if not s:
                    continue
                n = len(s)
                if n > 120:
                    c["sent_gt120"] += 1
                if n > 200:
                    c["sent_gt200"] += 1
                if n > 300:
                    c["sent_gt300"] += 1
                if n > longest[0]:
                    longest = (n, s[:100])
        tail = "".join(buf).strip()
        if len(tail) > 120:
            c["sent_tail_gt120"] += 1
    return c, longest


def para_stats(text: str):
    c = Counter()
    longest = (0, "")
    for para in text.split("\n"):
        s = para.strip()
        if not s:
            continue
        n = len(s)
        c["paras"] += 1
        if n > 150:
            c["para_gt150"] += 1
        if n > 250:
            c["para_gt250"] += 1
        if n > longest[0]:
            longest = (n, s[:80])
    return c, longest


def main() -> int:
    argv = sys.argv[1:]
    base = DEFAULT_DIR
    top = 10
    i = 0
    while i < len(argv):
        if argv[i] == "--top":
            top = int(argv[i + 1]); i += 2
        else:
            base = Path(argv[i]); i += 1

    files = sorted(base.rglob("*.txt"))
    total = Counter()
    per_file = []
    all_samples = []

    for p in files:
        t = read(p)
        cs, smp = classify_chapter_lines(t)
        ss, slong = sentence_stats(t)
        ps, plong = para_stats(t)
        row = {
            "file": str(p.relative_to(base)),
            "chars": len(t),
            **{f"chap_{k}": v for k, v in cs.items()},
            **dict(ss),
            **{f"par_{k}": v for k, v in ps.items()},
            "longest_sent": slong[0],
            "longest_sent_sample": slong[1],
            "longest_para": plong[0],
            "longest_para_sample": plong[1],
        }
        per_file.append(row)
        for k, v in row.items():
            if isinstance(v, int) and k not in ("chars", "longest_sent", "longest_para"):
                total[k] += v
        for s in smp:
            s["file"] = row["file"]
            all_samples.append(s)

    per_file.sort(key=lambda r: -(r.get("chap_line_glued", 0) * 100 + r.get("sent_gt200", 0)))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "base": str(base),
        "files": len(files),
        "totals": dict(total),
        "per_file": per_file,
        "glued_samples": all_samples[:60],
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"目录 {base}  文件 {len(files)}")
    for k, v in sorted(total.items()):
        print(f"  {k:20s} {v}")
    print("\n章标题粘连最多的文件：")
    for r in per_file[:top]:
        if r.get("chap_line_glued", 0) or r.get("chap_inline", 0):
            print(f"  glued={r.get('chap_line_glued',0):4d} inline={r.get('chap_inline',0):4d} "
                  f"sent>200={r.get('sent_gt200',0):4d}  {r['file']}")
    print(f"\n明细 -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
