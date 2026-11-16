# -*- coding: utf-8 -*-
"""Runner：按声明顺序跑 Stage，带幂等跳过、质量门禁、日志落盘、失败即停。

为什么不用 Prefect / Airflow / Dagster：
  这里每一步流动的是「磁盘上的文件 + SQLite 里的一行数据」，不是内存里传递的
  DataFrame。框架的 checkpoint / 重放 / 参数化在这种形态下都是空转（它要在节点间
  搬运的只是几个路径字符串），而它解决不了的几件事仍然要自己写：
    · 业务指纹幂等（输入 = 作品正文 + 提示词版本 + 模型）
    · 按作品归集成本、按次运行熔断
    · 中文质量门禁（字数区间、空正文、角色超限）
  三百行 DAG 足够覆盖，而且每一步的花费都能直接问 ledger。

执行语义：
  · 顺序 = stages.ALL 的声明顺序（不是 needs 的拓扑序）—— 因为数据依赖已经在库里
  · 幂等 = 同 dedupe_key 曾成功过则跳过；--force 关闭
  · 失败 = 记录到台账后立即中断整条流水线（不带病往下跑）
  · dry  = 只打印将要做的事，不写台账、不执行
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

from .config import Config, load
from .ledger import Ledger
from .stage import Ctx, Stage


class Runner:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or load()
        # 台账与日志都在 agent/state 下；Ledger 构造时会建表
        self.ledger = Ledger(self.cfg.paths.state / "ledger.db")
        self.log_dir = self.cfg.paths.state / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.lines: list[str] = []      # 攒起来最后一次性写文件

    # ---------- 日志 ----------
    def log(self, msg: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        line = f"[{stamp}] {msg}"
        self.lines.append(line)
        print(line, flush=True)          # flush：长任务时想立刻看到进度

    def flush_log(self, run_id: int) -> Path:
        """把本次运行的全部日志写成 state/logs/run_<id>.log（失败也要写）。"""
        p = self.log_dir / f"run_{run_id}.log"
        p.write_text("\n".join(self.lines), encoding="utf-8")
        return p

    # ---------- 环节挑选 ----------
    @staticmethod
    def order(stages: list[Stage], only: list[str] | None, skip: list[str]) -> list[Stage]:
        """按声明顺序过滤出本次要跑的环节。

        注意 only 不会自动带上依赖：数据已经在库里，重跑某一步不该连带重算全库。
        （早期版本会自动带 needs，结果是「只想补 bio」变成跑半条链，已改掉。）
        要全跑就省略环节名，或指定 pipeline（pipelines/*.toml 里的 stages）。
        """
        by_name = {s.name: s for s in stages}
        if only:
            unknown = [n for n in only if n not in by_name]
            if unknown:
                raise RuntimeError(f"没有这些环节：{', '.join(unknown)}")
            picked = [s for s in stages if s.name in only]
        else:
            picked = list(stages)
        return [s for s in picked if s.name not in skip]

    # ---------- 主循环 ----------
    def run(self, pipeline: str, stages: list[Stage], *, only: list[str] | None = None,
            skip: list[str] | None = None, force: bool = False,
            dry: bool = False) -> int:
        """跑一条流水线，返回进程退出码（0 成功 / 1 中断）。"""
        skip = skip or []
        seq = self.order(stages, only, skip)
        args = f"only={only} skip={skip} force={force} dry={dry}"
        run_id = 0 if dry else self.ledger.start_run(pipeline, args)
        self.log(f"pipeline={pipeline} run={run_id or '(dry)'} 环节 {len(seq)} 个："
                 f"{' → '.join(s.name for s in seq)}")

        ok_count = skip_count = fail_count = 0
        try:
            for st in seq:
                ctx = Ctx(cfg=self.cfg, ledger=self.ledger, run_id=run_id,
                          stage=st.name, force=force, log=self.log)
                key = st.dedupe_key(ctx)
                self.log(f"  ▸ {st.name}  [{st.kind}]  key={key[:12]}  {st.description}")

                # ---- 幂等跳过 ----
                if not force and self.cfg.idempotent and self.ledger.hit_ok(key):
                    self.log(f"    跳过：同指纹已成功过（--force 可强制重跑）")
                    if not dry:
                        sid = self.ledger.start_step(run_id, st.name, key)
                        self.ledger.end_step(sid, "skipped", "同指纹已成功")
                    skip_count += 1
                    continue

                if dry:
                    ok_count += 1
                    continue

                # ---- 真跑 ----
                sid = self.ledger.start_step(run_id, st.name, key)
                t0 = time.time()
                try:
                    detail = st.run(ctx) or ""
                    # 门禁：跑完立刻验收，不合格就当失败（不许「跑完就算过」）
                    if st.check:
                        good, msg = st.check(ctx)
                        if not good:
                            raise RuntimeError(f"门禁未过：{msg}")
                        detail = (detail + " | 门禁：" + msg).strip(" |")
                    self.ledger.end_step(sid, "ok", detail)
                    self.log(f"    ok {time.time() - t0:.1f}s  {detail[:160]}")
                    ok_count += 1
                except Exception as e:                       # noqa: BLE001
                    # 失败也记台账（含 traceback 尾部），然后向上抛 → 中断整条流水线
                    self.ledger.end_step(sid, "failed", f"{e}\n{traceback.format_exc()[-1500:]}")
                    self.log(f"    失败：{e}")
                    fail_count += 1
                    raise
            self.ledger.end_run(run_id, "ok",
                                f"ok={ok_count} skip={skip_count} fail={fail_count}")
            return 0
        except Exception as e:                               # noqa: BLE001
            self.log(f"流水线中断：{type(e).__name__}: {e}")
            self.log(traceback.format_exc()[-1200:])
            if run_id:
                self.ledger.end_run(run_id, "failed", f"ok={ok_count} fail={fail_count}")
            return 1
        finally:
            # 无论成功失败都落日志、都报花费 —— 中途失败时这段尤其重要
            if run_id:
                p = self.flush_log(run_id)
                self.log(f"日志 -> {p}")
                self.log(f"花费：本次 ${self.ledger.spent(run_id):.4f} / "
                         f"累计 ${self.ledger.spent_total():.4f}")

    # ---------- 报表 ----------
    def status(self, limit: int = 10) -> None:
        """`python -m agent status`：最近几次运行的总览。"""
        rows = self.ledger.recent_runs(limit)
        if not rows:
            print("还没有运行记录。")
            return
        print(f"{'run':>4}  {'状态':<8} {'开始':<20} {'流水线':<16} 备注")
        for r in rows:
            t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["started_at"]))
            print(f"{r['id']:>4}  {r['status']:<8} {t:<20} {r['pipeline']:<16} {r['note'] or ''}")

    def report(self, run_id: int) -> None:
        """`python -m agent report <id>`：某次运行的逐环节明细与花费。"""
        for s in self.ledger.run_steps(run_id):
            d = (s["duration"] or 0)
            print(f"  {s['stage']:<16} {s['status']:<8} {d:>8.1f}s  {(s['detail'] or '')[:120]}")
        print(f"本次花费 ${self.ledger.spent(run_id):.4f}")


def main(argv: list[str] | None = None) -> int:
    """命令分发（run / list / status / report）。apply 与 cost 在 agent/__main__.py。"""
    from .. import stages as stage_mod

    argv = argv or sys.argv[1:]
    cmd = argv[0] if argv else "status"
    r = Runner()

    if cmd == "status":
        r.status()
        return 0
    if cmd == "report":
        r.report(int(argv[1]))
        return 0
    if cmd == "list":
        # 列出全部环节：名字 / 类型 / 依赖 / 说明 —— 加新环节后先用它确认已注册
        for s in stage_mod.ALL:
            print(f"  {s.name:<16} {s.kind:<7} needs={','.join(s.needs) or '-':<22} {s.description}")
        return 0
    if cmd == "run":
        pipeline = argv[1] if len(argv) > 1 else "lib"
        only = [x for x in argv[2:] if not x.startswith("-")]
        flags = [x for x in argv[2:] if x.startswith("-")]
        if not only:
            # 命令行没点名环节时，用 pipelines/<name>.toml 里的 stages 列表
            f = stage_mod.PIPE_DIR / f"{pipeline}.toml"
            if f.exists():
                import tomllib
                only = list(tomllib.loads(f.read_text(encoding="utf-8")).get("stages") or [])
        return r.run(pipeline, stage_mod.ALL,
                     only=only or None,
                     force="--force" in flags,
                     dry="--dry" in flags)
    print(__doc__)
    return 2
