# Что нужно чтобы AQR Stream стал автономным research engine

## Аудит текущей системы

**Что уже есть:**
- Генераторы (5 типов LLM-агентов, работают 24/7)
- Backtest workers
- DuckDB для гипотез/результатов
- FAISS для semantic dedup
- Hourly insight extraction
- React dashboard

**Чего критически не хватает:**

| # | Пробел | Почему это блокирует автономность |
|---|---|---|
| 1 | **Иерархическая память** | Insights теряются через 24ч, нет накопления опыта |
| 2 | **Data Curator** | Никто не следит за качеством/актуальностью рыночных данных |
| 3 | **Research Planner** | Нет long-term стратегии — просто generate/test |
| 4 | **Portfolio Constructor** | Топ гипотезы висят в вакууме, не собираются в портфель |
| 5 | **Live Monitor** | Найденные стратегии не отслеживаются на живом рынке |
| 6 | **Failure Analyst** | Когда стратегия ломается — никто не понимает почему |
| 7 | **Literature Reader** | Не читает статьи/новости для инспирации |
| 8 | **Skill Library** | Каждый раз изобретает блоки заново, не накапливает переиспользуемые |
| 9 | **Self-Reflection** | Не проверяет собственные ошибки в рассуждениях |
| 10 | **Human-in-the-loop** | Нет способа корректировать курс без изменения кода |

Пройдёмся по каждому.

---

## 1. Иерархическая память (Multi-tier Knowledge Storage)

**Проблема:** сейчас у нас плоская таблица `insights` где строки помечаются inactive через 24ч. Это **амнезия**. Через неделю система забудет, что "z-fade на 10m не работает" и снова начнёт это генерировать.

**Решение — 4-уровневое хранилище:**

```
┌──────────────────────────────────────────────────────────────┐
│  L4: LAWS (immutable, ~10-100)                                │
│      Фундаментальные истины подтверждённые >1000 гипотез     │
│      "Тик 0.01 на MOEX для акций < 1000 руб"                 │
│      "Комиссии MOEX round-trip ≈ 6bp"                        │
├──────────────────────────────────────────────────────────────┤
│  L3: HEURISTICS (semi-permanent, ~100-500)                   │
│      Устойчивые паттерны с confidence > 0.85                 │
│      "z-fade lb 50-100 доминирует в TREND_DN (n>500)"        │
│      Проверяются раз в неделю на свежих данных               │
├──────────────────────────────────────────────────────────────┤
│  L2: HYPOTHESES (working memory, ~1k-10k)                    │
│      Активные insights последних 24-72ч                      │
│      Промпты генераторов инжектят это                        │
├──────────────────────────────────────────────────────────────┤
│  L1: RAW EVENTS (short-term, ~50k-500k)                      │
│      Каждый backtest, каждое сообщение агента                │
│      Хранится 30 дней, потом агрегируется в L2               │
└──────────────────────────────────────────────────────────────┘
```

**Реализация:**

```python
# aqr/memory/store.py

class MemoryStore:
    """4-tier knowledge storage с автоматической promotion/demotion."""

    async def promote_hypothesis_to_heuristic(self):
        """L2 → L3: hypothesis существующий >72ч и подтверждённый >100 гипотез."""
        candidates = db.query("""
            SELECT text, evidence_hypothesis_ids
            FROM insights
            WHERE created_at < NOW() - INTERVAL 72 HOUR
              AND array_length(evidence_hypothesis_ids) > 100
              AND confidence > 0.85
        """)
        for c in candidates:
            # Проверяем что паттерн ещё работает на свежих данных
            still_valid = await self.validate_on_recent(c)
            if still_valid:
                await db.insert("heuristics", c)
                await db.mark_promoted(c.id)

    async def promote_heuristic_to_law(self):
        """L3 → L4: heuristic существующий >30 дней и никогда не опровергался."""
        # ...

    async def demote_stale(self):
        """Обратный процесс — если heuristic перестал работать на свежих данных."""
        for h in db.query("SELECT * FROM heuristics WHERE last_validated < NOW() - 7 DAYS"):
            valid = await self.validate_on_recent(h)
            if not valid:
                await db.demote(h.id, reason="failed_recent_validation")

    async def retrieve_for_generator(self, generator_type: str, category: str, k: int = 20):
        """Умная выборка: laws + relevant heuristics + fresh insights."""
        laws = db.query("SELECT * FROM laws WHERE ? = ANY(applies_to) LIMIT 10", generator_type)
        heuristics = await vector_search("heuristics", query=category, k=15)
        fresh = db.query("SELECT * FROM insights WHERE is_active LIMIT 5")
        return {"laws": laws, "heuristics": heuristics, "fresh": fresh}
```

