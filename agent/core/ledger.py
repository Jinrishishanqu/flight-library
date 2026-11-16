# -*- coding: utf-8 -*-
"""台账：每次运行、每个环节、每次 AI 调用都落 SQLite。

为什么自己记而不靠框架：
  - 幂等的 key 必须是「业务指纹」（输入文件哈希 + prompt 版本 + 模型 + 参数），
    框架的缓存只认它自己定义的输入对象；
  - 成本必须按作品归集、按次运行熔断，这是业务需求，框架不管钱。
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline    TEXT NOT NULL,
    status      TEXT NOT NULL,              -- running / ok / failed / aborted
    started_at  REAL NOT NULL,
    ended_at    REAL,
    args        TEXT,
    note        TEXT
);
CREATE TABLE IF NOT EXISTS steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL,
    stage       TEXT NOT NULL,
    status      TEXT NOT NULL,              -- running / ok / failed / skipped
    dedupe_key  TEXT,
    started_at  REAL NOT NULL,
    ended_at    REAL,
    duration    REAL,
    detail      TEXT,
    log_path    TEXT,
    FOREIGN KEY(run_id) REFERENCES runs(id)
);
CREATE TABLE IF NOT EXISTS ai_calls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER,
    stage       TEXT,
    tag         TEXT,                        -- 业务标签，如 work:443 / char:张小凡
    model       TEXT,
    prompt_ver  TEXT,
    tokens_in   INTEGER,
    tokens_out  INTEGER,
    cost_usd    REAL,
    ok          INTEGER,
    attempts    INTEGER,
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
    def __init__(self, db: Path):
        db.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------- run ----------
    def start_run(self, pipeline: str, args: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO runs(pipeline,status,started_at,args) VALUES(?,?,?,?)",
            (pipeline, "running", time.time(), args),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def end_run(self, run_id: int, status: str, note: str = "") -> None:
        self.conn.execute(
            "UPDATE runs SET status=?, ended_at=?, note=? WHERE id=?",
            (status, time.time(), note, run_id),
        )
        self.conn.commit()

    # ---------- step ----------
    def start_step(self, run_id: int, stage: str, key: str | None) -> int:
        cur = self.conn.execute(
            "INSERT INTO steps(run_id,stage,status,dedupe_key,started_at) VALUES(?,?,?,?,?)",
            (run_id, stage, "running", key, time.time()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def end_step(self, step_id: int, status: str, detail: str = "", log_path: str = "") -> None:
        row = self.conn.execute(
            "SELECT started_at FROM steps WHERE id=?", (step_id,)
        ).fetchone()
        dur = time.time() - (row["started_at"] if row else time.time())
        self.conn.execute(
            "UPDATE steps SET status=?, ended_at=?, duration=?, detail=?, log_path=? WHERE id=?",
            (status, time.time(), dur, detail[:4000], log_path, step_id),
        )
        self.conn.commit()

    def hit_ok(self, key: str) -> bool:
        """同 key 曾经成功过 —— 幂等跳过的依据。"""
        row = self.conn.execute(
            "SELECT 1 FROM steps WHERE dedupe_key=? AND status='ok' LIMIT 1", (key,)
        ).fetchone()
        return row is not None

    # ---------- ai ----------
    def log_ai(self, run_id, stage, tag, model, prompt_ver, tin, tout, cost, ok, attempts):
        self.conn.execute(
            "INSERT INTO ai_calls(run_id,stage,tag,model,prompt_ver,tokens_in,tokens_out,"
            "cost_usd,ok,attempts,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, stage, tag, model, prompt_ver, tin, tout, cost, int(ok), attempts,
             time.time()),
        )
        self.conn.commit()

    def spent(self, run_id: int) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd),0) FROM ai_calls WHERE run_id=?", (run_id,)
        ).fetchone()
        return float(row[0])

    def spent_total(self) -> float:
        row = self.conn.execute("SELECT COALESCE(SUM(cost_usd),0) FROM ai_calls").fetchone()
        return float(row[0])

    # ---------- artifact ----------
    def log_artifact(self, run_id, stage, path: Path, sha: str, size: int):
        self.conn.execute(
            "INSERT INTO artifacts(run_id,stage,path,sha256,bytes,created_at) VALUES(?,?,?,?,?,?)",
            (run_id, stage, str(path), sha, size, time.time()),
        )
        self.conn.commit()

    # ---------- 报表 ----------
    def recent_runs(self, limit: int = 10):
        return self.conn.execute(
            "SELECT id,pipeline,status,started_at,ended_at,note FROM runs "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def run_steps(self, run_id: int):
        return self.conn.execute(
            "SELECT stage,status,duration,detail FROM steps WHERE run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()

    @contextmanager
    def tx(self):
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
