"""
Research Planner Agent — daily agenda для всей фабрики.

Запускается каждое утро (9:00 МСК):
1. Читает состояние знаний (L1-L4 memory)
2. Находит гэпы в покрытии
3. Пишет исследовательскую повестку на сутки
4. Обновляет focus/avoid у генераторов и распределение бюджета
"""
from __future__ import annotations
import json, uuid, litellm
from ..db.schema import get_conn


PLANNER_PROMPT = """Ты руководитель quant-исследовательской команды. Каждое утро ты решаешь чем команда займётся сегодня.

СОСТОЯНИЕ ЗНАНИЙ:
- L4 Laws (фундаментальные истины, {n_laws} шт):
{laws}

- L3 Heuristics (устойчивые паттерны, {n_heur} шт):
{heuristics}

- L2 Свежие Insights (последние 24ч):
{insights}

ПРОГРЕСС ЗА ВЧЕРА:
- Всего гипотез: {n_yesterday}
- Прошли p<0.05 и Sharpe>3: {n_significant}
- Топ находки: {top_yesterday}

ГЭПЫ (категории с низким покрытием / низким avg Sharpe):
{gaps}

БЮДЖЕТ СЕГОДНЯ: ${daily_budget}
ЦЕЛЬ ДОЛГОСРОЧНАЯ: {long_term_goal}

ЗАДАЧА: напиши research agenda на сегодня.

JSON: {{
  "focus_areas": ["специфические направления, 3-5 штук"],
  "avoid_areas": ["что НЕ трогать сегодня, 2-3 штуки"],
  "priority_hypotheses": {{"generator_type": "конкретная цель"}},
  "budget_allocation": {{"explorer": 0.2, "exploiter": 0.5, "mutator": 0.2, "adversary": 0.05, "regime": 0.05}},
  "success_criteria": ["измеримые условия успеха дня"],
  "rationale": "почему такой план"
}}
"""


class ResearchPlannerAgent:
    def __init__(self, model: str = "claude-sonnet-4-5",
                 daily_budget: float = 50.0,
                 long_term_goal: str = "Найти 3 uncorrelated стратегии с live Sharpe > 3"):
        self.model = model
        self.daily_budget = daily_budget
        self.long_term_goal = long_term_goal

    async def generate_daily_plan(self) -> dict:
        ctx = self._gather_context()
        prompt = PLANNER_PROMPT.format(**ctx, daily_budget=self.daily_budget,
                                       long_term_goal=self.long_term_goal)
        resp = await litellm.acompletion(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            thinking={"type": "enabled", "budget_tokens": 4000},
        )
        plan = json.loads(resp.choices[0].message.content)
        self._save_plan(plan)
        return plan

    def _gather_context(self) -> dict:
        conn = get_conn(read_only=True)
        try:
            laws = conn.execute("""
                SELECT text FROM laws WHERE confirmed_by_human LIMIT 20
            """).fetchall()
            heur = conn.execute("""
                SELECT text, confidence FROM heuristics
                ORDER BY confidence DESC LIMIT 30
            """).fetchall()
            insights = conn.execute("""
                SELECT text FROM insights WHERE is_active LIMIT 15
            """).fetchall()

            yday = conn.execute("""
                SELECT COUNT(*) FROM hypotheses
                WHERE created_at > NOW() - INTERVAL 24 HOUR
            """).fetchone()[0]
            significant = conn.execute("""
                SELECT COUNT(*) FROM backtest_results r
                JOIN hypotheses h ON h.id = r.hypothesis_id
                WHERE h.created_at > NOW() - INTERVAL 24 HOUR
                  AND r.sharpe > 3 AND r.pvalue < 0.05
            """).fetchone()[0]
            top = conn.execute("""
                SELECT h.hypothesis, r.sharpe FROM backtest_results r
                JOIN hypotheses h ON h.id = r.hypothesis_id
                WHERE h.created_at > NOW() - INTERVAL 24 HOUR
                ORDER BY r.sharpe DESC LIMIT 5
            """).fetchall()

            gaps = conn.execute("""
                SELECT h.category, h.timeframe, COUNT(*) as n,
                       AVG(r.sharpe) as avg_sh
                FROM hypotheses h LEFT JOIN backtest_results r ON h.id = r.hypothesis_id
                WHERE h.created_at > NOW() - INTERVAL 7 DAY
                GROUP BY h.category, h.timeframe
                HAVING avg_sh < 1 OR n < 50
                ORDER BY n ASC LIMIT 15
            """).fetchall()

            return {
                "n_laws": len(laws),
                "laws": "\n".join(f"- {r[0]}" for r in laws) or "нет подтверждённых",
                "n_heur": len(heur),
                "heuristics": "\n".join(f"- ({c:.2f}) {t}" for t, c in heur) or "нет",
                "insights": "\n".join(f"- {r[0]}" for r in insights) or "нет",
                "n_yesterday": yday,
                "n_significant": significant,
                "top_yesterday": "\n".join(f"  {t[:80]} (Sh {s:.1f})" for t, s in top),
                "gaps": "\n".join(f"- {c}/{tf}: n={n} avg_sh={s:.2f}" for c, tf, n, s in gaps),
            }
        finally:
            conn.close()

    def _save_plan(self, plan: dict):
        conn = get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS research_plans (
                    id VARCHAR PRIMARY KEY,
                    plan_date DATE,
                    focus_areas VARCHAR[],
                    avoid_areas VARCHAR[],
                    priority_hypotheses JSON,
                    budget_allocation JSON,
                    success_criteria VARCHAR[],
                    rationale TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                INSERT INTO research_plans (id, plan_date, focus_areas, avoid_areas,
                                            priority_hypotheses, budget_allocation,
                                            success_criteria, rationale)
                VALUES (?, CURRENT_DATE, ?, ?, ?, ?, ?, ?)
            """, [str(uuid.uuid4()), plan.get("focus_areas", []),
                  plan.get("avoid_areas", []),
                  json.dumps(plan.get("priority_hypotheses", {})),
                  json.dumps(plan.get("budget_allocation", {})),
                  plan.get("success_criteria", []),
                  plan.get("rationale", "")])
        finally:
            conn.close()