**Semantic retrieval:** каждый L2/L3/L4 запись имеет embedding → генератор при работе с категорией "arb" получает **релевантные heuristics** через vector search, а не все подряд.

## 2. Data Curator Agent

**Проблема:** генератор придумывает "SBER × GAZP на 1min", а бэктестер молча падает потому что 1min данных нет. Или ещё хуже — они есть, но с gap'ами, и backtest даёт ложный Sharpe.

**Решение — отдельный агент отвечающий за данные:**

```python
class DataCuratorAgent:
    """
    Работает раз в сутки.
    Проверяет:
    - какие датасеты есть в кэше
    - актуальны ли (last_bar > NOW - 1 day)
    - есть ли gap'ы, аномалии, splits, corporate actions
    - какие новые датасеты стоит подтянуть (по частым hypothesis-запросам)
    """

    async def audit(self):
        report = {"stale": [], "gaps": [], "missing": []}
        for dataset in db.query("SELECT DISTINCT assets, timeframe FROM hypotheses"):
            data = load_market_data(dataset.assets, dataset.timeframe)
            if data.last_bar < now() - timedelta(days=1):
                report["stale"].append(dataset)
            gap_pct = compute_gaps(data)
            if gap_pct > 0.05:
                report["gaps"].append((dataset, gap_pct))

        # LLM решает что делать
        plan = await llm.plan_data_actions(report)
        # → скачать новое, вычистить дубликаты, поправить splits
        await execute_plan(plan)

    async def request_new_dataset(self, hypothesis: Hypothesis):
        """Если гипотеза требует данные которых нет — LLM пишет loader."""
        # "user хочет sberbank options data" → LLM генерирует код через litellm tool call
        code = await llm.generate_loader_code(hypothesis.assets, hypothesis.timeframe)
        # sandbox execute, validate, добавить в registry
```

**Storage для данных:**

```
workspace/data/
├── raw/                          # первичные скачивания (parquet)
│   ├── moex/
│   │   ├── SBER_1d.parquet
│   │   └── SBER_1h.parquet
│   ├── binance/
│   └── yfinance/
├── curated/                      # почищенное, с corporate actions
│   └── SBER_1d_adjusted.parquet
├── features/                     # предвычисленные features
│   ├── SBER_returns_zscore_50.parquet
│   └── SBER_regimes_kmeans4.parquet
└── manifest.duckdb               # metadata: last_updated, gaps, quality_score
```

## 3. Research Planner (стратегическое мышление)

**Проблема:** сейчас Explorer тупо генерирует "новое". Но что если он миллион раз генерирует вариации того же самого класса? Нет **исследовательского плана**.

**Решение — Planner Agent запускается раз в день:**

```python
class ResearchPlannerAgent:
    """
    Каждое утро (9:00 МСК) читает всю базу, генерирует research agenda на сутки.
    """

    async def daily_plan(self):
        # 1. Что мы знаем? (retrieve from L3-L4)
        knowledge = await memory.summarize_current_state()

        # 2. Где gap'ы? (categories без покрытия / низкий Sharpe)
        gaps = db.query("""
            SELECT category, timeframe, COUNT(*) as n_tested,
                   AVG(r.sharpe) as avg_sharpe
            FROM hypotheses h LEFT JOIN backtest_results r ON h.id = r.hypothesis_id
            GROUP BY category, timeframe
            HAVING avg_sharpe < 1 OR n_tested < 100
        """)

        # 3. LLM пишет agenda
        agenda = await llm.generate_research_agenda(knowledge, gaps)
        # {
        #   "focus_areas": ["intraday microstructure MOEX metals", "carry USD-CNY"],
        #   "avoid_areas": ["наши winners in TREND_UP — там уже мы имеем 50 стратегий"],
        #   "hypotheses_target": {"explorer": 100, "exploiter": 500, ...},
        #   "budget_shift": {"explorer": +20%, "exploiter": -10%}
        # }

        # 4. Записать план + обновить конфиги генераторов
        db.insert("research_plans", agenda)
        for gen in generators:
            gen.set_focus(agenda.focus_areas)
            gen.set_avoid(agenda.avoid_areas)
```

