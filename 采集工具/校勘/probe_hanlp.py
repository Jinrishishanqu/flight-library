# -*- coding: utf-8 -*-
"""hanlp 分词 + NER 实测：验证自造人名召回与误报抑制。

用法：python probe_hanlp.py [文件] [--chars N]
不传文件则用内置例句。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SAMPLE = (
    "萧炎望着那萧家少年，云韵轻轻叹了口气，帕子掩住唇边。"
    "花晓镜与叶泠泠站在石阶上，凛月卿走过来，把玉佩塞进沈砚之手里。"
    "苏晚棠和柳如烟对视一眼，云澈与郑吒、楚轩都明白方才发生了什么。"
    "药老低声道：「闻言斗灵，暴露了。」高贵地抬了抬下巴。"
)


def load_pipe():
    import hanlp

    print("加载 tok / ner 模型（首次会下载约 95MB）…", flush=True)
    t0 = time.time()
    tok = hanlp.load(hanlp.pretrained.tok.COARSE_ELECTRA_SMALL_ZH)
    ner = hanlp.load(hanlp.pretrained.ner.MSRA_NER_ELECTRA_SMALL_ZH)
    pipe = (
        hanlp.pipeline()
        .append(tok, output_key="tok")
        .append(ner, input_key="tok", output_key="ner")
    )
    print(f"模型就绪 {time.time() - t0:.1f}s", flush=True)
    return pipe


def persons(doc) -> list[str]:
    """doc 可以是 dict（含 'ner'）或直接是 ner 列表。"""
    ner = doc["ner"] if isinstance(doc, dict) else doc
    out = []
    for item in ner:
        # 实测为四元组 (text, label, start, end)
        text, label = item[0], item[1]
        if label == "PERSON":
            out.append(text)
    return out


def main() -> int:
    text = SAMPLE
    n = 20000
    args = [a for a in sys.argv[1:]]
    if "--chars" in args:
        i = args.index("--chars")
        n = int(args[i + 1])
        del args[i : i + 2]
    if args:
        fp = Path(args[0])
        if not fp.is_absolute():
            fp = ROOT / fp
        raw = fp.open("r", encoding="utf-8", errors="replace", newline="").read()
        text = raw.replace("\r\n", "\n")[:n]
        print(f"语料：{fp.name} 取前 {len(text)} 字")

    pipe = load_pipe()

    # 例句
    doc = pipe(SAMPLE)
    ps = persons(doc)
    print("\n=== 例句 ===")
    print("PERSON:", ps)
    print("全部实体:", [(i[1], i[0]) for i in doc["ner"] if i[1] != "PERSON"][:12])

    if text is SAMPLE:
        return 0

    # 长文本：按 500 字切块批量跑
    t0 = time.time()
    chunks = [text[i : i + 500] for i in range(0, len(text), 500)]
    docs = pipe(chunks, batch_size=8)
    if isinstance(docs, dict):
        ner_list = docs["ner"]
    else:
        ner_list = [d["ner"] if isinstance(d, dict) else d for d in docs]
    dt = time.time() - t0
    from collections import Counter

    cnt: Counter[str] = Counter()
    for ner in ner_list:
        for p in persons(ner):
            cnt[p] += 1
    total = sum(cnt.values())
    print(f"\n=== 长文本 ===\n{len(text)} 字 / {len(chunks)} 块 / {dt:.1f}s "
          f"→ {len(text) / max(dt, 1e-6):.0f} 字/秒")
    print(f"PERSON 提及 {total} / 去重 {len(cnt)}")
    for w, c in cnt.most_common(40):
        print(f"  {w}\t{c}")
    print(f"\n估算全库 18,466,370 字单进程：{18466370 / max(len(text) / max(dt, 1e-6), 1) / 3600:.1f} 小时")
    return 0


if __name__ == "__main__":
    sys.exit(main())
