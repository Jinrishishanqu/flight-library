# -*- coding: utf-8 -*-
"""`python -m agent <命令>`。

  run <pipeline> [环节...] [--force] [--dry]   跑流水线（可只跑指定环节）
  list                                         列出所有环节与依赖
  status [n]                                   最近 n 次运行
  report <run_id>                              某次运行的逐环节明细
  apply bio|summary|proof [--dry]              把 state/out 里的 AI 产物入进库
  cost [n]                                     最近 n 次的花费
"""
from __future__ import annotations

import sys

from .core import apply as apply_mod
from .core.config import load
from .core.runner import Runner, main as runner_main


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "status"

    if cmd == "apply":
        cfg = load()
        what = argv[1] if len(argv) > 1 else "bio"
        dry = "--dry" in argv
        d = cfg.paths.state / "out" / ("bio" if what == "bio" else what)
        fn = {"bio": apply_mod.apply_bio,
              "summary": apply_mod.apply_summary,
              "proof": apply_mod.apply_proof}.get(what)
        if not fn:
            print("apply 只支持 bio / summary / proof")
            return 2
        print(fn(cfg, d, dry=dry))
        return 0

    if cmd == "cost":
        r = Runner()
        n = int(argv[1]) if len(argv) > 1 else 10
        rows = r.ledger.recent_runs(n)
        total = 0.0
        for row in rows:
            c = r.ledger.spent(row["id"])
            total += c
            print(f"run {row['id']:>4}  {row['pipeline']:<12} ${c:.4f}")
        print(f"合计 ${total:.4f}")
        return 0

    return runner_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
