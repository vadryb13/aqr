"""
Параметризованные гипотезы для тонкого сквозного демо.

Каждая гипотеза — функция (prices: pd.Series, **params) → position: pd.Series (-1/0/+1).
Реалистичные, но простые. Достаточно, чтобы гонять валидацию.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable
import numpy as np
import pandas as pd


@dataclass
class HypothesisSpec:
    """Одна конкретная гипотеза с заполненными параметрами."""

    name: str          # человекочитаемое имя
    family: str        # momentum | mean_reversion | breakout | volatility
    ticker: str
    params: dict
    fn: Callable[[pd.Series], pd.Series]  # prices → positions

    def describe(self) -> str:
        p = ", ".join(f"{k}={v}" for k, v in self.params.items())
        return f"{self.family}: {self.name} на {self.ticker} ({p})"


# ---------- ИМПЛЕМЕНТАЦИИ СИГНАЛОВ ----------

def _sma_crossover(fast: int, slow: int):
    def signal(prices: pd.Series) -> pd.Series:
        sf = prices.rolling(fast).mean()
        ss = prices.rolling(slow).mean()
        pos = np.where(sf > ss, 1.0, -1.0)
        pos = pd.Series(pos, index=prices.index)
        # первые slow точек — нет позиции
        pos.iloc[:slow] = 0.0
        return pos
    return signal


def _momentum_zscore(lookback: int, threshold: float):
    def signal(prices: pd.Series) -> pd.Series:
        r = prices.pct_change()
        z = (r - r.rolling(lookback).mean()) / r.rolling(lookback).std()
        pos = np.where(z > threshold, 1.0, np.where(z < -threshold, -1.0, 0.0))
        pos = pd.Series(pos, index=prices.index)
        pos.iloc[:lookback] = 0.0
        return pos
    return signal


def _mean_reversion(lookback: int, threshold: float):
    def signal(prices: pd.Series) -> pd.Series:
        # обратный к momentum: покупаем перепроданное, продаём перекупленное
        ma = prices.rolling(lookback).mean()
        sd = prices.rolling(lookback).std()
        z = (prices - ma) / sd
        pos = np.where(z < -threshold, 1.0, np.where(z > threshold, -1.0, 0.0))
        pos = pd.Series(pos, index=prices.index)
        pos.iloc[:lookback] = 0.0
        return pos
    return signal


def _breakout(lookback: int):
    def signal(prices: pd.Series) -> pd.Series:
        hi = prices.rolling(lookback).max()
        lo = prices.rolling(lookback).min()
        pos = np.zeros(len(prices))
        for i in range(lookback, len(prices)):
            if prices.iloc[i] >= hi.iloc[i - 1]:
                pos[i] = 1.0
            elif prices.iloc[i] <= lo.iloc[i - 1]:
                pos[i] = -1.0
            else:
                pos[i] = pos[i - 1]
        return pd.Series(pos, index=prices.index)
    return signal


def _volatility_filter(lookback: int, vol_threshold: float):
    """Momentum, но только когда волатильность выше порога."""
    def signal(prices: pd.Series) -> pd.Series:
        r = prices.pct_change()
        vol = r.rolling(lookback).std()
        vol_ok = (vol > vol_threshold).astype(float)
        base = _momentum_zscore(lookback, 1.0)(prices)
        return base * vol_ok
    return signal


# ---------- ГЕНЕРАТОР СПЕЦИФИКАЦИЙ ----------

def generate_hypotheses(
    tickers: list[str],
    families: list[str],
    n: int,
    seed: int = 42,
) -> list[HypothesisSpec]:
    """
    Разложить бюджет n гипотез между тикерами и семействами.
    Используем детерминистичный псевдослучайный подбор параметров.
    """
    rng = np.random.default_rng(seed)
    specs: list[HypothesisSpec] = []

    combos = [(t, f) for t in tickers for f in families]
    if not combos:
        return specs

    for i in range(n):
        ticker, family = combos[i % len(combos)]
        spec = _make_one(family, ticker, rng)
        if spec is not None:
            specs.append(spec)

    return specs


def _make_one(family: str, ticker: str, rng) -> HypothesisSpec | None:
    if family == "momentum":
        fast = int(rng.choice([5, 10, 20]))
        slow = int(rng.choice([50, 100, 200]))
        if fast >= slow:
            slow = fast * 4
        return HypothesisSpec(
            name=f"SMA{fast}/{slow}",
            family="momentum",
            ticker=ticker,
            params={"fast": fast, "slow": slow},
            fn=_sma_crossover(fast, slow),
        )
    if family == "mean_reversion":
        lb = int(rng.choice([10, 20, 40]))
        th = float(rng.choice([1.0, 1.5, 2.0]))
        return HypothesisSpec(
            name=f"MR-z{th}/{lb}",
            family="mean_reversion",
            ticker=ticker,
            params={"lookback": lb, "threshold": th},
            fn=_mean_reversion(lb, th),
        )
    if family == "breakout":
        lb = int(rng.choice([20, 55, 100]))
        return HypothesisSpec(
            name=f"Donchian-{lb}",
            family="breakout",
            ticker=ticker,
            params={"lookback": lb},
            fn=_breakout(lb),
        )
    if family == "volatility":
        lb = int(rng.choice([10, 20]))
        vt = float(rng.choice([0.005, 0.010, 0.015]))
        return HypothesisSpec(
            name=f"VolMom-{lb}/{vt}",
            family="volatility",
            ticker=ticker,
            params={"lookback": lb, "vol_threshold": vt},
            fn=_volatility_filter(lb, vt),
        )
    return None
