"""
Probability of Backtest Overfitting (PBO).

Bailey, Borwein, Lopez de Prado & Zhu (2015). The Probability of Backtest Overfitting.
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253

Идея:
1. Разбить in-sample матрицу возвратов (T x N) на S равных submatrices
2. Для всех C(S, S/2) комбинаций: train = половина, test = другая половина
3. Взять best strategy на train по SR, посмотреть её rank на test
4. PBO = доля случаев где test-rank оказался в нижней половине

PBO ≈ 0.5 → результаты чистый оверфит.
PBO < 0.3 → есть persistence из in-sample в out-of-sample.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np


def _sharpe_col(x: np.ndarray) -> float:
    if x.std(ddof=1) == 0:
        return 0.0
    return float(x.mean() / x.std(ddof=1))


def probability_of_backtest_overfitting(
    returns_matrix: np.ndarray,
    n_partitions: int = 16,
    max_combinations: int = 1000,
    rng_seed: int = 42,
) -> dict:
    """
    Compute PBO for a set of strategies.

    Args:
        returns_matrix: (T, N) array — T periods, N strategies
        n_partitions: S, must be even. 16 стандарт по paper.
        max_combinations: если C(S, S/2) > max, случайно семплируем
        rng_seed: для воспроизводимости

    Returns:
        {
            "pbo": вероятность оверфита в [0,1],
            "n_combinations": сколько сплитов оценено,
            "median_rank_degradation": медианная деградация ранга,
            "verdict": "robust" if pbo < 0.5 else "overfit"
        }
    """
    r = np.asarray(returns_matrix, dtype=float)
    if r.ndim != 2:
        raise ValueError("returns_matrix must be 2D (T x N)")

    T, N = r.shape
    if N < 2:
        return {"pbo": 0.5, "n_combinations": 0, "median_rank_degradation": 0.0, "verdict": "insufficient"}

    S = n_partitions
    if S % 2 != 0:
        S -= 1
    if S < 4:
        S = 4

    # Обрезаем T до кратного S
    T_trim = (T // S) * S
    if T_trim < S * 2:
        return {"pbo": 0.5, "n_combinations": 0, "median_rank_degradation": 0.0, "verdict": "insufficient"}

    r = r[:T_trim]
    partitions = np.array_split(r, S, axis=0)

    all_indices = list(range(S))
    all_combos = list(combinations(all_indices, S // 2))

    rng = np.random.default_rng(rng_seed)
    if len(all_combos) > max_combinations:
        chosen = rng.choice(len(all_combos), size=max_combinations, replace=False)
        combos = [all_combos[i] for i in chosen]
    else:
        combos = all_combos

    logits = []
    rank_degradations = []

    for train_idx in combos:
        test_idx = tuple(i for i in all_indices if i not in train_idx)

        train_returns = np.vstack([partitions[i] for i in train_idx])
        test_returns = np.vstack([partitions[i] for i in test_idx])

        train_sr = np.array([_sharpe_col(train_returns[:, j]) for j in range(N)])
        test_sr = np.array([_sharpe_col(test_returns[:, j]) for j in range(N)])

        # Best strategy in-sample
        best_is = int(np.argmax(train_sr))

        # Its rank out-of-sample (percentile in [0, 1])
        test_rank = float(np.sum(test_sr <= test_sr[best_is]) / N)

        # Logit for PBO calc — Bailey et al eq (7)
        # w_c = test_rank; logit = log(w/(1-w))
        eps = 1e-6
        w = np.clip(test_rank, eps, 1 - eps)
        logits.append(np.log(w / (1 - w)))

        # rank degradation: 1 (best) → test_rank (percentile)
        rank_degradations.append(1.0 - test_rank)

    logits = np.array(logits)
    pbo = float(np.mean(logits < 0))  # доля где OOS rank ниже median

    return {
        "pbo": pbo,
        "n_combinations": len(combos),
        "median_rank_degradation": float(np.median(rank_degradations)),
        "verdict": "robust" if pbo < 0.3 else ("suspicious" if pbo < 0.5 else "overfit"),
    }
