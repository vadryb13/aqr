"""
PipelineExecutor — исполняет ResearchPlan шаг за шагом, публикуя события в EventBus.

Шаги:
1. Загрузить данные (MOEX или synthetic-фолбэк)
2. Сгенерировать N гипотез (детерминистично из плана)
3. Для каждой: бэктест + Deflated Sharpe + CPCV + PBO по портфелю
4. Ранжировать, оставить топ
5. Готово
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field, asdict
from typing import Any
import numpy as np
import pandas as pd

from .events import EventBus, Event
from .hypotheses import HypothesisSpec, generate_hypotheses
from .planner import ResearchPlan

# Валидация из существующих модулей
from ..validation.deflated_sharpe import deflated_sharpe_ratio
from ..validation.cpcv import CombinatorialPurgedCV
from ..validation.pbo import probability_of_backtest_overfitting


@dataclass
class BacktestResult:
    hypothesis: HypothesisSpec
    sharpe: float
    dsr: float
    dsr_verdict: str
    cpcv_mean_sharpe: float
    cpcv_std_sharpe: float
    max_drawdown: float
    n_trades: int
    daily_returns: list[float]  # для PBO

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.hypothesis.name,
            "family": self.hypothesis.family,
            "ticker": self.hypothesis.ticker,
            "params": self.hypothesis.params,
            "sharpe": round(self.sharpe, 3),
            "dsr": round(self.dsr, 3),
            "dsr_verdict": self.dsr_verdict,
            "cpcv_mean_sharpe": round(self.cpcv_mean_sharpe, 3),
            "cpcv_std_sharpe": round(self.cpcv_std_sharpe, 3),
            "max_drawdown": round(self.max_drawdown, 3),
            "n_trades": self.n_trades,
        }


@dataclass
class PipelineResult:
    run_id: str
    plan: ResearchPlan
    n_hypotheses_tested: int
    n_survived_dsr: int
    portfolio_pbo: float
    portfolio_pbo_verdict: str
    top: list[BacktestResult] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    narrative: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "plan": asdict(self.plan),
            "n_hypotheses_tested": self.n_hypotheses_tested,
            "n_survived_dsr": self.n_survived_dsr,
            "portfolio_pbo": round(self.portfolio_pbo, 3),
            "portfolio_pbo_verdict": self.portfolio_pbo_verdict,
            "top": [r.to_dict() for r in self.top],
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "narrative": self.narrative,
        }


class PipelineExecutor:
    """Исполняет план и стримит события."""

    def __init__(self, bus: EventBus):
        self.bus = bus

    async def run(self, run_id: str, plan: ResearchPlan) -> PipelineResult:
        t0 = time.time()

        try:
            await self._emit(run_id, "planning", "План принят",
                             f"{len(plan.tickers)} тикеров, {plan.n_hypotheses} гипотез",
                             {"plan": asdict(plan)})

            # 1. Данные
            prices = await self._load_data(run_id, plan)

            # 2. Гипотезы
            await self._emit(run_id, "generating", "Генерирую гипотезы",
                             f"Разбрасываю {plan.n_hypotheses} гипотез по "
                             f"{len(plan.tickers)} тикерам и {len(plan.hypothesis_families)} семействам")
            specs = generate_hypotheses(
                tickers=plan.tickers,
                families=plan.hypothesis_families,
                n=plan.n_hypotheses,
            )

            # 3. Бэктест каждой + DSR
            results: list[BacktestResult] = []
            for i, spec in enumerate(specs, 1):
                if spec.ticker not in prices:
                    continue
                r = self._backtest_one(spec, prices[spec.ticker], plan)
                results.append(r)
                await self._emit(
                    run_id, "backtesting",
                    f"Бэктест {i}/{len(specs)}",
                    spec.describe(),
                    {
                        "i": i, "n": len(specs),
                        "name": spec.describe(),
                        "sharpe": round(r.sharpe, 2),
                        "dsr_verdict": r.dsr_verdict,
                    },
                )
                # даём event loop дышать
                await asyncio.sleep(0)

            # 4. Валидация портфеля через PBO
            await self._emit(run_id, "validating", "PBO по всему портфелю",
                             "Считаю Probability of Backtest Overfitting")
            pbo_result = self._portfolio_pbo(results)

            # 5. Ранжирование
            survived = [r for r in results
                        if r.dsr_verdict in ("significant", "borderline")]
            top = sorted(results, key=lambda r: r.dsr, reverse=True)[:5]

            result = PipelineResult(
                run_id=run_id,
                plan=plan,
                n_hypotheses_tested=len(results),
                n_survived_dsr=len(survived),
                portfolio_pbo=pbo_result["pbo"],
                portfolio_pbo_verdict=pbo_result["verdict"],
                top=top,
                elapsed_seconds=time.time() - t0,
            )

            # Инсайты (детерминистичные наблюдения)
            for insight in self._extract_insights(result):
                await self._emit(run_id, "insight", "Инсайт", insight)

            # Нарратив
            from .narrator import Narrator
            await self._emit(run_id, "narrating", "Пишу резюме", "")
            try:
                narrator = Narrator()
                result.narrative = narrator.narrate(result)
            except Exception as e:
                result.narrative = f"(narrator error: {e})"

            await self._emit(run_id, "done", "Готово",
                             f"Проверено {len(results)} гипотез, прошло DSR — {len(survived)}",
                             {"result": result.to_dict()})
            return result

        except Exception as e:
            await self._emit(run_id, "error", "Ошибка", str(e),
                             {"exception": type(e).__name__})
            raise

    # ---------- ШАГИ ----------

    async def _load_data(self, run_id: str, plan: ResearchPlan) -> dict[str, pd.Series]:
        prices: dict[str, pd.Series] = {}

        # Пытаемся MOEX. Если сеть недоступна — synthetic.
        try:
            from ..data.moex import MOEXAdapter
            adapter = MOEXAdapter()
            for t in plan.tickers:
                await self._emit(run_id, "data", f"Загружаю {t}",
                                 f"MOEX ISS: {plan.start_date} → {plan.end_date}")
                try:
                    df = adapter.candles(
                        t, plan.start_date, plan.end_date,
                        interval=24 if plan.timeframe == "D1" else 60,
                    )
                    if len(df) < 100:
                        raise ValueError(f"мало данных ({len(df)} строк)")
                    prices[t] = df["close"].astype(float)
                    await self._emit(run_id, "data", f"{t}: {len(df)} свечей",
                                     "OK", {"ticker": t, "n": len(df)})
                except Exception as e:
                    await self._emit(run_id, "data",
                                     f"MOEX недоступен для {t}",
                                     f"использую синтетику: {e}",
                                     {"ticker": t, "fallback": True})
                    prices[t] = self._synthetic_series(t, plan)
        except Exception as e:
            await self._emit(run_id, "data",
                             "MOEX-адаптер недоступен, синтетические данные",
                             str(e), {"fallback": True})
            for t in plan.tickers:
                prices[t] = self._synthetic_series(t, plan)

        return prices

    def _synthetic_series(self, ticker: str, plan: ResearchPlan) -> pd.Series:
        """Детерминистический GBM для тикера — воспроизводимо."""
        rng = np.random.default_rng(hash(ticker) % (2**32))
        n = 500
        drift = 0.0005
        vol = 0.015
        r = rng.normal(drift, vol, n)
        # добавляем режимную структуру: тренд-флэт-тренд
        r[100:200] += 0.002
        r[300:400] -= 0.001
        px = 100 * np.exp(np.cumsum(r))
        idx = pd.date_range(plan.start_date, periods=n, freq="B")
        return pd.Series(px, index=idx, name=ticker)

    def _backtest_one(self, spec: HypothesisSpec, prices: pd.Series,
                      plan: ResearchPlan) -> BacktestResult:
        pos = spec.fn(prices)
        # позиция сдвигается на 1 бар, чтобы избежать look-ahead
        pos_shifted = pos.shift(1).fillna(0.0)
        ret = prices.pct_change().fillna(0.0)
        strat_ret = (pos_shifted * ret).astype(float)
        strat_ret = strat_ret.dropna()

        if len(strat_ret) < 30 or strat_ret.std() == 0:
            return BacktestResult(
                hypothesis=spec, sharpe=0.0, dsr=0.0, dsr_verdict="insufficient",
                cpcv_mean_sharpe=0.0, cpcv_std_sharpe=0.0, max_drawdown=0.0,
                n_trades=0, daily_returns=[],
            )

        # Sharpe
        sharpe = float(strat_ret.mean() / strat_ret.std() * np.sqrt(252))

        # Drawdown
        equity = (1 + strat_ret).cumprod()
        dd = float((equity / equity.cummax() - 1.0).min())

        # Число сделок (смены позиции)
        trades = int((pos_shifted.diff().abs() > 0).sum())

        # DSR — считаем множественное тестирование внутри run
        dsr_out = deflated_sharpe_ratio(
            strat_ret.values,
            n_trials=plan.n_hypotheses,
        )
        # Уточняем verdict: borderline если 0.80 <= DSR <= 0.95
        dsr_val = float(dsr_out["deflated_sharpe"])
        if dsr_out["verdict"] == "significant":
            verdict = "significant"
        elif dsr_out["verdict"] == "insufficient_data":
            verdict = "insufficient"
        elif dsr_val >= 0.80:
            verdict = "borderline"
        else:
            verdict = "not_significant"

        # CPCV (лёгкая версия)
        cpcv_mean, cpcv_std = self._cpcv_sharpe(strat_ret, plan)

        return BacktestResult(
            hypothesis=spec,
            sharpe=sharpe,
            dsr=dsr_val,
            dsr_verdict=verdict,
            cpcv_mean_sharpe=cpcv_mean,
            cpcv_std_sharpe=cpcv_std,
            max_drawdown=dd,
            n_trades=trades,
            daily_returns=strat_ret.tolist(),
        )

    def _cpcv_sharpe(self, ret: pd.Series, plan: ResearchPlan) -> tuple[float, float]:
        """Средний OOS Sharpe по CPCV путям (test-fold-only)."""
        cfg = plan.validation
        try:
            cpcv = CombinatorialPurgedCV(
                n_splits=int(cfg.get("cpcv_splits", 6)),
                n_test_splits=int(cfg.get("cpcv_test_splits", 2)),
                embargo_pct=float(cfg.get("embargo_pct", 0.01)),
            )
            sharpes = []
            for train_idx, test_idx in cpcv.split(ret.index):
                if len(test_idx) < 20:
                    continue
                s = ret.iloc[test_idx]
                if s.std() == 0:
                    continue
                sharpes.append(float(s.mean() / s.std() * np.sqrt(252)))
            if not sharpes:
                return 0.0, 0.0
            return float(np.mean(sharpes)), float(np.std(sharpes))
        except Exception:
            return 0.0, 0.0

    def _portfolio_pbo(self, results: list[BacktestResult]) -> dict:
        """PBO по матрице возвратов всех гипотез."""
        good = [r for r in results if r.daily_returns]
        if len(good) < 4:
            return {"pbo": 0.0, "verdict": "insufficient"}
        # Выравниваем длины
        min_len = min(len(r.daily_returns) for r in good)
        min_len = min(min_len, 500)
        if min_len < 40:
            return {"pbo": 0.0, "verdict": "insufficient"}
        M = np.array([r.daily_returns[-min_len:] for r in good]).T
        try:
            out = probability_of_backtest_overfitting(M, n_partitions=8)
            return {"pbo": float(out["pbo"]), "verdict": out.get("verdict", "")}
        except Exception:
            return {"pbo": 0.0, "verdict": "error"}

    def _extract_insights(self, result: PipelineResult) -> list[str]:
        """Детерминистичные наблюдения по результатам."""
        insights = []
        r = result
        if not r.top:
            return insights

        # Лучшая гипотеза
        best = r.top[0]
        insights.append(
            f"Лучшая гипотеза: {best.hypothesis.describe()}. "
            f"Sharpe={best.sharpe:.2f}, DSR={best.dsr:.2f} ({best.dsr_verdict})."
        )

        # По семействам
        by_family: dict[str, list[BacktestResult]] = {}
        for res in r.top:
            by_family.setdefault(res.hypothesis.family, []).append(res)
        for fam, xs in by_family.items():
            avg_dsr = np.mean([x.dsr for x in xs])
            insights.append(
                f"Семейство '{fam}' даёт средний DSR {avg_dsr:.2f} на топе "
                f"({len(xs)} гипотез в топ-5)."
            )

        # PBO вердикт
        if r.portfolio_pbo >= 0.5:
            insights.append(
                f"Внимание: PBO={r.portfolio_pbo:.2f} ({r.portfolio_pbo_verdict}) — "
                f"портфель гипотез выглядит переобученным, лучшие Sharpe вероятно нестабильны."
            )
        elif r.portfolio_pbo >= 0.3:
            insights.append(
                f"PBO={r.portfolio_pbo:.2f} ({r.portfolio_pbo_verdict}) — "
                f"переобучение на грани, перепроверь топ-1 на другом периоде."
            )
        else:
            insights.append(
                f"PBO={r.portfolio_pbo:.2f} ({r.portfolio_pbo_verdict}) — "
                f"отбор в OOS выглядит устойчивым."
            )

        # Survival rate
        if r.n_hypotheses_tested > 0:
            rate = r.n_survived_dsr / r.n_hypotheses_tested
            insights.append(
                f"Выживаемость гипотез после Deflated Sharpe: "
                f"{r.n_survived_dsr}/{r.n_hypotheses_tested} ({rate:.0%})."
            )

        return insights

    async def _emit(self, run_id: str, kind: str, stage: str,
                    message: str = "", data: dict | None = None):
        await self.bus.publish(Event(
            run_id=run_id, kind=kind, stage=stage, message=message,
            data=data or {},
        ))
