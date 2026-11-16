# -*- coding: utf-8 -*-
"""LLM 层：OpenAI 兼容端点 + 结构化输出 + 并发 + 记账 + 预算熔断。

只用官方 openai SDK，不引 LiteLLM（38MB）也不用 Instructor（为 3000 次一次性补全
引入一层 DSL 不值）。协议就是 Chat Completions，换 provider 只改 config 的 base_url。
"""
from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from .config import LLMConfig


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0


class LLM:
    def __init__(self, cfg: LLMConfig, ledger=None, run_id: int | None = None,
                 stage: str = "", on_call: Callable | None = None):
        key = cfg.resolve_key()
        if not key:
            raise RuntimeError(
                f"没有可用的 API key：请在环境变量 {cfg.api_key_env} 里设置，"
                f"或在 agent/config.toml 的 [llm].api_key 直接填写。"
            )
        from openai import OpenAI, DefaultHttpxClient

        self.cfg = cfg
        self.client = OpenAI(
            api_key=key,
            base_url=cfg.base_url,
            timeout=cfg.timeout,
            max_retries=0,                       # 重试自己控制，便于记账与退避
            http_client=DefaultHttpxClient(limits=None),
        )
        self.ledger = ledger
        self.run_id = run_id
        self.stage = stage
        self._lock = threading.Lock()
        self.usage = Usage()

    # ---------- 记账 ----------
    def _record(self, tag: str, tin: int, tout: int, ok: bool, attempts: int,
                prompt_ver: str = "") -> float:
        cost = self.cfg.cost(tin, tout)
        with self._lock:
            self.usage.tokens_in += tin
            self.usage.tokens_out += tout
            self.usage.cost += cost
            if self.ledger is not None:
                self.ledger.log_ai(self.run_id, self.stage, tag, self.cfg.model,
                                   prompt_ver, tin, tout, cost, ok, attempts)
            if self.cfg.max_usd_per_run and self.usage.cost > self.cfg.max_usd_per_run:
                raise BudgetExceeded(
                    f"本次运行已花费 ${self.usage.cost:.3f}，超过上限 "
                    f"${self.cfg.max_usd_per_run:.2f}，停止。"
                )
        return cost

    # ---------- 主调用 ----------
    def chat(self, messages: list[dict], *, tag: str = "", prompt_ver: str = "",
             schema: dict | None = None, max_tokens: int | None = None,
             temperature: float | None = None) -> str:
        last_err = None
        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                kwargs: dict[str, Any] = {
                    "model": self.cfg.model,
                    "messages": messages,
                    "temperature": self.cfg.temperature if temperature is None else temperature,
                    "max_tokens": max_tokens or self.cfg.max_tokens,
                }
                if schema:
                    kwargs["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {"name": "result", "schema": schema, "strict": True},
                    }
                r = self.client.chat.completions.create(**kwargs)
                text = (r.choices[0].message.content or "").strip()
                u = r.usage
                self._record(tag, u.prompt_tokens if u else 0,
                             u.completion_tokens if u else 0, True, attempt, prompt_ver)
                return text
            except BudgetExceeded:
                raise
            except Exception as e:                   # noqa: BLE001
                last_err = e
                msg = str(e)
                # 429 / 超时 / 5xx 退避重试；4xx 其它（参数错、鉴权）直接抛
                retriable = any(s in msg for s in ("429", "timeout", "Timeout", "500",
                                                   "502", "503", "504", "overloaded"))
                if attempt < self.cfg.max_retries and retriable:
                    time.sleep(min(2 ** attempt, 20))
                    continue
                self._record(tag, 0, 0, False, attempt, prompt_ver)
                raise
        raise RuntimeError(f"调用失败：{last_err}")

    def chat_json(self, messages: list[dict], schema: dict, *, tag: str = "",
                  prompt_ver: str = "", max_tokens: int | None = None) -> Any:
        text = self.chat(messages, tag=tag, prompt_ver=prompt_ver, schema=schema,
                         max_tokens=max_tokens)
        return parse_json(text)

    # ---------- 并发 ----------
    def map(self, items: list, fn: Callable, workers: int | None = None) -> list:
        """按顺序返回结果；单个失败记 None，不拖垮整批。"""
        n = workers or self.cfg.concurrency
        with ThreadPoolExecutor(max_workers=max(1, n)) as ex:
            return list(ex.map(fn, items))


def parse_json(text: str) -> Any:
    """容错解析：模型偶尔会包 ```json 围栏或前后加解释。"""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # 退一步：抓第一个完整的 JSON 对象/数组
    for pat in (r"\{.*\}", r"\[.*\]"):
        m = re.search(pat, t, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
    raise ValueError(f"模型返回不是合法 JSON：{text[:300]}")
