# -*- coding: utf-8 -*-
"""可读性重排：只插入段落边界，不改动任何字符。

规则 A  第N章 标记若不在行首，前面补段落边界（章标题不再被吞进正文）
规则 B  超长段（> MIN_SPLIT）按句末标点切成 TARGET_* 字一段
规则 C  「」对话整体不拆（若引号内内容在 MAX_SEG 内，等闭引号后再切）
规则 D  只插换行，删掉全部 \r\n 后与原文件逐字节相同 —— 可逆

用法：
    python reflow.py --only "校勘版\斗破\《斗破苍穹老乞丐》-1~80-41.7w.txt"
    python reflow.py                       # 全库 → 校勘版_reflow\
"""
import argparse
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "校勘版")
OUT = os.path.join(ROOT, "校勘版_reflow")

# 切分阈值（字符数，含标点）
MIN_SPLIT = 220        # 短于此的段落不动
TARGET_MIN = 60        # 一段大致不少于这么多字
TARGET_MAX = 170       # 争取在这个长度内断开
HARD_MAX = 260         # 实在找不到标点，到这就硬切

CHAP = re.compile(r"第[0-9零一二三四五六七八九十百千两]+[章节回]")
# 句末：句号/叹号/问号/省略号/闭引号/闭书名号
SENT_END = "。！？…」』）"
# 硬切点（次要标点）
SOFT_END = "，；、：—～·"
# 切点后若紧跟这些字，说明句子没说完（「…而」+「的肉棒」），不能切
BAD_HEAD = set("的地得着了过而则就都也又还且并但却是在被把让给对向从于之其此该很更最与和")


def _head_ok(s, j):
    """检查切在下标 j 之后是否合理：看下一段的头两个字。"""
    if j + 1 >= len(s):
        return True
    if s[j + 1] in BAD_HEAD:
        return False
    return True


def split_para(s):
    """把一个超长段切成若干段，返回段落列表。只按标点切，不增删字符。"""
    out = []
    n = len(s)
    i = 0
    while i < n:
        remain = n - i
        if remain <= MIN_SPLIT:
            out.append(s[i:])
            break

        depth = 0          # 「」嵌套层数
        cut = -1           # 句末切点
        soft = -1          # 逗号切点
        j = i
        limit = min(n, i + HARD_MAX)
        while j < limit:
            c = s[j]
            if c == "「":
                if depth == 0:
                    # 只在明确的领起标点之后才把对话独立起段：
                    # 「说道：」「喝道，」「说完。」—— 避免把「发出「嗯嗯」声」拆开
                    prev = s[j - 1] if j > i else ""
                    pos = j - i
                    if pos >= TARGET_MIN and prev in "。！？…」，：；":
                        cut = pos
                        break
                depth += 1
            elif c == "」":
                if depth > 0:
                    depth -= 1
                if depth == 0:
                    pos = j - i + 1
                    if pos >= TARGET_MIN:
                        cut = pos
                        if pos >= TARGET_MAX:
                            break
            elif depth == 0:
                pos = j - i + 1
                if c in SENT_END:
                    if pos >= TARGET_MIN:
                        cut = pos
                        if pos >= TARGET_MAX:
                            break
                elif c in SOFT_END and pos >= TARGET_MAX:
                    if _head_ok(s, j):
                        soft = pos
                        break
                    # 切点不好（后面接「的」「了」等），继续往后找
            j += 1

        if cut > 0:
            out.append(s[i:i + cut])
            i += cut
        elif soft > 0:
            out.append(s[i:i + soft])
            i += soft
        else:
            # 既无句末也无好逗号：退到窗口内最靠后的标点，实在没有才硬切
            seg = s[i + TARGET_MIN:i + HARD_MAX]
            m = None
            for m in re.finditer(r"[。！？…」，；、：]", seg):
                pass
            if m:
                cut = i + TARGET_MIN + m.end()
                out.append(s[i:cut])
                i = cut
            else:
                out.append(s[i:i + HARD_MAX])
                i += HARD_MAX
    return [p for p in out if p.strip()]


def reflow_text(t, st):
    """t 为原始文本（保留 \r\n）。返回重排后的文本。"""
    # 规则 A：第N章 不在行首 → 前面补空行
    def _a(m):
        st["A_chap"] += 1
        return "\r\n\r\n" + m.group(0)

    t = re.sub(r"(?<![\r\n])" + CHAP.pattern, _a, t)

    # 统一换行，逐段处理
    t = t.replace("\r\n", "\n")
    lines = t.split("\n")
    out = []
    for line in lines:
        s = line.rstrip()
        if not s.strip():
            out.append("")
            continue
        L = len(s)
        if L <= MIN_SPLIT:
            out.append(s)
            continue
        parts = split_para(s)
        if len(parts) <= 1:
            out.append(s)
            continue
        st["B_split_para"] += 1
        st["B_new_paras"] += len(parts) - 1
        for p in parts:
            out.append(p)
            out.append("")
        out.pop()          # 去掉最后多插的空行
    res = "\n".join(out)
    # 收敛 3 个以上连续空行为 1 个空行
    res = re.sub(r"\n{3,}", "\n\n", res)
    # 保持原文件的 CRLF 风格
    return res.replace("\n", "\r\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    if args.only:
        files = [args.only if os.path.isabs(args.only) else os.path.join(ROOT, args.only)]
        outroot = args.out
    else:
        files = []
        for dirpath, _d, fns in os.walk(SRC):
            for fn in fns:
                if fn.endswith(".txt"):
                    files.append(os.path.join(dirpath, fn))
        outroot = args.out

    total = {"files": 0, "changed": 0, "A_chap": 0, "B_split_para": 0, "B_new_paras": 0,
             "chars_in": 0, "chars_out": 0, "bad": 0}
    report = []

    for fp in files:
        with open(fp, "r", encoding="utf-8", errors="replace", newline="") as f:
            raw = f.read()
        st = {"A_chap": 0, "B_split_para": 0, "B_new_paras": 0}
        new = reflow_text(raw, st)

        # 规则 D 校验：去掉所有空白后必须逐字相同
        a = re.sub(r"\s+", "", raw)
        b = re.sub(r"\s+", "", new)
        ok = (a == b)
        if not ok:
            total["bad"] += 1
            print(f"[FAIL] 字符不一致，跳过：{fp}")
            continue

        total["files"] += 1
        total["chars_in"] += len(raw)
        total["chars_out"] += len(new)
        for k in ("A_chap", "B_split_para", "B_new_paras"):
            total[k] += st[k]

        if new != raw:
            total["changed"] += 1
            report.append((st["A_chap"], st["B_split_para"], st["B_new_paras"], fp))

        dest = fp if outroot is None else os.path.join(outroot, os.path.relpath(fp, SRC))
        if outroot is not None or new != raw:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8", newline="") as f:
                f.write(new)

    print(f"files={total['files']} changed={total['changed']} bad={total['bad']}")
    print(f"A_chap={total['A_chap']}  B_split_para={total['B_split_para']}  "
          f"B_new_paras={total['B_new_paras']}")
    print(f"chars {total['chars_in']} -> {total['chars_out']} "
          f"(+{total['chars_out'] - total['chars_in']})")
    report.sort(reverse=True)
    print("\n改动最大的 10 个文件：")
    for a_, b_, c_, fp in report[:10]:
        print(f"  章{a_:5d} 段{b_:5d} 新增段{c_:6d}  {os.path.relpath(fp, ROOT)}")


if __name__ == "__main__":
    main()