**Иерархия целей:**

```
Long-term goal (month):
  "Найти 3 стратегии с Sharpe > 5, uncorrelated, capacity > $1M"
  ↓
Weekly plan:
  "Week 34: покрыть microstructure gap на MOEX metals"
  ↓
Daily plan:
  "Today: 500 hypotheses в intraday microstructure, focus GD/SILV/HGZ"
  ↓
Hourly execution:
  Generators работают по плану, insight_loop корректирует
```

## 4. Portfolio Constructor Agent

**Проблема:** мы находим 100 стратегий с Sharpe > 3, а дальше что? Нужно построить **portfolio**, где они не коррелированы.

```python
class PortfolioConstructorAgent:
    """
    Раз в день собирает диверсифицированный портфель из топ-стратегий.
    """

    async def construct(self):
        top = db.query("SELECT * FROM backtest_results WHERE sharpe > 3 ORDER BY sharpe DESC LIMIT 200")

        # 1. Correlation matrix returns'ов
        returns = load_returns_for_all(top)
        corr = returns.corr()

        # 2. Hierarchical clustering по корреляциям
        clusters = hierarchical_cluster(corr, threshold=0.3)

        # 3. LLM выбирает по 1-2 представителя из каждого кластера
        selection = await llm.pick_portfolio(top, clusters, target_size=20)

        # 4. Optimal weights (risk parity / mean-variance)
        weights = compute_risk_parity_weights(selection)

        # 5. Backtest portfolio
        portfolio_metrics = backtest_portfolio(selection, weights)

        db.insert("portfolios", {
            "selection": selection, "weights": weights,
            "metrics": portfolio_metrics, "created_at": now(),
        })
```

**Артефакт**: `workspace/portfolios/` — история портфелей с snapshot'ами и метриками.

## 5. Live Monitor Agent (Paper Trading)

**Проблема:** гипотеза с Sharpe 15 in-sample — не гарантия работы live. Нужно **paper trade** топ-стратегии на реальных котировках.

```python
class LiveMonitorAgent:
    """
    Каждые 5-15 минут:
    - Забирает live котировки для активных стратегий
    - Пересчитывает сигналы
    - Логирует "если бы торговали"
    """

    async def monitor_loop(self):
        active = db.query("SELECT * FROM live_strategies WHERE status = 'paper'")
        for strat in active:
            new_bar = await fetch_latest_bar(strat.assets, strat.timeframe)
            signal = compute_signal(strat, new_bar)

            if signal != strat.last_signal:
                db.insert("paper_trades", {
                    "strategy_id": strat.id, "signal": signal,
                    "price": new_bar.close, "timestamp": now(),
                })

            # Deviation alert: если реальные returns сильно расходятся с in-sample
            deviation = compare_live_vs_backtest(strat.id)
            if deviation.zscore > 2:
                await alert(f"Strategy {strat.id} degrading: {deviation}")
```

**Промоут в live:**

```
sharpe > 3 in-sample
  → paper trade 30 days
  → sharpe_live vs sharpe_is delta < 30%
  → promote to "live" tier
```

## 6. Failure Analyst Agent

**Проблема:** стратегия сломалась. Почему? Режим сменился? Vol упал? Ликвидность? Никто не разбирается.

```python
class FailureAnalystAgent:
    """
    Триггерится когда live-стратегия теряет > 2 sigma от backtest returns.
    """

    async def diagnose(self, strategy_id: str):
        # 1. Собрать всё: последние 100 сделок, market state, режим, конкуренты
        context = await gather_diagnostic_context(strategy_id)

        # 2. LLM с thinking проводит анализ
        diagnosis = await llm.diagnose_failure(context)
        # {
        #   "primary_cause": "regime shifted from TREND_DN to FLAT since 2026-05",
        #   "secondary": "volatility dropped 40%, edge compressed",
        #   "confidence": 0.82,
        #   "action": "pause_and_regenerate",
        #   "similar_past_failures": [...]
        # }

        # 3. Действие
        if diagnosis.action == "pause_and_regenerate":
            await pause_strategy(strategy_id)
            # Триггерим Adversary generator сделать stress-версии
            await queue_adversarial_hypotheses(strategy_id)
```

