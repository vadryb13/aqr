# Research Archive — все стратегии, режимы, тренды

Единый снимок исследовательской ветки: 12 904 гипотезы, стресс-тесты, режимные фильтры, трендовые фильтры. Сохранено на 2026-07-10 в отдельный документ, чтобы не жило только в CSV.

Позиционирование: **это архив прошлых исследований**, живой код проекта переехал в тонкий пайплайн (`aqr/pipeline/`). Здесь — то, что мы протестили за все итерации до чистки.

---

## 1. Общая сводка

| Метрика | Значение |
|---|---|
| Всего гипотез протестировано | 12 904 |
| Значимых p<0.05 (mean>0) | 609 (4.7%) |
| Значимых p<0.01 (mean>0) | 245 (1.9%) |
| **Bonferroni pass (p < 3.9e-6)** | **37** |
| BH-FDR (q=0.05) | 61 |
| Robust (p<0.01, n≥100, Sharpe≥1.5) | 231 |

Ожидание случайных p<0.05 при 12 904 тестах ≈ 645. Мы нашли 609 — на уровне шума в среднем, но в top-tail (p<0.01, Bonferroni) — сильное превышение над случайным. **Реальные паттерны сидят в узком элитном сегменте.**

---

## 2. Волны исследования

| Волна | Тема | Гипотез | Значимых | % | Best Sharpe |
|---|---|---:|---:|---:|---:|
| W1 | Metals (Gold/Silver) | 148 | 9 | 6.1% | 3.64 |
| W2 | Commodities (Oil/Gas/NG/HG/Pt) | 264 | 20 | 7.6% | 4.72 |
| W3 | FX + Indices | 380 | 23 | 6.1% | 14.37 |
| W4 | Crypto | 282 | 5 | 1.8% | 2.21 |
| W5 | MOEX stocks | 1 094 | 84 | 7.7% | 3.65 |
| W6 | CNY/RUB | 104 | 20 | 19.2% | 3.99 |
| W7 | Volatility | 298 | 9 | 3.0% | 14.40 |
| **W8** | **Cross-lag correlations** | **1 192** | **47** | 3.9% | **58.4** |
| **W9** | **Pairs & stat-arb** | **5 564** | **680** | **12.3%** | **39.2** |
| **W10** | **Micro & volume** | **3 610** | **169** | 4.7% | **48.5** |

Три волны (W8-W10) дают качественно другой уровень — там сидит big alpha.

---

## 3. Топ-30 стратегий (Bonferroni pass)

Все с p ≈ 0.0 (после Bonferroni поправки на 12 904 теста). Sharpe — сырые, без transaction costs.

