# -*- coding: utf-8 -*-
"""统一清洗工具：把 ftfy / confusables / regex 的正确用法固定下来。

★ 关键：ftfy.fix_text() 默认 fix_character_width=True，会把全角标点（：？！（））
  压成半角，对中文排版是破坏。本项目一律用 fix_character_width=False。

功能：
  clean(s)         — mojibake 修复 + HTML 实体 + 控制符 + 零宽字符（不动全角标点）
  wide_to_narrow(s)— 只把全角「数字/字母」转半角，标点一律不动
  skeleton(s)      — UTS #39 同形字归一，仅用于比对与检测
  audit(s)         — 返回问题清单 [(类型, 数量, 样例)]

命令行：
  python clean_text.py check <dir>     # 体检，不改文件
  python clean_text.py apply <dir>     — 写 <dir>_clean（保留原目录）
"""
from __future__ import annotations

import collections
import pathlib
import re
import sys
import unicodedata

ROOT = pathlib.Path(r"F:\新建文件夹\read - 副本")
CONF = ROOT / "采集工具" / "词库" / "confusables.txt"

# 全角 ASCII 变体 → 半角，只用于「字母与数字」，标点单独处理
FW_ALNUM = {chr(0xFF10 + i): str(i) for i in range(10)}
FW_ALNUM.update({chr(0xFF21 + i): chr(0x41 + i) for i in range(26)})
FW_ALNUM.update({chr(0xFF41 + i): chr(0x61 + i) for i in range(26)})

ZERO_WIDTH = re.compile("[\u200b-\u200f\u2060\ufeff\u00ad]")
CTRL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
HAN = re.compile(r"[\u4e00-\u9fff]")


def _ftfy():
    try:
        import ftfy
        return ftfy
    except ImportError:
        return None


def clean(s: str) -> str:
    """安全清洗：只修编码与不可见字符，绝不改标点宽度。"""
    ftfy = _ftfy()
    if ftfy is not None:
        s = ftfy.fix_text(s, fix_character_width=False)
    s = ZERO_WIDTH.sub("", s)
    s = CTRL.sub("", s)
    return s


def wide_to_narrow(s: str) -> str:
    """全角数字/字母 → 半角。不动 ，。：？！（） 等标点。"""
    return "".join(FW_ALNUM.get(ch, ch) for ch in s)


_tbl: dict[str, str] | None = None


def _conf_table() -> dict[str, str]:
    global _tbl
    if _tbl is not None:
        return _tbl
    m: dict[str, str] = {}
    if CONF.exists():
        for line in CONF.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(";")]
            if len(parts) < 2 or " " in parts[0]:
                continue
            try:
                m[chr(int(parts[0], 16))] = "".join(chr(int(x, 16)) for x in parts[1].split())
            except ValueError:
                pass
    _tbl = m
    return m


def skeleton(s: str, rounds: int = 3) -> str:
    t = _conf_table()
    if not t:
        return s
    for _ in range(rounds):
        nxt = "".join(t.get(c, c) for c in s)
        if nxt == s:
            break
        s = nxt
    return s


CJK_PUNCT = set("，。、；：？！“”‘’「」『』（）【】《》〈〉…—～·　")


def audit(s: str) -> list[tuple[str, int, str]]:
    """返回 [(类型, 数量, 首个上下文样例)]"""
    out: list[tuple[str, int, str]] = []

    def ctx(m: re.Match) -> str:
        a = max(0, m.start() - 10)
        return s[a:m.end() + 10].replace("\n", "\\n").replace("\r", "")

    checks = [
        ("mojibake", re.compile("[\u00c0-\u00ff]{2,}|[ÃÂâ€]{2,}|锟斤拷|烫烫烫|屯屯屯|鐨勬|涓€")),
        ("U+FFFD", re.compile("\ufffd+")),
        ("零宽/软连字符", ZERO_WIDTH),
        ("控制符", CTRL),
        ("全角ASCII字母数字", re.compile("[\uff10-\uff19\uff21-\uff3a\uff41-\uff5a]+")),
        ("私有区字符", re.compile("[\ue000-\uf8ff]+")),
        ("全角引号残留", re.compile("\uff02|\uff07")),
    ]
    for name, pat in checks:
        ms = list(pat.finditer(s))
        if ms:
            out.append((name, sum(len(m.group(0)) for m in ms), ctx(ms[0])))

    # 同形字：skeleton 变动且落到汉字
    odd = collections.Counter()
    sample = ""
    for ch in set(s):
        if ch in CJK_PUNCT or ch in "\r\n\t" or "\u4e00" <= ch <= "\u9fff":
            continue
        sk = skeleton(ch)
        if sk != ch and sk and all("\u4e00" <= c <= "\u9fff" for c in sk):
            i = s.find(ch)
            if not sample:
                sample = s[max(0, i - 10): i + 10]
            odd[ch] = s.count(ch)
    if odd:
        out.append(("同形字(伪装汉字)", sum(odd.values()), "".join(odd.keys()) + " | " + sample.replace("\n", "\\n")))

    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    mode = sys.argv[1]
    base = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "校勘版"
    files = sorted(base.rglob("*.txt"))
    if mode == "check":
        total = 0
        for fp in files:
            t = fp.open("r", encoding="utf-8", errors="replace", newline="").read()
            issues = audit(t)
            if issues:
                total += 1
                print(f"{fp.relative_to(base)}")
                for name, n, sample in issues:
                    print(f"   {name}: {n} 次 | {sample[:60]}")
        print(f"\n有问题的文件 {total} / {len(files)}")
        return 0
    if mode == "apply":
        dest = base.parent / (base.name + "_clean")
        changed = 0
        for fp in files:
            raw = fp.open("r", encoding="utf-8", errors="replace", newline="").read()
            new = clean(raw)
            rel = fp.relative_to(base)
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.open("w", encoding="utf-8", newline="").write(new)
            if new != raw:
                changed += 1
                print(f"  改动 {rel}: {len(raw)} -> {len(new)}")
        print(f"写出 {dest}（{len(files)} 文件，{changed} 个有改动）")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
