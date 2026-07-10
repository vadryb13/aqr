# Архитектура AQR Stream

## Ключевые принципы

1. **Continuous, not batch** — гипотезы генерируются 24/7, а не пачками по расписанию
2. **Multi-strategy generation** — 5+ разных generator'ов работают параллельно
3. **Feedback от результатов** — генераторы читают DuckDB и учатся на своих же результатах
4. **Semantic deduplication** — не дублировать идеи, сравнивая embedding'и
5. **Backpressure** — очередь регулирует темп работы, чтобы не переполнить workers

## Стек

| Слой | Технология |
|---|---|
| Data storage | **DuckDB** (embedded OLAP, 100M+ rows на 1 машине) |
| Vector store | **FAISS** (semantic dedup) или **pgvector** если много клиентов |
| Message queue | **Redis Streams** (persistent, consumer groups) |
| LLM providers | **litellm** → Anthropic Haiku / GPT-4-mini / GigaChat |
| Embeddings | `text-embedding-3-small` (cheap, 1536d) или sentence-transformers локально |
| Orchestration | **Prefect** (dataflow с retry, monitoring) ИЛИ pure async |
| Tracing | **Langfuse** |
| Metrics | **Prometheus + Grafana** |
| API | **FastAPI + SSE** |
| UI | React + Tremor dashboards |

## Data Model (DuckDB)

```sql
-- Основная таблица гипотез
CREATE TABLE hypotheses (
    id VARCHAR PRIMARY KEY,               -- uuid
    generator_type VARCHAR,                -- explorer/exploiter/mutator/...
    generator_version VARCHAR,             -- v2.3-2026-07
    hypothesis TEXT,                       -- description
    rationale TEXT,
    category VARCHAR,
    assets VARCHAR[],
    timeframe VARCHAR,
    block_name VARCHAR,
    params JSON,
    expected_sharpe DOUBLE,
    embedding FLOAT[1536],                 -- semantic hash
    created_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR                          -- pending/duplicate/tested/failed
);

-- Результаты backtest'ов
CREATE TABLE backtest_results (
    id VARCHAR PRIMARY KEY,
    hypothesis_id VARCHAR REFERENCES hypotheses(id),
    n INTEGER,
    sharpe DOUBLE,
    sortino DOUBLE,
    pvalue DOUBLE,
    max_dd DOUBLE,
    win_rate DOUBLE,
    total_pct DOUBLE,
    turnover DOUBLE,
    tc_bp INTEGER,
    -- разбивка по режимам
    best_regime VARCHAR,
    regime_breakdown JSON,
    -- stress-test
    sharpe_test_5bp DOUBLE,
    tc_curve JSON,
    -- meta
    backtest_duration_ms INTEGER,
    tested_at TIMESTAMP DEFAULT NOW()
);

-- Insights - агрегированные выводы от meta-LLM
CREATE TABLE insights (
    id VARCHAR PRIMARY KEY,
    generation INTEGER,                    -- поколение hourly cycle
    insight TEXT,                          -- "z-fade works better when vol > median"
    evidence_ids VARCHAR[],                -- hypothesis_id supporting this
    confidence DOUBLE,
    applied_to_generators VARCHAR[],       -- какие агенты обновили промпт
    created_at TIMESTAMP DEFAULT NOW()
);

-- Индексы
CREATE INDEX idx_hyp_status ON hypotheses(status);
CREATE INDEX idx_hyp_generator ON hypotheses(generator_type);
CREATE INDEX idx_res_sharpe ON backtest_results(sharpe DESC);
CREATE INDEX idx_res_hyp ON backtest_results(hypothesis_id);
```

## Generator Types

Каждый генератор — long-running async task, читающий контекст из DuckDB и пуляющий гипотезы в Redis Stream.

### 1. Explorer (creative, exploration)
- **Модель**: Sonnet 4.5 thinking
- **Промпт**: "Придумай что-то новое, чего нет в базе"
- **Контекст**: список категорий + активов + недавние Sharpe distributions
- **Rate**: 5-10 гипотез/минуту (медленно, но разнообразно)
- **Бюджет**: 20% общего

### 2. Exploiter (варьирует winners)
- **Модель**: Haiku (fast, cheap)
- **Промпт**: "Возьми топ-100 стратегий, сделай 20 вариаций каждой"
- **Контекст**: `SELECT * FROM backtest_results WHERE sharpe > 5 ORDER BY sharpe DESC LIMIT 100`
- **Rate**: 100+ гипотез/минуту
- **Бюджет**: 40%