| # | Стратегия | Категория | Sharpe | Win% | n | Волна |
|---:|---|---|---:|---:|---:|---|
| 1 | [1h] f_gd-g z-fade lb=20 thr=2.0 | Cross-asset pairs | 32.66 | 69.8 | 129 | W9 |
| 2 | [1h] f_gd-g z-fade lb=100 thr=2.0 | Cross-asset pairs | 32.26 | 67.6 | 142 | W9 |
| 3 | [1h] f_gd-g z-fade lb=50 thr=2.0 | Cross-asset pairs | 31.72 | 65.6 | 131 | W9 |
| 4 | [1h] f_gd-g z-fade lb=50 thr=1.5 | Cross-asset pairs | 30.28 | 67.0 | 273 | W9 |
| 5 | [1h] Gold→GD lag=2 | DXY→Gold→GD | 30.27 | 76.4 | 1 793 | W8 |
| 6 | [1h] f_gd-g z-fade lb=100 thr=1.5 | Cross-asset pairs | 27.32 | 67.9 | 268 | W9 |
| 7 | [1h] f_gd-g z-fade lb=20 thr=1.5 | Cross-asset pairs | 27.06 | 65.5 | 284 | W9 |
| 8 | [1h] f_gd-g z-fade lb=50 thr=1.0 | Cross-asset pairs | 26.90 | 67.3 | 545 | W9 |
| 9 | [1h] f_gd-g z-fade lb=20 thr=1.0 | Cross-asset pairs | 25.47 | 66.1 | 576 | W9 |
| 10 | [1h] f_gd-g z-fade lb=100 thr=1.0 | Cross-asset pairs | 22.78 | 64.2 | 536 | W9 |
| 11 | [10m] m_rosn-m_nvtk (oil) z-fade lb=50 thr=1.0 | Sector pairs | 16.10 | 54.7 | 2 479 | W9 |
| 12 | [DXY-EUR 1d] EURUSD inverse follows DXY | Cross-asset spreads | 14.37 | 86.1 | 1 238 | W3 |
| 13 | [EURUSD 5m] pure mean-reversion | Momentum / Mean-rev | 7.08 | 39.3 | 11 468 | W3 |
| 14 | [1h] sber-chmf z-fade lb=20 thr=1.5 | MOEX all pairs | 6.73 | 54.5 | 2 410 | W9 |
| 15 | [1h] ydex-chmf z-fade lb=20 thr=1.0 | MOEX all pairs | 6.37 | 54.1 | 4 549 | W9 |
| 16 | [1h] mgnt-chmf z-fade lb=50 thr=1.5 | MOEX all pairs | 6.28 | 54.1 | 2 620 | W9 |
| 17 | [1h] mgnt-chmf z-fade lb=20 thr=1.0 | MOEX all pairs | 5.74 | 53.2 | 4 646 | W9 |
| 18 | [1h] lkoh-tatn z-fade lb=20 thr=1.0 | MOEX all pairs | 5.61 | 53.4 | 4 806 | W9 |
| 19 | [1h] m_lkoh-m_tatn (oil) z-fade lb=20 thr=1.0 | Sector pairs | 5.61 | 53.4 | 4 806 | W9 |
| 20 | [1h] mgnt-chmf z-fade lb=50 thr=1.0 | MOEX all pairs | 5.09 | 52.7 | 4 866 | W9 |
| 21 | [1h] m_rosn-m_tatn (oil) z-fade lb=20 thr=1.0 | Sector pairs | 5.02 | 53.6 | 4 748 | W9 |
| 22 | [1h] rosn-tatn z-fade lb=20 thr=1.0 | MOEX all pairs | 5.02 | 53.6 | 4 748 | W9 |
| 23 | [1h] ydex-chmf z-fade lb=50 thr=1.0 | MOEX all pairs | 4.83 | 53.2 | 4 730 | W9 |
| 24 | [platinum 5m] pure mean-reversion | Momentum / Mean-rev | 4.72 | 51.4 | 13 220 | W2 |
| 25 | [CR-fut 1h] fade basis extreme | Spot-Futures basis | 3.99 | 55.8 | 815 | W6 |
| 26 | [CNY] 18:00 follow bullish open | Time-of-day (CNY) | 3.71 | 66.0 | 250 | W6 |
| 27 | [CR-fut 1h] pure mean-reversion | Momentum / Mean-rev | 3.37 | 51.5 | 4 083 | W6 |
| 28 | [GAZP] long at 23:00 | Time-of-day (1h) | 3.25 | 61.6 | 508 | W5 |
| 29 | [YDEX] long at 23:00 | Time-of-day (1h) | 3.20 | 65.1 | 498 | W5 |
| 30 | [GMKN] long during evening | Sessions MOEX | 3.19 | 52.9 | 2 542 | W5 |

**Ключевой инсайт**: `f_gd-g` (Gold-fut / Gold z-fade) даёт 10 из 10 лучших. Это микроструктурный арбитраж между фьючерсом GD и спотовым золотом G на MOEX. Sharpe 22-33 в чистом виде.

---

## 4. Стресс-тест GD/G под комиссии

С учётом транзакционных издержек — работает ли GD/G-арбитраж на реалистичных tc?