**Learning:** каждый failure → insight в L2 (или L3 если серьёзный). "Regime shift сломал N стратегий класса X" → в будущем Explorer знает добавлять regime hedge.

## 7. Literature Reader Agent

**Проблема:** мы изобретаем колесо. В арXiv каждую неделю появляются новые quant paper'ы. Наш агент их не читает.

```python
class LiteratureReaderAgent:
    """
    Раз в неделю: читает свежие arXiv q-fin, SSRN quant, top blogs.
    """

    async def weekly_scan(self):
        sources = [
            "https://arxiv.org/list/q-fin.TR/recent",
            "https://arxiv.org/list/q-fin.CP/recent",
            "https://papers.ssrn.com/sol3/JELJOUR_Results.cfm?form_name=journalBrowse&journal_id=203",
            # Alphalens, Robot Wealth, Ernest Chan blog, etc
        ]

        for src in sources:
            papers = await fetch_papers(src, days=7)
            for paper in papers:
                summary = await llm.summarize_actionable(paper)
                if summary.actionable:
                    # Автоматически создаёт "seed hypothesis" для Explorer
                    await queue_seed_hypothesis({
                        "hypothesis": summary.strategy_idea,
                        "source": paper.title,
                        "seed_from": "literature",
                    })
                    await memory.add_insight(summary.key_finding, source="literature")
```

**Хранение:**

```
workspace/literature/
├── arxiv/
│   └── 2026-07-10_2405.12345_pair_trading_lstm.pdf
├── summaries.duckdb              # {paper_id, title, summary, actionable_ideas[]}
└── seed_hypotheses.csv           # что сгенерили из статей
```

## 8. Skill Library — переиспользуемые блоки

**Проблема:** Coder агент постоянно "изобретает" код для одних и тех же операций. Нужна **растущая библиотека блоков**.

**Текущее:** `strategies/blocks.py` — 5-10 hardcoded блоков.

**Автономная версия:**

```python
class BlockRegistry:
    """
    Растущая библиотека блоков.
    Coder может: (1) использовать существующий (2) написать новый + сохранить.
    """

    def __init__(self, path="workspace/blocks/"):
        self.blocks = self._load_all()

    def register(self, block_code: str, tests: list, metadata: dict):
        """
        Регистрация нового блока.
        Проверки:
        - код синтаксически корректен (ast.parse)
        - тесты проходят
        - нет data leakage (использует только past data)
        - производительность (bench: <100ms per 1000 bars)
        """
        block_id = hash(block_code)
        if self._duplicate_check(block_code):
            return None  # уже есть похожий

        if not self._run_tests(block_code, tests):
            return None

        self._save(block_id, block_code, metadata)
        db.insert("block_registry", {...})
        return block_id

    async def suggest_new_block(self, hypothesis: Hypothesis):
        """
        Если Coder не нашёл подходящего блока — LLM пишет новый.
        """
        code = await llm.generate_block_code(hypothesis, existing_blocks=self.blocks)
        tests = await llm.generate_block_tests(code)
        block_id = self.register(code, tests, metadata={...})
        return block_id
```

**Storage:**

```
workspace/blocks/
├── registry.duckdb
├── code/
│   ├── b_00001_pair_z_fade.py
│   ├── b_00002_wide_range_fade.py
│   ├── b_00147_regime_conditional_carry.py    # автогенерированный
│   └── ...
└── tests/
    ├── b_00001_test.py
    └── ...
```

Через месяц: 100-500 блоков, каждый **протестирован** и **использовался >10 раз**.

## 9. Self-Reflection Loop

**Проблема:** LLM ошибается. Экономически бессмысленные гипотезы, look-ahead bias, over-fitting. Нам нужен внутренний критик уровня "проверь себя".

