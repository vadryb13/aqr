"""
White's Reality Check + Bootstrap Sharpe CI.

White (2000). A Reality Check for Data Snooping. Econometrica 68(5).
Hansen (2005). Superior Predictive Ability (SPA) — improvement over Reality Check.

Тест: даёт ли лучшая стратегия из N испытаний edge над benchmark
       после учёта того что мы искали среди многих?
"""
from __future__ import annotations

import numpy as np


def bootstrap_sharpe_ci(
    returns: np.ndarray,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    block_size: int | None = None,
    annualization: float = 252.0,
    rng_seed: int = 42,
) -> dict:
    """
    Stationary Bootstrap CI for Sharpe (Politis & Romano 1994).

    Учитывает autocorrelation через block bootstrap.

    Returns:
        {sharpe, ci_low, ci_high, p_positive}
    """
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    n = len(r)
    if n < 10:
        return {"sharpe": 0.0, "ci_low": 0.0, "ci_high": 0.0, "p_positive": 0.5}

    if block_size is None:
        block_size = max(int(n ** (1 / 3)), 5)

    rng = np.random.default_rng(rng_seed)
    sharpes = np.empty(n_bootstrap)

    for b in range(n_bootstrap):
        sample = np.empty(n)
        idx = 0
        while idx < n:
            start = rng.integers(0, n)
            length = min(block_size, n - idx)
            for j in range(length):
                sample[idx + j] = r[(start + j) % n]
            idx += length
        if sample.std(ddof=1) > 0:
            sharpes[b] = sample.mean() / sample.std(ddof=1) * np.sqrt(annualization)
        else:
            sharpes[b] = 0.0

    alpha = (1 - confidence) / 2
    return {
        "sharpe": float(r.mean() / r.std(ddof=1) * np.sqrt(annualization)) if r.std(ddof=1) > 0 else 0.0,
        "ci_low": float(np.quantile(sharpes, alpha)),
        "ci_high": float(np.quantile(sharpes, 1 - alpha)),
        "p_positive": float(np.mean(sharpes > 0)),
    }


def whites_reality_check(
    strategy_returns: np.ndarray,
    benchmark_returns: np.ndarray,
    n_bootstrap: int = 2000,
    block_size: int | None = None,
    rng_seed: int = 42,
) -> dict:
    """
    White's Reality Check via stationary bootstrap.

    Args:
        strategy_returns: (T, N) matrix — T периодов, N стратегий
        benchmark_returns: (T,) benchmark
        n_bootstrap: количество bootstrap samples

    Returns:
        {p_value, best_strategy_idx, best_mean_excess, verdict}
    """
    S = np.asarray(strategy_returns, dtype=float)
    B = np.asarray(benchmark_returns, dtype=float)

    if S.ndim == 1:
        S = S.reshape(-1, 1)
    T, N = S.shape

    if len(B) != T:
        raise ValueError("Length mismatch strategy vs benchmark")

    # Excess returns
    X = S - B.reshape(-1, 1)  # (T, N)

    # Observed max mean
    mean_x = X.mean(axis=0)  # (N,)
    V_obs = np.sqrt(T) * mean_x.max()
    best_idx = int(mean_x.argmax())

    if block_size is None:
        block_size = max(int(T ** (1 / 3)), 5)

    rng = np.random.default_rng(rng_seed)
    V_star = np.empty(n_bootstrap)

    # Centered variables for bootstrap under H0
    X_centered = X - mean_x  # (T, N)

    for b in range(n_bootstrap):
        # Stationary bootstrap indices
        indices = np.empty(T, dtype=int)
        pos = 0
        while pos < T:
            start = rng.integers(0, T)
            length = min(block_size, T - pos)
            for j in range(length):
                indices[pos + j] = (start + j) % T
            pos += length

        X_boot = X_centered[indices]  # (T, N)
        V_star[b] = np.sqrt(T) * X_boot.mean(axis=0).max()

    p_value = float(np.mean(V_star >= V_obs))

    return {
        "p_value": p_value,
        "best_strategy_idx": best_idx,
        "best_mean_excess": float(mean_x[best_idx]),
        "verdict": "significant" if p_value < 0.05 else "not_significant",
        "n_bootstrap": n_bootstrap,
    }