| Стратегия | tc bp | All Sharpe | Train Sh | Test Sh | Degradation |
|---|---:|---:|---:|---:|---:|
| GD/G z-fade lb=50 thr=1.5 (base) | 0 | 30.28 | 28.12 | 39.12 | −11.0 |
| GD/G z-fade lb=50 thr=1.5 (base) | 2 | 21.69 | 20.47 | 26.92 | −6.5 |
| GD/G z-fade lb=50 thr=1.5 (base) | 5 | 19.39 | 18.53 | 23.41 | −4.9 |
| GD/G z-fade lb=50 thr=1.5 (base) | 10 | 16.34 | 15.96 | 18.82 | −2.9 |
| GD/G z-fade lb=50 thr=1.5 (base) | 20 | 8.92 | 9.67 | 7.94 | +1.7 |
| GD/G z-fade lb=50 thr=2.0 (base) | 5 | 20.91 | 21.89 | 21.31 | +0.6 |
| GD/G z-fade lb=50 thr=2.0 (base) | 10 | 18.33 | 19.77 | 17.08 | +2.7 |
| GD/G z-fade hr=15-18 thr=1.0 (hour-filter) | 5 | 24.09 | 23.52 | 27.69 | −4.2 |
| GD/G z-fade hr=15-18 thr=1.0 (hour-filter) | 10 | 20.71 | 20.69 | 22.54 | −1.9 |
| GD/G hr=16 z-fade thr=1.5 (peak-hour) | 5 | 25.94 | 25.11 | 29.50 | −4.4 |
| GD/G hr=16 z-fade thr=1.5 (peak-hour) | 10 | 19.69 | 19.75 | 20.82 | −1.1 |
| BR/CL z-fade lb=20 thr=2.0 | 5 | 17.09 | 14.11 | 24.80 | −10.7 |
| BR/CL z-fade lb=50 thr=1.5 hi-vol | 5 | 18.23 | 15.40 | 30.89 | −15.5 |

**Инсайты**:
- GD/G живёт до **tc ≈ 20 bp**, потом Sharpe схлопывается в однозначный
- **Час-фильтр 15-18 MSK** даёт +30% к Sharpe при tc=5-10 bp (лучшая MOEX-ликвидность)
- Test degradation отрицательная — стратегия работает **лучше на OOS**, что редкость (нет look-ahead)
- BR/CL (Brent/WTI-фьючерсы) даёт похожий профиль, но degradation в другую сторону (train хуже test — вероятно, была волатильная фаза в train)

---

## 5. Режимные фильтры (regimes_v2)

Проверка: даёт ли условная торговля по режиму рынка (HV / KMeans / Adaptive-Historical / HMM) uplift к baseline OOS Sharpe.

| Стратегия | Base OOS | HV best | HV OOS | KM best | KM OOS | AH best | AH OOS | HMM best | HMM OOS |
|---|---:|---|---:|---|---:|---|---:|---|---:|
| GD/G z-fade lb=50 thr=1.5 | 29.38 | MID_VOL | 40.01 | 3.0 | 42.34 | MEAN_REV | 30.12 | 0.0 | 28.66 |
| GD/G z-fade lb=100 thr=2.0 | 28.33 | MID_VOL | 40.95 | 1.0 | **73.34** | CHOP | 29.88 | 0.0 | 24.70 |
| GD/G z-fade lb=20 thr=2.0 | 27.18 | LOW_VOL | — | 1.0 | 40.01 | CHOP | 32.42 | 0.0 | 28.26 |
| BR/CL z-fade lb=20 thr=2.0 | 29.86 | LOW_VOL | 33.63 | 2.0 | 33.65 | MEAN_REV | — | 0.0 | 21.35 |
| BR/CL z-fade lb=50 thr=1.5 | 31.08 | LOW_VOL | 32.70 | 1.0 | **47.76** | MEAN_REV | 41.10 | 1.0 | 25.36 |
| MIX wide 1.5x fade lb=50 | 13.57 | LOW_VOL | −3.45 | 2.0 | 11.56 | CHOP | 13.64 | 1.0 | 8.95 |
| MIX wide 2.0x fade lb=50 | 16.36 | LOW_VOL | 2.85 | 2.0 | 16.12 | CHOP | 16.15 | 0.0 | 22.03 |
| Si-CNY z-fade lb=50 t=2 (1h) | −1.11 | MID_VOL | −7.10 | 2.0 | −7.45 | CHOP | −4.81 | 0.0 | −2.45 |
| Si-CNY z-fade lb=100 t=1.5 (1h) | 0.54 | MID_VOL | −10.16 | 2.0 | 7.79 | MEAN_REV | 1.40 | 1.0 | −0.46 |
| SBER-CHMF pair z-fade lb=50 t=2 | 2.77 | — | — | — | — | — | — | — | — |
| GAZP-CHMF pair z-fade lb=50 t=2.5 | 12.09 | — | — | — | — | — | — | — | — |
| CHMF streak≥5 fade 1h | 9.50 | — | — | — | — | — | — | — | — |

