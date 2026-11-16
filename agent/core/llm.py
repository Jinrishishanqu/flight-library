# -*- coding: utf-8 -*-
"""LLM 层：OpenAI 兼容端点 + 结构化输出 + 并发 + 记账 + 预算熔断。

为什么只用官方 openai SDK：
  LiteLLM 光 wheel 就 38MB，还带 tokenizers / boto3，它的花费统计藏在内存 map 里，
  关掉进程就没了；Instructor 是给「几百次交互式补全」设计的一层 DSL，而本项目的
  调用都是「一批离线任务、结果落盘」，多一层抽象只是多一处出错点。
  协议就是 Chat Completions —— 换 provider 只改 config 的 base_url + model。

一次调用的完整链路：
  Stage(ai) → LLM.chat() → OpenAI.chat.completions.create()
      → _record() 把 token / 费用写进 ledger.ai_calls
      → 返回文本；chat_json() 再用 parse_json() 转成对象
  Stage 负责把对象写成 state/out/<stage>/w<id>.json，
  入库是另一条命令（python -m agent apply bio）—— 生成与入库分离。
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
    """本次运行的花费超过 cfg.max_usd_per_run。runner 会把它当致命错误中断整条流水线。"""


@dataclass
class Usage:
    """本次 LLM 实例（= 一个 stage 的一次执行）的累计用量。"""

    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0


class LLM:
    """一个 stage 一个实例；内部线程安全（并发时共享同一份 usage 计数）。"""

    def __init__(self, cfg: LLMConfig, ledger=None, run_id: int | None = None,
                 stage: str = "", on_call: Callable | None = None):
        # ---- 第一步永远是确认 key 存在 ----
        # 没有 key 就在构造时炸，而不是跑到一半才发现：AI 环节的失败要早、要清楚
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
            base_url=cfg.base_url,               # ← 换 provider 只靠这一行
            timeout=cfg.timeout,
            max_retries=0,                       # 重试自己控制：SDK 的自动重试看不到 token 记账
            http_client=DefaultHttpxClient(limits=None),   # 交给外面的线程池控并发
        )
        self.ledger = ledger          # core.ledger.Ledger，可为 None（比如手动试跑）
        self.run_id = run_id
        self.stage = stage
        self._lock = threading.Lock() # usage 与台账写入的互斥锁
        self.usage = Usage()

    # ---------- 记账 ----------
    def _record(self, tag: str, tin: int, tout: int, ok: bool, attempts: int,
                prompt_ver: str = "") -> float:
        """把一次调用的 token 与费用写进台账，并检查预算。

        tag 是业务标签（work:443 / char:张小凡 / proof:21457），
        有了它才能回答「这个角色的 bio 花了多少钱」。
        失败的调用也记一条（tin/tout=0），否则重试次数无从统计。
        """
        cost = self.cfg.cost(tin, tout)
        with self._lock:
            self.usage.tokens_in += tin
            self.usage.tokens_out += tout
            self.usage.cost += cost
            if self.ledger is not None:
                self.ledger.log_ai(self.run_id, self.stage, tag, self.cfg.model,
                                   prompt_ver, tin, tout, cost, ok, attempts)
            # 熔断：注意是在「记完账之后」抛，所以超支的那一笔一定留痕
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
        """发一次 Chat Completions，返回纯文本。

        messages   : [{"role": "system"|"user", "content": "..."}]
        schema     : 传了就用 response_format=json_schema(strict) 强约束输出结构。
                     服务端不支持时这里会 400 —— 那种情况下删掉 schema 参数，
                     靠 parse_json 的容错去剥 ```json 围栏。
        tag/prompt_ver : 只进台账，不发给模型。
        """
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
                    # strict=True 要求 schema 里每个 object 都有 additionalProperties: False
                    # 且 required 列全 —— _schema() 已经保证了这一点
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
                raise                                    # 预算不是「错误」，不重试
            except Exception as e:                       # noqa: BLE001
                last_err = e
                msg = str(e)
                # 只有「限流 / 超时 / 服务端抖动」值得重试；
                # 4xx 里其它情况（key 错、模型名错、schema 不合法）重试一万次也一样
                retriable = any(s in msg for s in ("429", "timeout", "Timeout", "500",
                                                   "502", "503", "504", "overloaded"))
                if attempt < self.cfg.max_retries and retriable:
                    time.sleep(min(2 ** attempt, 20))    # 2s, 4s, 8s… 封顶 20s
                    continue
                self._record(tag, 0, 0, False, attempt, prompt_ver)
                raise
        raise RuntimeError(f"调用失败：{last_err}")

    def chat_json(self, messages: list[dict], schema: dict, *, tag: str = "",
                  prompt_ver: str = "", max_tokens: int | None = None) -> Any:
        """chat() + parse_json()。schema 既做服务端强约束，也做客户端兜底解析。"""
        text = self.chat(messages, tag=tag, prompt_ver=prompt_ver, schema=schema,
                         max_tokens=max_tokens)
        return parse_json(text)

    # ---------- 并发 ----------
    def map(self, items: list, fn: Callable, workers: int | None = None) -> list:
        """按输入顺序返回结果；单个任务抛异常会变成 None 而不会中断整批。

        这里用线程池而不是 asyncio：任务体 99% 的时间在等 HTTP，线程足够，
        而且 fn 里会同步读 SQLite，协程反而要处处 await 化。
        """
        n = workers or self.cfg.concurrency
        with ThreadPoolExecutor(max_workers=max(1, n)) as ex:
            return list(ex.map(fn, items))


def parse_json(text: str) -> Any:
    """容错解析模型输出。

    即使有 json_schema 约束，模型偶尔也会：
      - 外面包一层 ```json 围栏
      - 前后多一句「好的，以下是结果：」
      - 把长字符串里的换行写成裸换行（这是最常见的坏 JSON 来源）
    第三种情况这里修不了，只能靠 prompt 里强调转义；前两种在这里兜住。
    """
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # 退一步：抓第一个完整的 JSON 对象 / 数组（re.S 让 . 跨行）
    for pat in (r"\{.*\}", r"\[.*\]"):
        m = re.search(pat, t, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
    raise ValueError(f"模型返回不是合法 JSON：{text[:300]}")
