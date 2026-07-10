# AGENTS.md

Контракт для LLM-агентов (Claude Code, Codex, Cursor), работающих с этим репозиторием.

## Что это за проект

Тонкий вертикальный срез автоматизированного квант-исследования: пользователь пишет цель по-русски, система планирует, загружает данные с MOEX, генерирует гипотезы, бэктестит, валидирует статистически и пишет отчёт. Никакого Redis, никакого Kafka, никакой очереди — всё в одном процессе. Redis, workers, Docker Compose были удалены как избыточные для текущей стадии.

Единица работы = один **run**. Одна цель → один результат.

## Что уже работает

- **CLI**: `python -m aqr "цель на русском"` — прогон пайплайна с живым логом
- **HTTP API**: FastAPI + SSE, три endpoint'а под `/pipeline/*`
- **Fallback-режим без LLM**: пайплайн работает без API-ключей (регекспный планировщик, шаблонный нарратор)
- **17 тестов**: 12 на валидационные модули, 5 e2e на пайплайн

## Что НЕ надо трогать без явной причины

- `aqr/validation/` — reference-имплементации из книг López de Prado / Bailey. Формулы уже проверены тестами. Если меняешь — обязательно перепрогони `tests/test_validation.py`.
- `aqr/data/moex.py` — MOEX ISS адаптер. API MOEX — внешнее, менять эндпоинты только по документации https://iss.moex.com.
- `aqr/pipeline/events.py` — контракт `Event`, на нём завязан SSE UI. Ломать поля осторожно.

## Разрешено активно менять

- `aqr/pipeline/planner.py` — правила разбора русского запроса. Добавить тикеры/семейства/категории — здесь.
- `aqr/pipeline/hypotheses.py` — новые семейства гипотез. Формат: функция `(prices: pd.Series) -> pd.Series` возвращает позицию -1/0/+1.
- `aqr/pipeline/narrator.py` — стиль отчёта.
- `aqr/pipeline/executor.py` — оркестрация шагов. Если добавляешь новый шаг, эмить события через `_emit()`.

## Инварианты, которые нельзя нарушать

1. **Никакого look-ahead**. В `_backtest_one` позиция сдвигается на 1 бар (`shift(1)`). Не убирать.
2. **Fallback обязателен**. Планировщик и нарратор ДОЛЖНЫ работать без LLM-ключей. Не удаляй `_fallback_plan` / `_fallback_narrate`.
3. **События идут в порядке**: `planning → data → generating → backtesting × N → validating → insight × M → narrating → done`. При ошибке — `error`.
4. **Один процесс, никаких брокеров**. Если нужен фон — `asyncio.create_task`. Не тащить Redis / Celery / RQ.
5. **Валидация — источник истины**. Sharpe без DSR не показывать пользователю как «значимый».

## Как запускать локально

```bash
pip install -e ".[dev]"

# 1. Прогон CLI
python -m aqr "проверь momentum на голубых фишках"

# 2. HTTP-сервер
uvicorn aqr.main:app --reload --port 8000
curl -s -X POST http://localhost:8000/pipeline/runs \
  -H "Content-Type: application/json" \
  -d '{"goal":"проверь mean reversion на Газпроме"}'

# 3. Тесты
pytest tests/ -v
```

## Как добавить новое семейство гипотез

1. В `aqr/pipeline/hypotheses.py` добавить функцию-сигнал `_my_signal(param1, param2)` возвращающую `(prices) -> positions`.
2. В `_make_one()` добавить ветку `if family == "my_family": ...` с генерацией параметров.
3. В `aqr/pipeline/planner.py`:
   - добавить ключевые слова в `_fallback_plan()` (например, `"мой_паттерн" → "my_family"`)
   - добавить в `PLANNER_SYSTEM` описание для LLM
4. В `tests/test_pipeline_e2e.py` добавить проверку что план с этим ключевым словом даёт правильный family.
5. Прогнать `pytest tests/`.

## Как добавить новый MOEX-инструмент

1. В `aqr/pipeline/planner.py::MOEX_TICKERS` добавить тикер.
2. В `_extract_tickers()` добавить русское название в `aliases` или в категорию (голубые фишки / банки / металлурги).
3. Проверить `python -m aqr "проверь <название>"` находит тикер.

## Проверка перед PR

```bash
pytest tests/ -v                              # 17 должны быть зелёные
python -m aqr "проверь momentum на Сбере"     # end-to-end проходит
ruff check aqr/ tests/                        # линтер
```

## Что явно вне scope сейчас

- Транзакционные издержки и slippage в бэктесте (наибольший приоритет когда решим этим заняться)
- Многопользовательский режим, аутентификация
- Хранилище прошлых run'ов (сейчас всё in-memory в EventBus)
- Reinforcement learning / auto-ML на гипотезах
- Live-trading, брокерская интеграция

Если пользователь просит что-то из этого списка — обсудить план прежде чем реализовывать: это большой шаг.

## Файлы, которые ты почти всегда трогаешь

| Задача | Файлы |
|---|---|
| Новое семейство гипотез | `pipeline/hypotheses.py`, `pipeline/planner.py`, `tests/test_pipeline_e2e.py` |
| Улучшение отчёта | `pipeline/narrator.py` |
| Новый MOEX-тикер / алиас | `pipeline/planner.py` |
| Новый шаг пайплайна | `pipeline/executor.py`, `pipeline/events.py` (если нужен новый kind) |
| Новый HTTP endpoint | `pipeline/api.py`, `main.py` |
| Новая валидационная метрика | `validation/` + `tests/test_validation.py` |

## Стиль

- Type hints с `from __future__ import annotations`
- Комментарии по-русски там, где помогают понять контекст; docstring по-английски или по-русски, консистентно в модуле
- Никаких emoji в коде
- Модуль не длиннее 400 строк — иначе разбивать