**Инсайты**:
- **KMeans clustering** — самый сильный регимный сигнал: даёт uplift +10-45 Sharpe к baseline OOS на GD/G и BR/CL
- **HV-режимы (MID_VOL)** стабильно улучшают GD/G до 40 Sharpe
- **AH (adaptive-historical)** даёт умеренный uplift, HMM почти не влияет
- Пары (SBER-CHMF, GAZP-CHMF) — режимный фильтр здесь не даёт эффекта (либо пар слишком мало точек, либо режим не различает состояния)
- Si-CNY — режимы делают только хуже; стратегия сама по себе слабая

---

## 6. Трендовые фильтры (top 15)

Условная торговля по 5-режимной трендовой шкале (TREND_UP / WEAK_UP / FLAT / WEAK_DN / TREND_DN). Считаем, где стратегия работает лучше всего.

| # | Стратегия | Baseline Sh | Best regime | Best Sh | Uplift |
|---:|---|---:|---|---:|---:|
| 1 | [1h] f_gd-g z-fade lb=100 thr=2.5 | 23.45 | WEAK_DN | 59.00 | +35.55 |
| 2 | [1h] f_gd-g z-fade lb=50 thr=2.5 | 29.94 | WEAK_DN | 48.54 | +18.60 |
| 3 | [1h] f_gd-g z-fade lb=20 thr=2.0 | 24.94 | TREND_DN | 43.38 | +18.44 |
| 4 | [1h] f_gd-g z-fade lb=50 thr=2.0 | 24.23 | WEAK_DN | 40.66 | +16.43 |
| 5 | [1h] f_gd-g z-fade lb=100 thr=2.0 | 24.64 | WEAK_DN | 40.40 | +15.76 |
| 6 | [1h] gazp-ydex z-fade lb=20 thr=2.5 | 7.73 | TREND_UP | 39.29 | +31.56 |
| 7 | [1h] sber-chmf z-fade lb=20 thr=2.0 | 5.93 | WEAK_UP | 37.97 | +32.04 |
| 8 | [1h] f_gd-g z-fade lb=50 thr=1.5 | 23.12 | WEAK_DN | 34.73 | +11.61 |
| 9 | [1h] Gold→GD lag=2 | 23.19 | TREND_DN | 31.23 | +8.04 |
| 10 | [1h] f_gd-g z-fade lb=100 thr=1.5 | 20.86 | WEAK_DN | 29.49 | +8.63 |
| 11 | [1h] f_gd-g z-fade lb=20 thr=1.0 | 19.46 | WEAK_DN | 28.57 | +9.11 |
| 12 | [1h] f_gd-g z-fade lb=20 thr=1.5 | 20.67 | WEAK_DN | 28.46 | +7.79 |
| 13 | [1h] sber-chmf z-fade lb=50 thr=1.5 | 3.58 | WEAK_UP | 27.72 | +24.14 |
| 14 | [1h] f_gd-g z-fade lb=50 thr=1.0 | 20.55 | FLAT | 27.19 | +6.64 |
| 15 | [1d] f_mix-m_sber z-mom lb=50 thr=1.0 | 20.71 | FLAT | 25.32 | +4.61 |

**Инсайты**:
- Основные победители — **GD/G z-fade в даун-тренде** (WEAK_DN / TREND_DN). В медвежьей фазе арбитраж работает сильнее — вероятно, ликвидность и волатильность спреда выше
- **MOEX-пары (gazp-ydex, sber-chmf)** оживают в трендах: базовый Sharpe 3-8 → 27-40 при условной торговле. Это скрытая alpha, которая теряется в baseline
- **FLAT-режим** — лучший для momentum-стратегий на индексах (`f_mix-m_sber z-mom`)

