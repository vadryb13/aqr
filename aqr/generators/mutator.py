"""Mutator: комбинирует топ-блоки в новые композиции."""
from __future__ import annotations
import json, litellm, uuid, random
from .base import BaseGenerator
from ..db.schema import get_conn


MUTATOR_PROMPT = """Ты quant-исследователь. Возьми ДВЕ работающие стратегии и создай {n} НОВЫХ композиций, объединяющих их логику.

Стратегия A: {a_hyp} (Sharpe {a_sharpe})
Стратегия B: {b_hyp} (Sharpe {b_sharpe})

Правила комбинирования:
1. AND: сигнал только когда обе стратегии совпадают
2. Filter: одна выдаёт сигнал, другая — фильтр контекста (regime, vol, hour)
3. Portfolio: 50/50 или динамические веса
4. Sequential: A решает entry, B решает exit

Верни {n} комбинаций как composite стратегии.

JSON: {{"combinations": [{{"hypothesis": "...", "rationale": "почему комбо работает лучше суммы частей", "block_name": "composite", "params": {{"mode": "and|filter|portfolio|sequential", "a": "...", "b": "..."}}, "assets": [...], "timeframe": "...", "category": "composite", "expected_sharpe": 0.0}}]}}
"""


class Mutator(BaseGenerator):
    async def fetch_context(self) -> dict:
        conn = get_conn(read_only=True)
        winners = conn.execute("""
            SELECT h.id, h.hypothesis, r.sharpe FROM hypotheses h
            JOIN backtest_results r ON h.id = r.hypothesis_id
            WHERE r.sharpe > 3
            ORDER BY r.tested_at DESC LIMIT 50
        """).fetchall()
        conn.close()
        return {"winners": winners}

    async def generate(self, ctx: dict) -> tuple[list[dict], float]:
        if len(ctx["winners"]) < 2:
            return [], 0.0
        a, b = random.sample(ctx["winners"], 2)
        prompt = MUTATOR_PROMPT.format(
            n=self.cfg.max_hyp_per_call,
            a_hyp=a[1], a_sharpe=a[2], b_hyp=b[1], b_sharpe=b[2],
        )
        resp = await litellm.acompletion(
            model=self.cfg.model, temperature=self.cfg.temperature,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        cost = resp._hidden_params.get("response_cost", 0.002)
        try:
            data = json.loads(resp.choices[0].message.content)
            combos = data.get("combinations", [])
            for c in combos:
                c.setdefault("id", str(uuid.uuid4()))
                c["seed_hypothesis_id"] = a[0]  # первичный seed
            return combos, cost
        except Exception:
            return [], cost