```python
class ReflectionAgent:
    """
    После N гипотез генератор ставит паузу и рефлексирует:
    - какие мои недавние гипотезы дали высокий Sharpe?
    - что общего у неудач?
    - какие мои допущения оказались неверными?
    - переписать промпт следующей сессии
    """

    async def reflect(self, generator_type: str):
        recent = db.query("""
            SELECT h.*, r.sharpe, r.pvalue
            FROM hypotheses h JOIN backtest_results r ON h.id = r.hypothesis_id
            WHERE h.generator_type = ? AND h.created_at > NOW() - INTERVAL 6 HOUR
        """, generator_type)

        reflection = await llm.reflect(recent, thinking_budget=4000)
        # {
        #   "what_worked": ["z-fade thr 2-3", "MOEX pairs same sector"],
        #   "what_failed": ["10m timeframe", "cross-country pairs"],
        #   "biases_detected": ["избыток momentum, недостаток mean-reversion"],
        #   "new_prompt_addendum": "Prefer mean-reversion over momentum in next batch"
        # }

        # Обновляем промпт агента
        await update_agent_prompt(generator_type, reflection.new_prompt_addendum)
```

**Как встраивается:**

Каждые ~1000 гипотез генератора → reflect. LLM Sonnet thinking с большим budget. Обновление промпта версионируется:

```
prompts/
├── explorer/
│   ├── v001_initial.j2
│   ├── v002_reflection_2026-07-11.j2       # автоматически
│   ├── v003_reflection_2026-07-13.j2
│   └── current -> v003_reflection_2026-07-13.j2
```

## 10. Human-in-the-loop через natural language

**Проблема:** сейчас чтобы поменять курс — нужно править код или yaml. Автономная система должна **слушать инструкции текстом**.

```python
class DirectorInterface:
    """
    Приём инструкций от пользователя в UI/Slack/CLI.
    """

    async def process_directive(self, text: str):
        # "Забудь про USD-CNY, фокус на MOEX металлах ближайшие сутки"
        parsed = await llm.parse_directive(text)
        # {
        #   "action": "focus_shift",
        #   "avoid": ["USD-CNY", "forex"],
        #   "prioritize": ["MOEX metals: GD, SILV, HGZ, PLD"],
        #   "duration_hours": 24,
        # }

        # Применить к research plan
        await research_planner.override(parsed, expires_in_hours=24)

        # Логировать директиву
        db.insert("directives", {"text": text, "parsed": parsed, "user": user})
```

Реализация в UI: **command palette** с примерами:
- "Focus on X"
- "Pause generator Y"
- "Report progress on Z"
- "What's your current hypothesis about market regime?"

---

## Единая архитектура автономного engine

```
                      ┌───────────────────────┐
                      │   DIRECTOR (human)    │
                      │   NL commands via UI  │
                      └──────────┬────────────┘
                                 │
                                 ▼
             ┌────────────────────────────────────┐
             │      RESEARCH PLANNER AGENT        │◄─┐
             │      (daily agenda, priorities)    │  │
             └──────────────┬─────────────────────┘  │
                            │ agenda                 │
                            ▼                        │
    ┌────────────┬─────────────────┬────────────┐    │
    ▼            ▼                 ▼            ▼    │
 ┌─────────┐ ┌──────────┐ ┌──────────────┐ ┌───────────┐
 │ DATA    │ │ 5 GEN    │ │ REFLECTION   │ │ LITERATURE│
 │ CURATOR │ │ AGENTS   │ │ AGENT        │ │ READER    │
 └────┬────┘ └────┬─────┘ └──────┬───────┘ └─────┬─────┘
      │           │              │               │
      ▼           ▼              │               │
 ┌────────┐  ┌────────────┐      │               │
 │ Data   │  │ Backtest   │      │               │
 │ store  │  │ workers    │      │               │
 └────────┘  └──────┬─────┘      │               │
                    │            │               │
                    ▼            │               │
             ┌──────────────────────────────┐    │
             │  4-TIER MEMORY               │◄───┘
             │  L1 events / L2 hyp /        │
             │  L3 heuristics / L4 laws     │◄──feedback loop
             └──────┬───────────────────────┘
                    │ retrieve
                    ▼
    ┌──────────────────┬───────────────────┐
    │                  │                   │
    ▼                  ▼                   ▼
┌─────────────┐  ┌──────────────┐  ┌──────────────┐
│ PORTFOLIO   │  │ LIVE MONITOR │  │ FAILURE      │
│ CONSTRUCTOR │  │ (paper)      │  │ ANALYST      │
└─────────────┘  └──────┬───────┘  └──────▲───────┘
                        │                 │
                        └─── degradation ─┘
```

