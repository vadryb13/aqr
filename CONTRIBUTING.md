# Contributing to AQR

Thanks for your interest. This project is early-stage and welcomes contributions.

## Development setup

```bash
git clone https://github.com/vadryb13/aqr.git
cd aqr
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Running tests

```bash
pytest tests/ -v
```

## Contribution areas

Priority-ordered gaps that need work:

1. **Statistical validation** — additional tests beyond DSR/PBO/CPCV (SPA test, MCS, etc.)
2. **MOEX data coverage** — bonds, options, alternative data sources
3. **Backtest engine** — vectorized backtest with realistic transaction costs and slippage
4. **Live paper trading** — broker MCP integration
5. **UI polish** — the React Tremor dashboard has rough edges
6. **Documentation** — tutorials, examples on real MOEX data

## Design principles

1. **Statistical rigor over headline Sharpe** — every reported edge must include DSR + PBO
2. **Point-in-time correctness** — no look-ahead bias, corp actions applied only as of the observation date
3. **Reproducibility** — every backtest recoverable from `{seed, code_version, data_snapshot_id}`
4. **Anti-crowding at generation** — enforce diversity in the LLM prompt, not ex-post filtering
5. **Cost-first thinking** — track `$ per validated strategy` as a primary metric

## Code style

- Type hints on all public APIs (`from __future__ import annotations`)
- Docstrings on public functions cite the paper if applicable
- One module per concept — split rather than concatenate

## Pull requests

1. Fork the repo
2. Create a feature branch (`feat/topic` or `fix/topic`)
3. Add tests for new behavior
4. Run `pytest` and `ruff check .`
5. Open PR against `main` with a clear description

## Non-goals

To keep the project focused, we do NOT accept contributions for:

- Turnkey "money-printing" bots or wrapper products
- US-equity-only features (this is deliberately MOEX-first)
- Trading-signal marketplaces or paid tiers in the OSS repo
- Legal/regulatory tooling (out of scope; use dedicated compliance products)

## Code of Conduct

Be kind. Assume good faith. No harassment.

## License

By contributing you agree that your contributions will be licensed under Apache 2.0.
