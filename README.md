# AQR

Тонкий пайплайн: цель на естественном языке → валидированные гипотезы на MOEX.

Ввод — русский текст («проверь momentum на голубых фишках»). Внутри: план → загрузка MOEX → генерация гипотез → бэктест → Deflated Sharpe / CPCV / PBO → нарративный отчёт. Живая лента шагов через SSE.

## Быстрый старт

```bash
pip install -e ".[dev]"
python -m aqr "проверь momentum на Сбере"
```

CLI покажет план, шаги бэктеста, топ-5 гипотез по Deflated Sharpe и текстовый вывод. Работает без LLM-ключей (fallback-планировщик и fallback-нарратор), без Redis, без Docker.

С LLM (Claude / GPT / GigaChat):
```bash
export ANTHROPIC_API_KEY=...
export AQR_LLM_MODEL=claude-3-5-sonnet-20241022
python -m aqr "что работает у металлургов?"
```

## HTTP API

```bash
uvicorn aqr.main:app --port 8000
```

- `POST /pipeline/runs` — `{"goal": "..."}` → `{run_id, plan}`
- `GET /pipeline/runs/{run_id}` — снимок событий и статус
- `GET /pipeline/runs/{run_id}/stream` — SSE-лента событий в реальном времени
- `GET /health`

## Что делает пайплайн

1. **ChatPlanner** — превращает цель в JSON-план (тикеры, семейства гипотез, таймфрейм, количество)
2. **_load_data** — MOEX ISS, при недоступности сети — синтетика с фиксированным seed
3. **generate_hypotheses** — параметризованные семейства: momentum, mean_reversion, breakout, volatility
4. **_backtest_one** — vectorized backtest с shift(1), Sharpe, drawdown, число сделок
5. **Валидация** — Deflated Sharpe с поправкой на multiple testing, CPCV OOS, PBO по портфелю
6. **_extract_insights** — детерминистичные наблюдения
7. **Narrator** — LLM или fallback пишет 3-6 абзацев по-русски

Каждый шаг публикует Event в EventBus. UI/CLI подписываются через SSE.

## Тесты

```bash
pytest tests/ -v
```

17 тестов: 12 на валидацию (DSR / PBO / CPCV / Reality Check / MinTRL) и 5 e2e на пайплайн (планировщик, синтетические данные, нарратор).

## Структура

```
aqr/
├── pipeline/         # сквозной пайплайн: планировщик, executor, narrator, SSE-события, HTTP-роутер
├── validation/       # Deflated Sharpe, CPCV, PBO, White's Reality Check
├── data/             # MOEX ISS адаптер, DataManifest (DuckDB, опционально)
├── main.py           # FastAPI app
├── cli.py            # `python -m aqr <goal>`
└── __main__.py
tests/
├── test_pipeline_e2e.py
└── test_validation.py
```

Полное описание для LLM-агентов: [AGENTS.md](AGENTS.md).

## Ограничения

- MOEX ISS исторически не даёт H1 глубже нескольких месяцев — для H1-стратегий покрытие короткое
- Backtest не учитывает комиссии и проскальзывание (planned)
- Fallback-планировщик — по ключевым словам, не понимает сложные формулировки

## Лицензия

Apache 2.0.