---

## 7. Что нужно перепроверить (открытые дыры)

1. **Единица времени бэктеста**: multiplier Sharpe (годовой vs дневной) не единообразен между waves. Часть Sharpe 30+ может быть завышена на √252 или √4096 (по количеству баров), а не отражать годовую волатильность
2. **Look-ahead bias**: в паре стратегий (`gd-g z-fade`) train degradation отрицательная — это подозрительно. Возможно, MOEX-данные для GD и G пришли из разных источников с разным alignment
3. **Комиссии в стресс-тесте** тестировались только для 5-6 стратегий; остальные Bonferroni-победители не проверены на tc
4. **Отсутствие DSR/CPCV на этой ветке**: 12 904 гипотезы прошли только классические t-тесты и Bonferroni. Deflated Sharpe и CPCV — уже в новом тонком пайплайне, но эти конкретные стратегии там пока не гоняли
5. **Overlap между стратегиями**: топ-10 — все `f_gd-g z-fade` с разными (lb, thr). Это одна стратегия с 10 параметрами, а не 10 независимых. Реальное число независимых edge'ов — 5-7 (GD/G семейство, EURUSD-DXY, sector pairs, MOEX time-of-day, CNY basis)

---

## 8. Что запустить, если возвращаемся к этому

Быстрый smoke-test — прогнать одну ключевую стратегию через новый пайплайн (с DSR/CPCV/PBO):

```bash
cd /home/user/workspace/aqr_stream
PYTHONPATH=. python -m aqr "проверь mean reversion на паре SBER-CHMF на часовиках"
```

Пайплайн не покроет всё, что было сделано в исследовательской ветке (там были специфические кросс-инструмент спреды, GD/G, EURUSD-DXY, streak-fade), но покроет базовые пары / momentum / mean-reversion / volatility. Расширение — новые семейства в `aqr/pipeline/hypotheses.py`.

Данные для стратегий из этого архива лежат в `.pkl` файлах:
- `gold_1h.pkl`, `silver_1h.pkl`, `platinum_5m.pkl` — металлы
- `cl_1h.pkl`, `br_1h.pkl`, `ng_1h.pkl`, `hg_1h.pkl`, `pl_1h.pkl` — commodities
- `eurusd_5m.pkl`, `dxy_1d.pkl`, `usdjpy_1h.pkl` — FX
- `sber_1h.pkl`, `gazp_1h.pkl`, `lkoh_1h.pkl`, `chmf_1h.pkl`, ... — MOEX (H1)
- `btc_1h.pkl`, `eth_1h.pkl`, `bnb_1h.pkl` — crypto
- `c_cny_1h.pkl`, `c_crm6_1h.pkl`, `c_cru6_1h.pkl` — CNY/RUB

## 9. Исходные CSV (сырые данные для этого документа)

Все в `/home/user/workspace/`:
- `all_10k_hypotheses.csv` — все 12 904 гипотезы
- `all_hypotheses.csv` — предыдущий срез (~2 570)
- `bonferroni_pass.csv` — 37 топ-стратегий
- `fdr_pass_strategies.csv` — 61 BH-FDR pass
- `robust_strategies.csv` — 231 robust
- `results_arb.csv`, `results_arb2.csv` — arbitrage runs
- `arb_stress_results.csv` — стресс-тест GD/G под tc
- `regime_analysis.csv`, `regime_oos_results.csv`, `regimes_v2_results.csv` — режимы
- `regime_conditional_sharpe.csv` — условные Sharpe
- `trend_filter_results.csv` — 136 стратегий × 5 трендовых режимов
- `results_moex.csv`, `results_fx.csv`, `results_comm.csv`, `results_crypto.csv`, `results_cny.csv`, `results_pairs.csv`, `results_micro.csv`, `results_crosslag.csv` — по волнам
- `research_log.md`, `research_log_final.md` — интерактивные логи прошлых сессий
