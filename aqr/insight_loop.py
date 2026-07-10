"""Hourly insight extraction — meta-LLM смотрит все последние результаты и выводит паттерны."""
from __future__ import annotations
import asyncio, json, litellm, uuid, logging
from .db.schema import get_conn

log = logging.getLogger(__name__)


INSIGHT_PROMPT = """Ты meta-аналитик квант-исследования. Тебе даны {n} свежих результатов бэктестов за последний час.

СТАТИСТИКА:
{stats}

СЭМПЛ ТОП-РЕЗУЛЬТАТОВ (лучшие 30):
{top}

СЭМПЛ ХУДШИХ (худшие 20):
{bottom}

Извлеки 3-7 ПАТТЕРНОВ (не тривиальных). Каждый паттерн должен:
1. Быть подтверждён минимум 10 гипотезами
2. Иметь количественное обоснование (avg sharpe, p-value, sample size)
3. Быть actionable — конкретная рекомендация для генератора

Форматы:
- pattern: "z-fade работает в TREND_DN лучше в 2.3× чем в FLAT (n=847, p<0.001)"
- warning: "wide-range fade деградирует на 10m (уменьшить генерацию)"
- recommendation: "Exploiter: приоритет на MOEX-MOEX пары"

JSON: {{"insights": [{{"insight_type": "pattern|warning|recommendation", "text": "...", "confidence": 0.0-1.0, "applies_to_generators": ["explorer", "exploiter", "mutator", "adversary", "regime", "all"], "evidence_hypothesis_ids": [...]}}]}}
"""


async def hourly_insight_extraction():
    conn = get_conn()
    try:
        recent = conn.execute("""
            SELECT h.id, h.hypothesis, h.category, h.block_name, h.timeframe,
                   r.sharpe, r.pvalue, r.best_regime, r.max_dd
            FROM hypotheses h JOIN backtest_results r ON h.id = r.hypothesis_id
            WHERE r.tested_at > NOW() - INTERVAL 1 HOUR
        """).fetchall()
        if len(recent) < 50:
            log.info(f"insight loop: only {len(recent)} results, skipping")
            return

        # Prep context
        n = len(recent)
        top = sorted(recent, key=lambda x: x[5] or 0, reverse=True)[:30]
        bottom = sorted(recent, key=lambda x: x[5] or 0)[:20]
        stats = _compute_stats(recent)

        prompt = INSIGHT_PROMPT.format(
            n=n, stats=json.dumps(stats, indent=2),
            top=_fmt_rows(top), bottom=_fmt_rows(bottom),
        )

        resp = await litellm.acompletion(
            model="claude-sonnet-4-5",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            thinking={"type": "enabled", "budget_tokens": 3000},
        )
        data = json.loads(resp.choices[0].message.content)
        insights = data.get("insights", [])

        # Деактивировать старые (>24ч)
        conn.execute("""
            UPDATE insights SET is_active = FALSE
            WHERE created_at < NOW() - INTERVAL 24 HOUR
        """)
        gen = int(conn.execute("SELECT COALESCE(MAX(generation), 0) + 1 FROM insights").fetchone()[0])

        # Сохранить новые
        for ins in insights:
            conn.execute("""
                INSERT INTO insights (id, generation, insight_type, text, evidence_hypothesis_ids, confidence, applies_to_generators)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [str(uuid.uuid4()), gen, ins.get("insight_type"), ins.get("text"),
                  ins.get("evidence_hypothesis_ids", []), ins.get("confidence", 0.5),
                  ins.get("applies_to_generators", ["all"])])

        log.info(f"insight loop: saved {len(insights)} insights (gen {gen})")
    finally:
        conn.close()


def _fmt_rows(rows: list) -> str:
    return "\n".join(
        f"- [{r[2]}/{r[3]}/{r[4]}] Sharpe={r[5]:.2f} regime={r[7]} — {r[1][:80]}"
        for r in rows if r[5] is not None
    )


def _compute_stats(rows: list) -> dict:
    from collections import Counter
    cats = Counter(r[2] for r in rows if r[2])
    regs = Counter(r[7] for r in rows if r[7])
    sharpes = [r[5] for r in rows if r[5] is not None]
    return {
        "n_total": len(rows),
        "by_category": dict(cats.most_common(10)),
        "by_regime": dict(regs.most_common(5)),
        "sharpe_gt_3": sum(1 for s in sharpes if s > 3),
        "sharpe_gt_5": sum(1 for s in sharpes if s > 5),
        "avg_sharpe": sum(sharpes) / len(sharpes) if sharpes else 0,
        "max_sharpe": max(sharpes) if sharpes else 0,
    }


async def loop_forever(interval_sec: int = 3600):
    while True:
        try:
            await hourly_insight_extraction()
        except Exception as e:
            log.exception(f"insight loop error: {e}")
        await asyncio.sleep(interval_sec)
