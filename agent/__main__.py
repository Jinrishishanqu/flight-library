# -*- coding: utf-8 -*-
"""`python -m agent <命令>` —— 统一入口。

  run <pipeline> [环节...] [--force] [--dry]   跑流水线（可只跑指定环节）
  list                                         列出所有环节与依赖
  status [n]                                   最近 n 次运行
  report <run_id>                              某次运行的逐环节明细
  apply bio|summary|proof [--dry]              把 state/out 里的 AI 产物入进库
  cost [n]                                     最近 n 次的花费

只有 apply 与 cost 在这里实现，其余转发给 core.runner.main ——
因为 apply 动的是「数据库」，而 run/status/report 动的是「台账」，
两者职责不同，放在一处会互相牵连。
"""
from __future__ import annotations

import sys

from .core import apply as apply_mod
from .core.config import load
from .core.runner import Runner, main as runner_main


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "status"     # 不带参数时给最常用的 view

    if cmd == "apply":
        # 生成与入库分离：AI 环节只负责把 JSON 写进 state/out/，
        # 这里负责把它们读出来落库 —— 所以「只想重入一次」不需要重新调 API。
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
        # 按运行列出花费。单价在 config.toml 的 [llm] 里，改模型要同步改单价，
        # 否则这里的数字是错的（台账存的是当时算好的 cost_usd）。
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
