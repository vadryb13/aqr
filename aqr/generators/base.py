"""Базовый класс LLM-генератора: long-running task с backpressure."""
from __future__ import annotations
import asyncio, logging, os, uuid, time
from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel

from ..queue.streams import HypothesisProducer, get_redis
from ..db.schema import get_conn
from ..db.dedup import SemanticDedup

log = logging.getLogger(__name__)


class GeneratorConfig(BaseModel):
    name: str
    generator_type: str
    model: str = "claude-haiku-4"
    temperature: float = 0.8
    max_hyp_per_call: int = 10
    calls_per_minute: int = 30       # target rate
    daily_budget_usd: float = 10.0
    version: str = "v1.0"


class BaseGenerator(ABC):
    """
    Long-running: infinite loop через:
      fetch_context → LLM.generate → dedup → DB insert → Redis push
    """

    def __init__(self, cfg: GeneratorConfig):
        self.cfg = cfg
        self.dedup: Optional[SemanticDedup] = None
        self.producer: Optional[HypothesisProducer] = None
        self.paused = False
        self.total_cost = 0.0
        self.total_generated = 0
        self.total_duplicates = 0

    async def start(self):
        self.dedup = SemanticDedup()
        r = await get_redis()
        self.producer = HypothesisProducer(r)
        log.info(f"[{self.cfg.name}] starting, target rate {self.cfg.calls_per_minute}/min")

        while True:
            try:
                if self.paused:
                    await asyncio.sleep(5)
                    continue
                if self.total_cost >= self.cfg.daily_budget_usd:
                    log.warning(f"[{self.cfg.name}] daily budget hit ${self.total_cost:.2f}")
                    await asyncio.sleep(300)
                    continue

                # Backpressure
                bp = await self.producer.backpressure_wait()
                if bp > 1:
                    log.info(f"[{self.cfg.name}] backpressure, wait {bp}x")
                    await asyncio.sleep(bp * 2)
                    continue

                # 1. Собрать контекст (реализует subclass)
                ctx = await self.fetch_context()
                # 2. Сгенерировать пачку гипотез
                t0 = time.time()
                hyps, cost = await self.generate(ctx)
                dt_ms = int((time.time() - t0) * 1000)
                self.total_cost += cost
                self._log_llm_call(cost, len(hyps), dt_ms)

                # 3. Dedup + insert + push
                for h in hyps:
                    is_dup, _ = await self.dedup.is_duplicate(
                        h["hypothesis"] + " " + h.get("rationale", "")
                    )
                    if is_dup:
                        self.total_duplicates += 1
                        self._save_hypothesis(h, status="duplicate")
                        continue
                    self._save_hypothesis(h, status="pending")
                    await self.producer.push(h)
                    self.total_generated += 1

                # Rate control
                sleep = max(1.0, 60.0 / self.cfg.calls_per_minute)
                await asyncio.sleep(sleep)
            except Exception as e:
                log.exception(f"[{self.cfg.name}] error: {e}")
                await asyncio.sleep(10)

    @abstractmethod
    async def fetch_context(self) -> dict:
        """Каждый субкласс собирает свой контекст из DB."""
        ...

    @abstractmethod
    async def generate(self, ctx: dict) -> tuple[list[dict], float]:
        """Возвращает (список гипотез, cost_usd)."""
        ...

    # ─── DB helpers ───

    def _save_hypothesis(self, h: dict, status: str = "pending"):
        conn = get_conn()
        try:
            conn.execute("""
                INSERT INTO hypotheses (
                    id, generator_type, generator_version,
                    hypothesis, rationale, category, assets, timeframe,
                    block_name, params, expected_sharpe,
                    seed_hypothesis_id, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                h.get("id") or str(uuid.uuid4()),
                self.cfg.generator_type, self.cfg.version,
                h.get("hypothesis"), h.get("rationale"),
                h.get("category"), h.get("assets"), h.get("timeframe"),
                h.get("block_name"), h.get("params", {}),
                h.get("expected_sharpe"), h.get("seed_hypothesis_id"),
                status,
            ])
        finally:
            conn.close()

    def _log_llm_call(self, cost: float, n_hyp: int, latency_ms: int):
        conn = get_conn()
        try:
            conn.execute("""
                INSERT INTO llm_calls (id, generator_type, model, cost_usd, latency_ms, n_hypotheses)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [str(uuid.uuid4()), self.cfg.generator_type,
                  self.cfg.model, cost, latency_ms, n_hyp])
        finally:
            conn.close()

    def pause(self): self.paused = True
    def resume(self): self.paused = False