### 3. Mutator (комбинирует блоки)
- **Модель**: Haiku
- **Промпт**: "Возьми 2 работающих блока и объедини их в новую композицию"
- **Пример**: z-fade + regime filter + hour filter = новая тройка
- **Rate**: 50 гипотез/минуту
- **Бюджет**: 20%

### 4. Adversary (challenger)
- **Модель**: Sonnet 4.5
- **Промпт**: "Найди WHY существующая топ-стратегия должна СЛОМАТЬСЯ. Что её отменит?"
- **Контекст**: топ-10 стратегий + их результаты
- **Цель**: генерирует **stress-тесты**, а не новые стратегии
- **Rate**: 2 hyp/минуту
- **Бюджет**: 10%

### 5. RegimeSpecialist
- **Модель**: Haiku
- **Промпт**: "Для режима TREND_DN найди 20 стратегий, которые должны работать особенно хорошо"
- **Контекст**: regime-conditional таблица
- **Rate**: 30 hyp/минуту
- **Бюджет**: 10%

## Feedback Loop (Insight Extraction)

Раз в час запускается **meta-LLM job**:

```python
async def hourly_insight_loop():
    # 1. Забрать последние 5000 результатов
    recent = duckdb.execute("""
        SELECT h.*, r.*
        FROM hypotheses h JOIN backtest_results r ON h.id = r.hypothesis_id
        WHERE r.tested_at > NOW() - INTERVAL 1 HOUR
    """).df()
    
    # 2. Meta-LLM ищет паттерны
    llm = make_llm("meta", model="claude-sonnet-4-5-thinking")
    insights = await llm.extract_patterns(recent, existing_insights)
    
    # 3. Сохранить в DB
    for ins in insights:
        db.insert("insights", ins)
    
    # 4. Обновить промпты генераторов
    for generator in generators:
        generator.inject_insights([i for i in insights if i.applies_to(generator.name)])
    
    # 5. Ребалансировка бюджета
    perf = analyze_generator_performance(recent)
    budget_allocator.rebalance(perf)  # если Exploiter лучше — дать ему больше $
```

**Пример извлечённого insight'a**:
> "z-fade на MOEX-парах даёт средний Sharpe 4.2 vs 1.8 на межстрановых парах.  
> Confidence: 0.87, evidence: 342 гипотез.  
> Рекомендация: Exploiter — приоритет на MOEX-MOEX пары."

Этот insight автоматически инжектируется в промпт Exploiter'а как:
> "Приоритет: MOEX-MOEX пары (эмпирически в 2.3× лучше межстрановых)."

## Semantic Deduplication

Каждая гипотеза при генерации получает embedding через `text-embedding-3-small`.

Перед вставкой в очередь:

```python
async def dedup_check(hyp: Hypothesis, faiss_index) -> bool:
    emb = await embed(hyp.hypothesis + hyp.rationale)
    # Поиск ближайших 5 соседей
    dists, idxs = faiss_index.search(emb, k=5)
    if dists[0] < 0.15:  # cosine distance
        return False  # это дубликат
    faiss_index.add(emb)
    return True
```

Экономия: обычно 40-60% гипотез отбрасываются как дубли (это норма для creative LLM).

## Backtest Workers

Каждый worker — отдельный процесс (multiprocessing), не async:

```python
def backtest_worker(worker_id: int):
    r = redis.Redis()
    while True:
        # Забрать 1 гипотезу
        msg = r.xreadgroup("workers", f"w{worker_id}",
                          {"hypotheses:pending": ">"}, block=5000)
        hyp = deserialize(msg)
        
        # Загрузить данные (кэш DuckDB / pickle)
        data = load_market_data(hyp.assets, hyp.timeframe)
        
        # Backtest
        result = run_full_evaluation(hyp, data)
        
        # Сохранить
        db.insert("backtest_results", result)
        r.xack("hypotheses:pending", "workers", msg.id)
        
        # Публикация "интересного" — если Sharpe > 5
        if result.sharpe > 5:
            r.xadd("hypotheses:top", result.model_dump())
```

## Backpressure

Redis Streams автоматически даёт natural backpressure:
- Если workers не успевают — stream растёт → мониторим `XLEN`
- При XLEN > 10 000 — снижаем rate генераторов (adaptive semaphore)

```python
def adaptive_rate_control():
    while True:
        depth = r.xlen("hypotheses:pending")
        if depth > 10_000:
            slow_down_generators(factor=0.5)
        elif depth < 1000:
            speed_up_generators(factor=2.0)
        await asyncio.sleep(30)
```

## Cost Control

