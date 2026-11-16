# -*- coding: utf-8 -*-
"""台账：每次运行、每个环节、每次 AI 调用、每个产出文件都落进一个 SQLite。

为什么自己记而不靠框架：
  - 幂等的 key 必须是「业务指纹」（输入哈希 + 提示词版本 + 模型），
    框架的缓存只认它自己定义的输入对象，认不出「这是同一部作品的同一版正文」；
  - 成本必须按作品归集、按次运行熔断，这是业务需求，框架不管钱也不会留痕。

四张表：
  runs       一次流水线执行
  steps      一次执行里的每个环节（含被幂等跳过的）
  ai_calls   每次模型调用（token / 钱 / 是否成功 / 重试了几次 / 业务 tag）
  artifacts  产出文件（路径 + sha256 + 字节数）

查询示例：
  sqlite3 agent/state/ledger.db "SELECT tag, SUM(cost_usd) FROM ai_calls GROUP BY tag ORDER BY 2 DESC LIMIT 10"
"""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline    TEXT NOT NULL,              -- lib / canon / ai / full
    status      TEXT NOT NULL,              -- running / ok / failed
    started_at  REAL NOT NULL,
    ended_at    REAL,
    args        TEXT,                       -- only=/skip=/force=/dry= 原样记录
    note        TEXT                        -- 收尾时的 ok/skip/fail 计数
);
CREATE TABLE IF NOT EXISTS steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL,
    stage       TEXT NOT NULL,
    status      TEXT NOT NULL,              -- running / ok / failed / skipped
    dedupe_key  TEXT,                       -- 幂等依据；hit_ok() 按 status='ok' 命中
    started_at  REAL NOT NULL,
    ended_at    REAL,
    duration    REAL,
    detail      TEXT,                       -- run() 的返回值 + 门禁结论（截断 4000 字）
    log_path    TEXT,
    FOREIGN KEY(run_id) REFERENCES runs(id)
);
CREATE TABLE IF NOT EXISTS ai_calls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER,
    stage       TEXT,                       -- 哪个环节
    tag         TEXT,                       -- 业务标签：bio:443 / summary:19 / proof:21457
    model       TEXT,
    prompt_ver  TEXT,                       -- 提示词版本，改了 prompt 必须 bump
    tokens_in   INTEGER,
    tokens_out  INTEGER,
    cost_usd    REAL,                       -- 按 config 里的单价折算
    ok          INTEGER,                    -- 0/1；失败的调用也记，用于统计重试率
    attempts    INTEGER,                    -- 第几次尝试成功
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS artifacts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER,
    stage       TEXT,
    path        TEXT NOT NULL,
    sha256      TEXT,
    bytes       INTEGER,
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_steps_key ON steps(dedupe_key, status);
CREATE INDEX IF NOT EXISTS idx_ai_run ON ai_calls(run_id);
"""


class Ledger:
    """台账门面。所有方法都立刻 commit —— 中途崩溃也不能丢已完成步骤的记录。

    线程安全：AI 环节用 `LLM.map()` 在线程池里并发调模型，每次调用回写一行
    `ai_calls`，而连接是在主线程建的。sqlite3 默认 `check_same_thread=True`
    会直接抛 `ProgrammingError: SQLite objects created in a thread can only be
    used in that same thread` —— 所以这里关掉该检查，并用一把锁把写串行化
    （SQLite 本身也只允许单写者，串行不会损失什么）。
    """

    def __init__(self, db: Path):
        db.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db, timeout=30, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row            # 让查询结果能按列名取
        self._lock = threading.Lock()                  # 跨线程写串行化
        self.conn.executescript(SCHEMA)                # IF NOT EXISTS，重复打开无害
        self.conn.commit()

    def _exec(self, sql: str, args: tuple = (), commit: bool = True):
        """所有写入的唯一入口：加锁 → 执行 → 提交。"""
        with self._lock:
            cur = self.conn.execute(sql, args)
            if commit:
                self.conn.commit()
            return cur

    def _read(self, sql: str, args: tuple = ()):
        with self._lock:
            return self.conn.execute(sql, args)

    # ---------- run ----------
    def start_run(self, pipeline: str, args: str = "") -> int:
        cur = self._exec(
            "INSERT INTO runs(pipeline,status,started_at,args) VALUES(?,?,?,?)",
            (pipeline, "running", time.time(), args),
        )
        return int(cur.lastrowid)

    def end_run(self, run_id: int, status: str, note: str = "") -> None:
        self._exec(
            "UPDATE runs SET status=?, ended_at=?, note=? WHERE id=?",
            (status, time.time(), note, run_id),
        )

    # ---------- step ----------
    def start_step(self, run_id: int, stage: str, key: str | None) -> int:
        cur = self._exec(
            "INSERT INTO steps(run_id,stage,status,dedupe_key,started_at) VALUES(?,?,?,?,?)",
            (run_id, stage, "running", key, time.time()),
        )
        return int(cur.lastrowid)

    def end_step(self, step_id: int, status: str, detail: str = "", log_path: str = "") -> None:
        # duration 由 started_at 反算，不依赖调用方传时间
        row = self._read(
            "SELECT started_at FROM steps WHERE id=?", (step_id,)
        ).fetchone()
        dur = time.time() - (row["started_at"] if row else time.time())
        self._exec(
            "UPDATE steps SET status=?, ended_at=?, duration=?, detail=?, log_path=? WHERE id=?",
            (status, time.time(), dur, detail[:4000], log_path, step_id),
        )

    def hit_ok(self, key: str) -> bool:
        """同 key 曾经成功过 —— 幂等跳过的唯一依据。

        只看 status='ok'：失败或跳过的记录不构成「已经做过这件事」的证据。
        """
        row = self._read(
            "SELECT 1 FROM steps WHERE dedupe_key=? AND status='ok' LIMIT 1", (key,)
        ).fetchone()
        return row is not None

    # ---------- ai ----------
    def log_ai(self, run_id, stage, tag, model, prompt_ver, tin, tout, cost, ok, attempts):
        """记一次模型调用。成功失败都记，失败时 tin/tout 为 0。

        这个方法会被线程池里的并发调用同时打到，必须走 _exec 的锁。
        """
        self._exec(
            "INSERT INTO ai_calls(run_id,stage,tag,model,prompt_ver,tokens_in,tokens_out,"
            "cost_usd,ok,attempts,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, stage, tag, model, prompt_ver, tin, tout, cost, int(ok), attempts,
             time.time()),
        )

    def spent(self, run_id: int) -> float:
        """本次运行花了多少美元。"""
        row = self._read(
            "SELECT COALESCE(SUM(cost_usd),0) FROM ai_calls WHERE run_id=?", (run_id,)
        ).fetchone()
        return float(row[0])

    def spent_total(self) -> float:
        """有台账以来的累计花费。"""
        row = self._read("SELECT COALESCE(SUM(cost_usd),0) FROM ai_calls").fetchone()
        return float(row[0])

    # ---------- artifact ----------
    def log_artifact(self, run_id, stage, path: Path, sha: str, size: int):
        """记一个产出文件的路径与校验和（目前 apply 层还没批量调用，留给溯源用）。"""
        self._exec(
            "INSERT INTO artifacts(run_id,stage,path,sha256,bytes,created_at) VALUES(?,?,?,?,?,?)",
            (run_id, stage, str(path), sha, size, time.time()),
        )

    # ---------- 报表 ----------
    def recent_runs(self, limit: int = 10):
        return self._read(
            "SELECT id,pipeline,status,started_at,ended_at,note FROM runs "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def run_steps(self, run_id: int):
        return self._read(
            "SELECT stage,status,duration,detail FROM steps WHERE run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()

    @contextmanager
    def tx(self):
        """事务上下文：要么全成，要么全回滚。批量写时用。"""
        with self._lock:
            try:
                yield self.conn
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
