# -*- coding: utf-8 -*-
"""配置：读 agent/config.toml，路径一律解析成绝对路径。"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent      # .../agent
ROOT = AGENT_DIR.parent                                # 项目根
CONFIG_PATH = AGENT_DIR / "config.toml"


@dataclass
class LLMConfig:
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key: str = ""
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 0.7
    max_tokens: int = 3000
    timeout: int = 120
    max_retries: int = 3
    concurrency: int = 6
    price_in_per_mtok: float = 0.15
    price_out_per_mtok: float = 0.60
    max_usd_per_run: float = 5.0

    def resolve_key(self) -> str:
        return self.api_key or os.environ.get(self.api_key_env, "")

    def cost(self, tin: int, tout: int) -> float:
        return (tin * self.price_in_per_mtok + tout * self.price_out_per_mtok) / 1_000_000


@dataclass
class Paths:
    root: Path = ROOT
    canon: Path = ROOT / "校勘版"
    proof: Path = ROOT / "校对后文章"
    source: Path = ROOT / "原文"
    db: Path = ROOT / "采集工具" / "书库" / "data" / "library.db"
    state: Path = AGENT_DIR / "state"
    artifacts: Path = AGENT_DIR / "state" / "artifacts"
    logs: Path = AGENT_DIR / "state" / "logs"


@dataclass
class Config:
    paths: Paths = field(default_factory=Paths)
    llm: LLMConfig = field(default_factory=LLMConfig)
    stages: dict[str, str] = field(default_factory=dict)
    idempotent: bool = True

    @property
    def ledger_db(self) -> Path:
        return self.paths.state / "ledger.db"


def load(path: Path | None = None) -> Config:
    p = path or CONFIG_PATH
    raw = tomllib.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    paths = Paths()
    if "paths" in raw:
        d = raw["paths"]
        paths = Paths(
            root=ROOT,
            canon=ROOT / d.get("canon", "校勘版"),
            proof=ROOT / d.get("proof", "校对后文章"),
            source=ROOT / d.get("source", "原文"),
            db=ROOT / d.get("db", "采集工具/书库/data/library.db"),
            state=AGENT_DIR / d.get("state", "state"),
            artifacts=AGENT_DIR / d.get("artifacts", "state/artifacts"),
            logs=AGENT_DIR / d.get("log_dir", "state/logs"),
        )

    llm = LLMConfig()
    if "llm" in raw:
        for k, v in raw["llm"].items():
            if hasattr(llm, k):
                setattr(llm, k, v)

    cfg = Config(paths=paths, llm=llm)
    cfg.stages = dict(raw.get("stages", {}))
    cfg.idempotent = bool(raw.get("run", {}).get("idempotent", True))

    for d in (paths.state, paths.artifacts, paths.logs):
        d.mkdir(parents=True, exist_ok=True)
    return cfg