Автоматический stop-loss по бюджету:

```yaml
# config/budget.yaml
daily_limit_usd: 50
per_generator:
  explorer: 15    # $15/day = ~500 Sonnet calls
  exploiter: 20   # $20/day = ~20k Haiku calls
  mutator: 8
  adversary: 5
  regime: 2
alerts:
  slack_webhook: https://hooks.slack.com/...
  stop_at_pct: 90    # stop generators если потрачено 90% дневного лимита
```

Каждый LLM call логируется в Langfuse с cost tag → dashboard в реальном времени.

## API

```python
# FastAPI endpoints
GET  /stats                  # текущая скорость, размер очередей, cost/hour
GET  /top?limit=20           # топ гипотез по Sharpe
GET  /insights               # активные insights от meta-LLM
GET  /generators             # статус каждого генератора (running/paused/errors)
POST /generators/{id}/pause  # пауза конкретного
POST /budget/set_limit       # изменить дневной лимит
GET  /stream/hypotheses      # SSE: живой поток новых гипотез
GET  /stream/top             # SSE: топовые находки (Sharpe > 5)
```

## UI Dashboard (React + Tremor)

```
┌─ Live Feed ─────────────────────────────────────────────┐
│ 14:23:41 [Explorer] sber-lkoh z-fade lb=100 thr=1.8      │
│           Sharpe=3.2 ✓                                    │
│ 14:23:39 [Exploiter] gd-gold z-fade thr=2.5 hr=16        │
│           Sharpe=29.1 🔥                                  │
│ 14:23:37 [Mutator] chmf wide_range × TREND_UP filter     │
│           Sharpe=5.7 ✓                                    │
└──────────────────────────────────────────────────────────┘

┌─ Throughput (last hour) ─────┐  ┌─ Cost ─────────────────┐
│ Generated: 42 831            │  │ Today: $12.40 / $50    │
│ After dedup: 26 122 (61%)    │  │ ▓▓▓░░░░░░░ 25%         │
│ Backtested: 26 122           │  │ Explorer: $4.20        │
│ Sharpe > 3: 341 (1.3%)       │  │ Exploiter: $6.80       │
│ Sharpe > 5: 87 (0.33%)       │  │ ...                    │
└──────────────────────────────┘  └────────────────────────┘

┌─ Generator Performance ──────────────────────────────────┐
│ Generator    │ HypRate │ AvgSharpe │ Top1  │ $/gd_hyp   │
│ ─────────────┼─────────┼───────────┼───────┼───────────── │
│ Explorer     │ 12/min  │ 2.1       │ 15.3  │ $0.052       │
│ Exploiter    │ 89/min  │ 4.7       │ 29.1  │ $0.006       │
│ Mutator      │ 42/min  │ 3.8       │ 18.4  │ $0.011       │
│ Adversary    │  2/min  │ -0.3      │  —    │ $0.180       │
│ RegimeSpec   │ 28/min  │ 3.2       │ 12.6  │ $0.014       │
└──────────────────────────────────────────────────────────┘

┌─ Recent Insights (meta-LLM) ─────────────────────────────┐
│ ★ z-fade lb=50-100 доминирует в TREND_DN режиме (n=847)  │
│ ★ Sector pairs metals >>  domestic tech (Sharpe 6.1 vs 2.3)│
│ ⚠ Wide-range fade деградирует на 10m (survivorship?)     │
│ ★ Hour 15-18 MSK — статистически значимый эффект (p<0.01)│
└──────────────────────────────────────────────────────────┘
```

## Deployment

### Локальный (dev)
```bash
docker-compose up -d   # Redis + DuckDB + Langfuse + Grafana
aqr-stream start       # генераторы + workers + API + insight loop
```

### Production (self-hosted)
```
                ┌─── VPS 1 (генераторы) ────┐
                │  10 explorer/exploiter    │
                │  Haiku/Sonnet LLM calls   │
                └────────────┬──────────────┘
                             │
                             ▼
                ┌─── VPS 2 (Redis + DuckDB) ──┐
                │  msg queue + storage        │
                └────────────┬────────────────┘
                             │
                             ▼
                ┌─── VPS 3 (backtest workers) ┐
                │  20 CPU workers             │
                │  data cache                 │
                └─────────────────────────────┘
```

- Расходы (реалистично): $200/mo VPS + $30-50/day LLM = **~$1500/mo**
- Продуктивность: **~30 000 backtested hypotheses/day**, **~100-300 strategies с Sharpe>3/day**
- Стоимость 1 найденной "хорошей" стратегии: ~$5-15
