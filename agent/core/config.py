# -*- coding: utf-8 -*-
"""配置读取层：把 agent/config.toml 解析成带默认值的 dataclass，路径统一转绝对路径。

设计约束：
  1. 所有路径以「项目根」为基准解析，因此 agent/ 整个目录可以挪位置而不用改代码；
  2. 缺省值必须能直接跑通（只有 API key 必须由使用者提供）；
  3. 不读环境变量以外的外部状态 —— 同一份 config.toml + 同一份语料 = 同一份结果。

调用关系：config.load() → Runner() → 每个 Stage 的 Ctx.cfg。
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# AGENT_DIR = .../agent（本文件在 agent/core/ 下，向上两级）
AGENT_DIR = Path(__file__).resolve().parent.parent
# ROOT = 项目根（agent 的上一级），语料三层、采集工具、文档都在它下面
ROOT = AGENT_DIR.parent
CONFIG_PATH = AGENT_DIR / "config.toml"


@dataclass
class LLMConfig:
    """AI 调用的全部参数。改这里就够了，不用碰代码。

    ---- 怎么配（最短路径）----
    1) 用 OpenAI 官方：把 key 放进环境变量 OPENAI_API_KEY，其余保持默认；
    2) 用第三方 OpenAI 兼容服务（DeepSeek / 通义 / Kimi / 中转站 / 本地 vLLM）：
       改 base_url 与 model 两项，价格按该服务商标价改两个 price 字段；
    3) 不想用环境变量：直接在 config.toml 的 [llm] 里写 api_key = "sk-..."（该文件已在 .gitignore 外，注意别提交）。
    """

    # 端点根地址，末尾带 /v1。官方是 https://api.openai.com/v1
    # 换 provider 只改这一行 + model，代码里没有任何 OpenAI 私有假设
    base_url: str = "https://api.openai.com/v1"

    # 模型名。必须支持 Chat Completions 与 response_format=json_schema
    # （不支持 json_schema 的服务会报 400，此时把 stages/ai.py 的 schema 参数去掉改用 parse_json 兜底）
    model: str = "gpt-4o-mini"

    # 两种给 key 的方式，resolve_key() 里「显式 api_key」优先于环境变量
    api_key: str = ""
    api_key_env: str = "OPENAI_API_KEY"

    # 生成参数：temperature 高一点更适合写小传（0.7）；做校对类可降到 0.2
    temperature: float = 0.7
    max_tokens: int = 3000

    # 单次 HTTP 超时（秒）与最大尝试次数（含首次）。重试只对 429/超时/5xx 生效
    timeout: int = 120
    max_retries: int = 3

    # 并发线程数。本地脚本跑 6 路一般不会被限流；被限流就调小或加大 max_retries
    concurrency: int = 6

    # 单价（美元 / 百万 token），用于把 token 折算成钱 → 台账里能按作品归集成本
    # 默认值对应 gpt-4o-mini（输入 0.15 / 输出 0.60）。换模型务必同步改，否则账算错
    price_in_per_mtok: float = 0.15
    price_out_per_mtok: float = 0.60

    # 单次运行的花费上限（美元）。超过就抛 BudgetExceeded，整条流水线停住
    # 设 0 表示不限额
    max_usd_per_run: float = 5.0

    # 结构化输出的约束方式，决定 request 里 response_format 长什么样：
    #   json_schema —— {"type":"json_schema", ...}，服务端照 schema 生成。
    #                  OpenAI、部分兼容网关支持。
    #   json_object —— {"type":"json_object"}，只保证是合法 JSON，
    #                  schema 以文字塞进对话末尾，靠 parse_json + 人工核对兜底。
    #                  **DeepSeek 只支持这个**：传 json_schema 会 400
    #                  「This response_format type is unavailable now」（实测）。
    #   none        —— 不设约束，纯文本。
    json_mode: str = "json_schema"

    def resolve_key(self) -> str:
        """显式 api_key 优先，其次环境变量。空字符串表示没配。"""
        return self.api_key or os.environ.get(self.api_key_env, "")

    def cost(self, tin: int, tout: int) -> float:
        """按 token 数算钱。台账里每条 ai_calls 都存这个值。"""
        return (tin * self.price_in_per_mtok + tout * self.price_out_per_mtok) / 1_000_000


@dataclass
class Paths:
    """全部路径。默认值即仓库现状，config.toml 的 [paths] 段可逐项覆盖。"""

    root: Path = ROOT                              # 项目根
    canon: Path = ROOT / "校勘版"                   # S2+S3 成品（入库的唯一来源）
    proof: Path = ROOT / "校对后文章"                # S1 排版层（清洗的输入）
    source: Path = ROOT / "原文"                    # 冻结源库（只读）
    db: Path = ROOT / "采集工具" / "书库" / "data" / "library.db"
    state: Path = AGENT_DIR / "state"              # 台账、日志、AI 产物都在这
    artifacts: Path = AGENT_DIR / "state" / "artifacts"
    logs: Path = AGENT_DIR / "state" / "logs"


@dataclass
class Config:
    """Runner 拿到的完整配置：路径 + AI 参数 + 环节归类 + 幂等开关。"""

    paths: Paths = field(default_factory=Paths)
    llm: LLMConfig = field(default_factory=LLMConfig)
    stages: dict[str, str] = field(default_factory=dict)   # {环节名: script|ai|hybrid}，仅作速查
    idempotent: bool = True                                # False 时每次都真跑

    @property
    def ledger_db(self) -> Path:
        return self.paths.state / "ledger.db"


def load(path: Path | None = None) -> Config:
    """读 config.toml 并补默认值；顺带把 state / artifacts / logs 三个目录建好。

    只覆盖认识的键（hasattr 判断），所以 toml 里写错字段名不会炸，只是被忽略 ——
    调试时用 `python -m agent list` 之前先看一遍 config 是否被读到。
    """
    p = path or CONFIG_PATH
    raw = tomllib.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    # ---- [paths] ----
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

    # ---- [llm] ----
    llm = LLMConfig()
    if "llm" in raw:
        for k, v in raw["llm"].items():
            if hasattr(llm, k):
                setattr(llm, k, v)

    # ---- [stages] / [run] ----
    cfg = Config(paths=paths, llm=llm)
    cfg.stages = dict(raw.get("stages", {}))
    cfg.idempotent = bool(raw.get("run", {}).get("idempotent", True))

    # 台账与日志的落盘目录必须在第一次写入前存在
    for d in (paths.state, paths.artifacts, paths.logs):
        d.mkdir(parents=True, exist_ok=True)
    return cfg
