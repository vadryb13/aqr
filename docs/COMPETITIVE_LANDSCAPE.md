# AQR vs. LLM+Trading ландшафт 2026

## TL;DR

Мы (AQR) относимся к **другой категории**, чем большинство громких проектов:

- **TradingAgents / AI Hedge Fund / AGENTICAITA** — это **decision-time**: "стоит ли купить AAPL сегодня?" Дебаты аналитиков → trade
- **AlphaCrafter / VARRD ELROND** — **strategy-discovery**: генерация факторов и alpha 
- **FinGPT / FinRL** — **инфраструктура/foundation**: модели и RL-среды
- **AQR (наш проект)** — **research-time**: массовая генерация гипотез, streaming, накопление знания

Наши прямые конкуренты — **AlphaCrafter** и **VARRD**. TradingAgents к нам не относится (мы не принимаем trade-decisions).

---

## Ландшафт: 5 категорий систем

### Категория 1: Multi-agent decision-makers
Симулируют торговую фирму: аналитики → дебаты → trader → risk → portfolio manager. Принимают **конкретное решение** по конкретному тикеру.

| Система | Что делает | Stars | Заметки |
|---------|-----------|-------|---------|
| **TradingAgents** (Tauric Research) | 7 ролей, LangGraph, bull/bear debate → BUY/SELL/HOLD | 82k+ | Reference implementation. Backtest: +26% AAPL, Sharpe 8.21, но 3 мес, 30 LLM calls/decision, никогда не торговал вживую |
| **AI Hedge Fund** | Именованные персонажи (Buffett, Cathie Wood, Munger) дебатируют портфель | 54k+ | Более interpretable, но менее строгий |
| **AGENTICAITA** (arXiv 2605) | 4 агента, deliberative pipeline, live 5-day dry-run на BTC | — | 157 zero-intervention решений, +14.94pp vs BTC B&H, но 5 дней ≠ статистика |
| **FinRobot** (AI4Finance) | Financial Chain-of-Thought, 4 слоя | — | Ближе к research assistant |

### Категория 2: Autonomous strategy-discovery
Ищут **новые edges/factors** без указания тикера. Ближайший класс к нам.

| Система | Что делает |
|---------|-----------|
| **AlphaCrafter** (arXiv 2605.05580) | 3 агента: Miner (LLM-guided factor search) → Screener (regime-aware selection) → Trader (risk-constrained execution). **Hypothesis-validation-execution loop.** Cross-sectional |
| **VARRD ELROND** | 8 investigator агентов (momentum/vol/regime/flow/seasonality/chart/quant/cross-market). Ночью autonomous mode → библиотека validated edges с exact entry/stop/tp |
| **AQR (мы)** | 5 генераторов (Explorer/Exploiter/Mutator/Adversary/Regime), streaming, 30k гипотез/день, 4-tier memory |

### Категория 3: Foundation / infrastructure
Модели и среды, поверх которых строят остальные.

| Система | Что даёт |
|---------|---------|
| **FinGPT** | Fine-tuned finance LLM (open-source альтернатива BloombergGPT) |
| **BloombergGPT** | 50B параметров на finance-тексте, closed |
| **FinRL / FinRL-X** | RL-среды для торговли, интеграция с брокерами |
| **FinNLP** | Datasets pipeline для finance-LLM |

### Категория 4: Live evaluation harness
Проверяют насколько LLM реально работают на живом рынке.

| Система | Что делает |
|---------|-----------|
| **LiveTradeBench** | 50-day live eval (Aug-Oct 2025), 21 LLM, US equities + Polymarket |
| **TraderBench** | Adversarial market manipulation stress-test. 8/13 single-agent LLM развалились |

### Категория 5: Регулируемые "product" платформы
Enterprise-focused, compliance-first.

| Система | Что делает |
|---------|-----------|
| **RocketEdge / MultiEdge** | Signal Fabric + AI Trade Idea Generator + Agentic Research Platform. Azure AI Foundry backbone |
| **Columbia/BlackRock 3-layer** | Академ. работа: bull/bear debate consistently beats S&P 500 |

---

## Прямое сравнение по 12 измерениям

Три главных конкурента:

- **TradingAgents** (decision-maker, самый популярный)
- **AlphaCrafter** (наш класс, strategy discovery)
- **VARRD ELROND** (наш класс, commercial)
- **AQR** (мы)

