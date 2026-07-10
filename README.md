# AQR — Auto Quant Research

**LLM-driven quantitative research framework for MOEX markets, with rigorous statistical validation.**

[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

> **Status: research preview (v0.1.0).** APIs may change. Not financial advice.

---

## What makes AQR different

Most LLM+trading projects are decision-makers ("should I buy AAPL today?"). AQR is different:

| | Decision-makers<br>(TradingAgents, AI Hedge Fund) | Alpha miners<br>(AlphaCrafter, VARRD) | **AQR** |
|---|:-:|:-:|:-:|
| Continuous vs batch | Episodic | Daily refresh | **24/7 streaming** |
| Growing block library | ❌ | ❌ | **Validated on register** |
| Hierarchical memory | ❌ | ❌ | **4-tier L1-L4** |
| Adversarial testing | End-of-pipeline | End-of-pipeline | **Continuous** |
| Deflated Sharpe / CPCV | ✅ | ✅ | **✅ (this repo)** |
| Anti-crowding at gen-time | ex-post | ex-post | **at generation** |
| MOEX-first | ❌ | ❌ | **✅** |

## Key features

### 1. Statistical validation you can defend
- **Deflated Sharpe Ratio** (Bailey & López de Prado, 2014) — corrects for multiple testing
- **Combinatorial Purged Cross-Validation** — no look-ahead bias, multiple OOS paths
- **Probability of Backtest Overfitting** — detects Sharpe-hacking
- **White's Reality Check** with stationary bootstrap
- **Minimum Track Record Length** — how long until you can trust the SR

### 2. MOEX-first data layer
- MOEX ISS adapter for shares, futures, currency, indices, bonds
- Point-in-time discipline via `DataManifest` — every backtest is byte-reproducible
- Corporate-action adjustments applied only up to `as_of`

### 3. Streaming hypothesis generation
- 5 generator types (Explorer, Exploiter, Mutator, Adversary, Regime Specialist)
- Redis Streams + multi-process backtest workers
- FAISS semantic dedup at generation time (not ex-post)
- Diversity guard forces prompts away from over-explored areas

### 4. Growing block library
- Every reusable strategy component registered with tests
- Automatic leakage detection (rejects `shift(-N)` etc.)
- Pytest validation before entering the registry
- Tracks avg Sharpe & usage count per block

### 5. Hierarchical memory (4-tier)
- **L1 events** — raw agent actions (30 days)
- **L2 insights** — patterns extracted hourly (24-72h)
- **L3 heuristics** — promoted after ≥100 evidence + validation (weeks-months)
- **L4 laws** — human-confirmed permanent knowledge

## Quick start

```bash
git clone https://github.com/vadryb13/aqr.git
cd aqr
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run the statistical validation demo (no LLM needed)
python -m aqr.cli demo-validation

# Fetch MOEX data
python -c "from aqr.data import MOEXAdapter; print(MOEXAdapter().candles('SBER','2024-01-01','2024-12-31'))"

# Run test suite
pytest tests/ -v
```

## Statistical validation example

```python
import numpy as np
from aqr.validation import deflated_sharpe_ratio, probability_of_backtest_overfitting

returns = np.random.normal(0.001, 0.01, 500)  # daily returns

# Correct for multiple testing (we generated 1000 hypotheses)
dsr = deflated_sharpe_ratio(returns, n_trials=1000)
print(dsr)
# {'sharpe': 1.6, 'expected_max_sharpe': 3.05, 'deflated_sharpe': 0.07,
#  'n_trials': 1000, 'verdict': 'not_significant'}

# Check if a portfolio of strategies is overfit
returns_matrix = np.random.normal(0, 0.01, (500, 50))  # T x N
pbo = probability_of_backtest_overfitting(returns_matrix, n_partitions=16)
print(pbo)
# {'pbo': 0.42, 'verdict': 'suspicious', ...}
```

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — system overview
- [docs/AUTONOMOUS_RESEARCH_ENGINE.md](docs/AUTONOMOUS_RESEARCH_ENGINE.md) — 10 gaps to full autonomy
- [docs/COMPETITIVE_LANDSCAPE.md](docs/COMPETITIVE_LANDSCAPE.md) — how AQR compares to TradingAgents / AlphaCrafter / VARRD
- [docs/COLLABORATIVE_AGENT_PLATFORM.md](docs/COLLABORATIVE_AGENT_PLATFORM.md) — multi-user platform design

## References

If you use AQR, please cite it. See [CITATION.cff](CITATION.cff).

Key papers that AQR builds on:
- Bailey, D. and López de Prado, M. (2014). *The Deflated Sharpe Ratio.* Journal of Portfolio Management 40(5). [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)
- Bailey, D., Borwein, J., López de Prado, M. and Zhu, Q. (2015). *The Probability of Backtest Overfitting.* [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253)
- López de Prado, M. (2018). *Advances in Financial Machine Learning.* Wiley — ch. 12 (CPCV).
- White, H. (2000). *A Reality Check for Data Snooping.* Econometrica 68(5).
- QuantaAlpha (2026). *Factor Crowding in LLM Alpha Mining.* arXiv:2602.07085

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Disclaimer

This software is for **research purposes only**. Nothing in this repository constitutes financial, investment, or trading advice. Past performance of any strategy — real or backtested — does not guarantee future results. Use at your own risk.
