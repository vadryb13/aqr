"""Explorer: creative, ищет НОВЫЕ идеи."""
from __future__ import annotations
import json, litellm, uuid, random
from .base import BaseGenerator
from ..db.schema import get_conn


EXPLORER_PROMPT = """Ты quant-исследователь. Придумай {n} НОВЫХ гипотез для торговых стратегий на MOEX/global markets.

Уже протестировано (за последний час):
- Категории: {tested_categories}
- Топ Sharpe: {top_sharpes}
- Не повторяй эти идеи!

Активные инсайты:
{insights}

Доступные блоки (кратко):
- pair_z_fade(px_a, px_b, lookback, threshold): z-fade log-spread пары
- wide_range_fade(hi, lo, cl, k): fade широких дневных диапазонов
- momentum_breakout(px, lookback, k): пробой n-day high
- carry_arb(spot, futures, cost): arb на carry-разнице
- vol_target(px, target_vol): rebalance по vol

Создай {n} РАЗНЫХ гипотез, каждая с полем seed_category (что-то новое: sector rotation, cross-asset, calendar effect, microstructure, macro-hedge).

JSON: {{"hypotheses": [{{"hypothesis": "...", "rationale": "экономический смысл", "block_name": "...", "params": {{...}}, "assets": [...], "timeframe": "1d|1h|10m", "category": "...", "expected_sharpe": 0.0}}]}}
"""


class Explorer(BaseGenerator):
    async def fetch_context(self) -> dict:
        conn = get_conn(read_only=True)
        # Что тестировали недавно
        cats = conn.execute("""
            SELECT category, COUNT(*) as n FROM hypotheses
            WHERE created_at > NOW() - INTERVAL 1 HOUR
            GROUP BY category ORDER BY n DESC LIMIT 10
        """).fetchall()
        tops = conn.execute("""
            SELECT h.category, MAX(r.sharpe) FROM hypotheses h
            JOIN backtest_results r ON h.id = r.hypothesis_id
            WHERE r.tested_at > NOW() - INTERVAL 1 HOUR
            GROUP BY h.category
        """).fetchall()
        insights = conn.execute("""
            SELECT text FROM insights WHERE is_active = TRUE
              AND ('explorer' = ANY(applies_to_generators) OR 'all' = ANY(applies_to_generators))
            ORDER BY confidence DESC LIMIT 5
        """).fetchall()
        conn.close()
        return {
            "tested_categories": [c[0] for c in cats],
            "top_sharpes": {c: f"{s:.1f}" for c, s in tops},
            "insights": [i[0] for i in insights],
        }

    async def generate(self, ctx: dict) -> tuple[list[dict], float]:
        prompt = EXPLORER_PROMPT.format(
            n=self.cfg.max_hyp_per_call,
            tested_categories=", ".join(ctx["tested_categories"]) or "нет данных",
            top_sharpes=ctx["top_sharpes"] or {},
            insights="\n".join(f"- {i}" for i in ctx["insights"]) or "нет",
        )
        resp = await litellm.acompletion(
            model=self.cfg.model, temperature=self.cfg.temperature,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            thinking={"type": "enabled", "budget_tokens": 2000} if "sonnet" in self.cfg.model else None,
        )
        content = resp.choices[0].message.content
        cost = resp._hidden_params.get("response_cost", 0.01)
        try:
            data = json.loads(content)
            hyps = data.get("hypotheses", [])
            for h in hyps:
                h.setdefault("id", str(uuid.uuid4()))
            return hyps, cost
        except Exception:
            return [], cost