| # | Измерение | TradingAgents | AlphaCrafter | VARRD | AQR |
|---|-----------|:-:|:-:|:-:|:-:|
| 1 | **Класс задачи** | Decision per ticker | Factor mining + trade | Autonomous edge discovery | Hypothesis streaming |
| 2 | **Continuous vs episodic** | Episodic (запрос → решение) | Daily rotation | Overnight batch | Continuous 24/7 stream |
| 3 | **Throughput** | ~1 decision/hour | Daily factor pool refresh | ~overnight | 30k гипотез/день |
| 4 | **Multi-agent debate** | ✅ Bull/Bear + Risk | Miner/Screener/Trader | 8 investigators | Explorer/Exploiter/Mutator/Adversary |
| 5 | **Memory между runs** | Decision log | Factor pool | Edge library | 4-tier L1-L4 (planned) |
| 6 | **Growing block registry** | ❌ | ❌ | ❌ | ✅ (registry.py с validation) |
| 7 | **Dedup гипотез** | N/A (нет генерации) | Correlation filter | ? | FAISS semantic 0.15 cosine |
| 8 | **Cost tracking** | В paper | ? | Enterprise pricing | Per-generator, per-hypothesis |
| 9 | **Regime adaptation** | ❌ | ✅ (Screener) | ✅ | Trend/flat/crisis классификатор |
| 10 | **Live paper trading** | Backtest only | Executable orders | ? | Planned (Live Monitor gap) |
| 11 | **Portfolio construction** | ✅ PM agent | ✅ | ? | Planned (gap #4) |
| 12 | **Multi-user platform** | ❌ single-user CLI | ❌ | ✅ Web+MCP+CLI | Planned |

---

## Где мы объективно ЛУЧШЕ

### 1. Streaming vs batch — **уникальное преимущество**
Все конкуренты работают **порциями** — TradingAgents делает решение по запросу, AlphaCrafter обновляет factor pool раз в день, VARRD "overnight batch". 

**Мы единственные** запускаем непрерывный поток: генераторы 24/7 → Redis → воркеры → результаты через SSE в реальном времени. Это архитектурная разница как **git commit** vs **live editing** — совсем другая модель работы.

**Почему это важно**: LLM-alpha decays быстро. Кто быстрее адаптируется к regime shift — выигрывает. У нас цикл гипотеза → результат = минуты, а не сутки.

### 2. Growing block registry — **никто не делает**
TradingAgents/AlphaCrafter/VARRD пишут стратегии заново каждый раз. У нас `blocks/registry.py` со syntax→signature→leakage→pytest validation + dedup по hash + track avg Sharpe.

Через 3 месяца работы у нас будет 200+ проверенных reusable-функций. У них — ноль.

### 3. Иерархическая память L1-L4 — **самая продуманная**
| Система | Memory |
|---------|--------|
| TradingAgents | Decision log (плоский) |
| AlphaCrafter | Factor pool (плоский) |
| AGENTICAITA | Audit trail (не для reuse) |
| AQR | L1 events → L2 insights → L3 heuristics → L4 laws (с автопромоцией + revalidation) |

Наша модель ближе к Letta (MemGPT), но специализирована под quant knowledge.

### 4. Adversarial generator — **редкая фича**
Adversary агент (10% budget) специально пытается **сломать топ-стратегии** — стресс-тесты в кризисах, регимы, corner cases. У большинства это отдельный "risk step" в конце, а не непрерывный.

TraderBench показал что 8/13 single-agent LLM ломаются под adversarial manipulation. Наш Adversary работает против собственных находок постоянно.

### 5. Cost-per-Sharpe как first-class метрика
$5-15 per Sharpe>3 finding — мы это трекаем как основную метрику. У TradingAgents "30 LLM calls per decision" — нет системного cost management.

### 6. MOEX focus — **пустая ниша**
Все конкуренты US equity + crypto. MOEX + CNY + русские commodities — почти никто. У нас доменная экспертиза (это твой edge как разработчика).

---

## Где мы объективно ХУЖЕ

### 1. Backtest rigor — **самое слабое место**
TradingAgents имеет reproducible backtest harness с paper (arXiv 2412.20138), результаты цитируемы. AlphaCrafter — статья с proper cross-validation.

У нас — генератор Sharpe чисел без:
- **Deflated Sharpe Ratio** (Bailey/Lopez de Prado) — обязателен для multiple testing
- **Combinatorial Purged Cross-Validation** — стандарт для strategy validation
- **White's Reality Check** / SPA тест
- **Bootstrap CI** для Sharpe

Из 30k гипотез статистически значимы будут единицы после proper корректировки. Мы пока не считаем.

**Что делать**: реализовать DSR + CPCV в `backtest_worker.py`. Это уровень серьёзной quant-фирмы.

### 2. Point-in-time data guarantees — **критично**
TradingAgents реиграет **историю только с данными, доступными на тот момент**. Мы гарантируем это? Нет look-ahead в fundamentals, sentiment, news feeds?

**Что делать**: Data Curator agent с manifest-таблицей "какие данные были известны на момент T". Иначе все Sharpe > 3 подозрительны.

### 3. Debate mechanism — **у нас нет**
Ключевая фича TradingAgents/AGENTICAITA/AlphaCrafter — Bull vs Bear дебаты. Externalizing cognitive tension даёт +returns, показывают Columbia/BlackRock.

У нас Adversary есть, но он **атакует найденную стратегию**, а не **дебатирует про новую гипотезу**. Это разное.

**Что делать**: добавить Critic-Advocate пару, которая дебатирует топ-гипотезы **до** финального ранжирования, не только после.

### 4. Execution / live trading — **полностью отсутствует**
| Система | Broker integration |
|---------|--------------------|
| TradingAgents | Simulated exchange (в v0.7) |
| FinRL-X | Real broker (Alpaca) |
| AGENTICAITA | Live BTC dry-run 5 дней |
| VARRD | Exact entry/stop/tp levels |
| AQR | ❌ ничего |

Backtest-to-live gap — это то место где 90% систем разваливаются. У нас его вообще нет.

**Что делать**: paper trading loop через брокерский MCP + Live Monitor agent. Это gap #5 из "10 missing components".

### 5. Compliance & audit trail — **никак**
RocketEdge пишет: **регуляторы 2026** (MAS Toolkit, OCC 2026-13, EU AI Act Phase 2) требуют named human accountability + traceable decision chains + reproducible audit trails.

У нас Langfuse traces есть, но:
- Нет "который человек ответственен за эту стратегию"
- Нет reproducibility guarantee (data seed + code version + LLM version snapshot)
- Нет kill-switch

Для personal research не критично. Для commercialization — блокер.

### 6. Model tier separation — **у TradingAgents лучше**
TradingAgents: `quick_think_llm` (Haiku/gpt-4o-mini) для сбора данных, `deep_think_llm` (Opus/o1) для решений. Экономия в разы.

У нас — тоже раскидано (Explorer=Sonnet thinking, Exploiter=Haiku), но не так строго. И нет automatic model routing по сложности задачи.

### 7. Multi-user & product polish — **мы в самом начале**
VARRD имеет web app + MCP server + CLI + Python SDK. Мы имеем прототип Tremor UI.

### 8. Community & credibility — **очевидное отставание**
- TradingAgents: 82k stars, AAAI 2025 paper
- AI Hedge Fund: 54k stars  
- FinGPT: часть AI4Finance Foundation с академическим весом
- AQR: 0 stars, свой проект

Пока это не проблема (стадия early). Станет проблемой если захочешь community.

### 9. Anti-crowding — **критичный пробел**
QuantaAlpha paper (arXiv 2602.07085) прямо называет **factor crowding** главным риском LLM alpha mining. Genetic search + trajectory mutation **в момент генерации**, а не ex-post correlation filter.

У нас Mutator есть, но:
- Не проверяем корреляцию с ранее найденным
- Не enforce diversity в промптах генераторов
- Все Explorer вызовы могут случайно сходиться к одной идее

**Что делать**: 
- FAISS-based similarity check **до** запуска backtest (не только после)
- Diversity-boost в промпте Explorer'а с injection "уже искали: [...]"

### 10. Живой benchmark — **нет валидации**
LiveTradeBench проверяет 21 LLM на реальных 50 днях. Мы не знаем как наши гипотезы поведут себя live.

---

## Наш профиль в целом

**Сильные стороны:**
- Уникальная streaming архитектура
- Growing block library (никто не делает)
- Правильная иерархическая память
- Adversarial testing из коробки
- MOEX-специализация

**Слабые стороны:**
- Backtest rigor (нет DSR/CPCV — блокер для доверия)
- Point-in-time guarantees (нет Data Curator)
- Нет живого paper trading
- Нет debate mechanism на этапе гипотезы
- Compliance / audit trail

**Позиционирование**: мы **research infrastructure для quant команды**, а не **turnkey trading bot**. Ближе к "как построить свой мини-Renaissance с LLM" чем к "нажми кнопку → купит AAPL".

---

## Приоритеты чтобы догнать и перегнать

**P0 — не подлежит обсуждению (без этого Sharpe не доказан):**
1. Deflated Sharpe Ratio + CPCV в backtest worker
2. Point-in-time data manifest (Data Curator)
3. Anti-crowding at generation time (не ex-post)

**P1 — критично для credibility:**
4. Debate mechanism между Bull/Bear до финального ранжирования
5. Paper trading loop с реальным брокерским MCP
6. Reproducibility (seed + data snapshot + code version)

**P2 — превратит из "твой pet project" в "продукт":**
7. Multi-user (то что обсудили)
8. Compliance/audit hooks
9. LiveBench-style continuous eval

**P3 — nice to have:**
10. Academic paper (нужен для credibility в quant-community)
11. GitHub OSS release
12. arXiv publication

---

## Что я бы предложил

Три пути:

**A. Research-first**: focus на P0-P1, реализовать DSR/CPCV/Data Curator/Debate → написать статью → выйти как **open-source AlphaCrafter competitor** с фокусом на MOEX. Академ. позиционирование.

**B. Product-first**: focus на P2 (multi-user platform) + minimum P0 (DSR) → продукт для российских quant-команд. Коммерческий путь.

**C. Personal moat**: держать закрытым, доводить до состояния "personal Renaissance", торговать своими деньгами через paper→live loop. Максимальная приватность edges.

Каждый путь имеет разные приоритеты по 12 пунктам. Скажи какой ближе — соберу конкретный roadmap.