## Единое хранилище — full spec

```
workspace/
├── aqr.duckdb                # основная БД
│   ├── hypotheses            (было)
│   ├── backtest_results      (было)
│   ├── llm_calls             (было)
│   ├── memory_events         (L1)
│   ├── insights              (L2, было)
│   ├── heuristics            (L3, NEW)
│   ├── laws                  (L4, NEW)
│   ├── research_plans        (NEW)
│   ├── directives            (NEW)
│   ├── portfolios            (NEW)
│   ├── live_strategies       (NEW)
│   ├── paper_trades          (NEW)
│   ├── failure_diagnoses     (NEW)
│   ├── block_registry        (NEW)
│   └── literature_summaries  (NEW)
│
├── data/                     # market data (parquet)
│   ├── raw/
│   ├── curated/
│   ├── features/
│   └── manifest.duckdb
│
├── blocks/                   # code + tests
│   ├── code/
│   ├── tests/
│   └── registry.duckdb
│
├── prompts/                  # versioned per generator
│   ├── explorer/
│   ├── exploiter/
│   ├── ...
│   └── history.duckdb        # какая версия когда была активна
│
├── literature/               # прочитанные paper'ы
│   ├── arxiv/
│   ├── ssrn/
│   ├── blogs/
│   └── summaries.duckdb
│
├── portfolios/               # snapshots
│   └── 2026-07-11_v1.json
│
├── faiss/
│   ├── hypotheses.index      # dedup
│   ├── heuristics.index      # retrieval
│   ├── laws.index
│   └── literature.index      # RAG для чтения статей
│
└── traces/                   # Langfuse dumps
    └── ...
```

## Roadmap внедрения

**Phase 1 — Memory + Blocks (2 недели)**
- 4-tier memory store
- Block registry с автотестами
- Semantic retrieval для генераторов

**Phase 2 — Data + Planner (2 недели)**
- Data Curator agent
- Research Planner (daily agenda)
- Directives interface в UI

**Phase 3 — Portfolio + Live (3 недели)**
- Portfolio Constructor
- Paper trading loop
- Live Monitor + drift detection

**Phase 4 — Autonomous learning (3 недели)**
- Failure Analyst
- Reflection loop
- Literature Reader
- Full feedback closure

## Метрики автономности

Как понять что система реально автономна:

| Метрика | Baseline | Autonomous |
|---|---|---|
| Human interventions/week | ~10 | **<1** |
| Time to detect strategy failure | days | **hours** |
| Novel patterns discovered/week | 0 | **3-10** |
| Blocks in registry | 5 | **>200** |
| Portfolio Sharpe (live paper) | — | **>2** |
| Cost per validated strategy | $50-200 | **<$20** |
| Recovery from regime shift | manual code | **automatic** |

## Что ещё критически важно (короткий список)

- **Sandbox execution** — Coder генерирует Python код, его нужно безопасно исполнять (Docker / Firejail / RestrictedPython)
- **Git-подобное версионирование стратегий** — diff между версиями "GD-Gold z-fade v1 → v2 (added regime filter)"
- **Cost anomaly detection** — если генератор внезапно тратит 5× больше — pause + alert
- **Reproducibility** — каждый backtest должен reproduce'ться (seed, data snapshot, code version)
- **Alerts hierarchy** — critical → PagerDuty, warning → Slack, info → dashboard only

---

## Итого

Сейчас у нас **умный конвейер**. Чтобы стать **автономным исследователем**, нужны 10 компонентов сверху:

1. Memory (4-tier)  
2. Data Curator  
3. Research Planner  
4. Portfolio Constructor  
5. Live Monitor  
6. Failure Analyst  
7. Literature Reader  
8. Block Registry  
9. Reflection Loop  
10. Human directives

Все они — **LLM agents**, каждый со своей ответственностью и промптом. Общаются через shared DuckDB и Redis events. Это уже полноценный **quant research firm в коробке**.
