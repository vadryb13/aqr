# Collaborative Agent Platform для AQR

## Что мы хотим построить

Не "запусти скрипт → получи pdf", а **живой чат с командой агентов**:
- есть постоянный "разум" (общая память + tools + traces)
- несколько людей общаются с ним параллельно (Slack / веб / CLI)
- каждый видит что делают другие
- агент помнит всех и все проекты

Аналог: как Perplexity Computer, только заточенный под quant research и multi-user.

---

## Ключевые архитектурные развилки

### 1. Runtime агента — три школы

| Подход | Пример | Плюсы | Минусы |
|--------|--------|-------|--------|
| **OS-style memory** | Letta (MemGPT) | Агент сам управляет памятью, self-editing | Тяжелее, требует Letta server |
| **Vector memory layer** | Mem0 | Простой bolt-on, framework-agnostic | Плоская модель, слабая temporality |
| **Temporal knowledge graph** | Zep / Graphiti | "Что было верно в Q1?" — точные факты во времени | Сложнее моделировать |

**Для нашего кейса**: **гибрид** — Letta-style tiered memory для conversation, Graphiti-style temporal graph для strategy facts ("Sharpe стратегии X был 3.2 в июне, упал до 1.1 в июле").

### 2. Frontend/interface — где живёт чат

| Вариант | Плюсы | Минусы |
|---------|-------|--------|
| **Slack MCP client** | Zero-config для team, все уже там | Vendor lock, ограниченный UX |
| **Custom web (Next.js)** | Полный контроль, красивые графики | Нужно строить auth/RBAC |
| **CLI + Textual TUI** | Мощный для power users | Не подходит нетехническим |
| **Telegram bot** | Ты уже там живёшь | Публичные графики сложнее |

**Рекомендация**: **Web (главный) + Slack (для команды) + CLI (для тебя)** — три канала в один и тот же agent runtime через MCP.

### 3. Multi-user coordination

Три уровня:

**A. Shared workspace, individual conversations** (простой)
- Каждый юзер — свой thread
- Общая память + артефакты
- Как Notion: разные документы, но одна база

**B. Shared conversations** (мультиплеер)
- Несколько людей в одном треде с агентом
- Slack Claude Tag модель — @agent видит контекст канала
- Хорошо для brainstorm сессий

**C. Agents-as-teammates** (крутой)
- @explorer генерирует гипотезы  
- @critic ревьюит
- @analyst делает summary
- Каждый агент — отдельный "участник" канала

**Рекомендация**: **все три**, но начать с A → B → C.

---

## Слои платформы

```
┌─────────────────────────────────────────────────────┐
│  INTERFACES                                          │
│  Web chat  │  Slack  │  Telegram  │  CLI  │  API    │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  GATEWAY (auth, rate-limit, session routing)         │
│  - user identity + team scoping                      │
│  - permissions (viewer/researcher/admin)             │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  AGENT ORCHESTRATOR                                  │
│  - conversation manager (thread state)               │
│  - agent router (какой sub-agent обрабатывает)       │
│  - tool dispatcher                                   │
└──┬──────────┬───────────┬───────────┬────────────────┘
   │          │           │           │
   ▼          ▼           ▼           ▼
┌──────┐  ┌──────┐   ┌────────┐  ┌──────────┐
│MEMORY│  │TOOLS │   │  DATA  │  │  TRACES  │
│      │  │      │   │        │  │          │
│L1-L4 │  │Sand- │   │Market  │  │Langfuse  │
│Graph │  │boxes │   │DuckDB  │  │OpenTel   │
│Facts │  │Skills│   │FAISS   │  │Datasets  │
└──────┘  └──────┘   └────────┘  └──────────┘
```

---

## Слой 1: Хранилище (единое, но с scoping)

Ключевой сдвиг от текущего: **всё имеет owner + team + visibility**.

```sql
-- Каждая сущность знает кому принадлежит
CREATE TABLE hypotheses (
    id UUID PRIMARY KEY,
    ...
    created_by  VARCHAR,        -- user_id или agent name
    team_id     VARCHAR,        -- namespace изоляция
    visibility  VARCHAR,        -- private / team / public
    tags        VARCHAR[]       -- для навигации
);

CREATE TABLE users (
    id, email, name, role,      -- viewer/researcher/admin
    slack_id, telegram_id,      -- линковка interfaces
    preferences JSON            -- личные настройки
);

CREATE TABLE teams (
    id, name, budget_daily_usd,
    settings JSON
);

CREATE TABLE conversations (
    id, team_id, title,
    participants VARCHAR[],     -- user_ids
    agents VARCHAR[],           -- какие агенты подключены
    created_at, updated_at
);

CREATE TABLE messages (
    id, conversation_id,
    author_type,                -- user / agent / system
    author_id, content, tool_calls JSON,
    trace_id                    -- линк на Langfuse
);
```

**Хранение файлов**: MinIO/S3 с префиксом `s3://aqr/{team}/{user}/{project}/...`

**Memory scoping**:
- L1 events: per-user (личная работа)
- L2 insights: per-team (делятся)  
- L3 heuristics: cross-team validated (проверенное знание)
- L4 laws: global (законы рынка)

Так избегаешь взаимного мусора, но накопленное знание расшаривается.

---

## Слой 2: Tools как экосистема "скиллов"

Как у меня skills — навыки, которые агент грузит по необходимости.

Три типа tools:

**A. Skills (декларативные)** — markdown с инструкциями и вызовами
- `moex-data-fetch` — как правильно тянуть с MOEX
- `sharpe-validation` — метрики бэктеста  
- `regime-classifier` — определить режим рынка
- Хранятся в git, load-on-demand

**B. Code blocks (исполняемые)** — библиотека функций
- Уже сделано: `blocks/registry.py`
- Каждый блок = проверенная функция (сигнал, feature, risk model)

**C. External connectors** — MCP-серверы
- MOEX ISS MCP
- Broker MCP (paper trading)
- Slack/Telegram MCP (для отправки алертов)
- Литература MCP (arXiv, SSRN)

Ключевое: **любой юзер и любой агент** используют одни и те же tools. Разница только в правах.

---

## Слой 3: UI-паттерны которые работают

### Основной чат
```
┌─────────────────────────────────────────┐
│ #research-metals   3 участника  2 agents│
├─────────────────────────────────────────┤
│                                         │
│ Вадим:                                  │
│   @explorer поищи pairs в metals        │
│                                         │
│ Explorer (agent):                       │
│   Запускаю 500 гипотез...               │
│   [trace] [pause] [tune]                │
│                                         │
│ Explorer (10 мин спустя):               │
│   Нашёл 3 с Sharpe>3:                   │
│   [card: GD-GC z-fade Sh=3.4]           │
│   [card: PL-PA momentum Sh=3.1]         │
│                                         │
│ Sergey:                                  │
│   @critic проверь GD-GC на leakage     │
│                                         │
│ Critic (agent):                         │
│   [running validation...]               │
└─────────────────────────────────────────┘
```

Ключевые фичи UI:
- **Rich cards** для стратегий (не текст, а компонент со сжатыми метриками)
- **Inline traces** — клик по действию агента → Langfuse trace
- **Live updates** — если агент работает часами, ты видишь прогресс не reload'ая
- **Threading** — subthread для deep-dive, чтобы не засорять
- **Artifact panel** — sidebar со всеми файлами разговора

### Dashboard
Уже спроектирован (aqr_stream/ui). Добавить:
- **Активные разговоры** (кто сейчас работает)
- **Личная лента** (что делали агенты по моим запросам)  
- **Team feed** (что происходит в команде)

### Command palette
Cmd+K → быстрый доступ к:
- Найти стратегию по имени
- Открыть недавний разговор
- Запустить скилл напрямую
- Спросить агента

---

## Слой 4: Трейсинг и наблюдаемость

Индустрия сошлась на **OpenTelemetry GenAI conventions** как wire-протоколе. Топ выборы:

| Инструмент | Сильная сторона |
|-----------|-----------------|
| **Langfuse** | OSS, self-host, отличный UX для промптов |
| **LangSmith** | Best-in-class datasets & evals (но vendor-lock LangChain) |
| **Arize Phoenix** | OSS, силён в eval и drift |
| **Braintrust** | Datasets + evals + prompt playground |

**Рекомендация**: **Langfuse** (self-hosted, уже есть в v2) + OpenTelemetry spans.

Что трейсить:
- Every message → span `invoke_agent`
- Every LLM call → child span `chat` (input/output/tokens/latency)
- Every tool call → child span `execute_tool`  
- Every backtest → span с датасетом+метриками

**Ключевая метрика 2026**: `TrajectoryEfficiency` — насколько короткий путь агент прошёл. Полезно для aqr — сколько LLM calls он тратит на одну валидированную стратегию.

---

## Слой 5: Multi-user coordination — конкретные паттерны

### A. Presence + real-time
- Показывать кто онлайн в разговоре
- "Sergey набирает..."
- Кто ещё смотрит эту стратегию

### B. Мутации без конфликтов
Если два человека одновременно правят гипотезу:
- **Optimistic UI** + backend rejects конфликтующие  
- Или **CRDT** (сложнее, но правильнее для realtime edit)

### C. Handoff между людьми
```
Вадим: @sergey смотри что нашёл explorer, тебе близко к твоей теме
Sergey: [receives notification with context]
```

### D. Agent-to-agent handoff в одном разговоре
```
Explorer нашёл кандидата → передаёт Critic → передаёт Backtester → передаёт Portfolio Constructor
```
Реализуется через `handoff_to_agent(target, context)` tool.

### E. Budget management
- Каждый team имеет daily budget
- Каждый user внутри team — свой sub-budget
- Агенты знают лимиты и pause до утра при исчерпании

---

## Стек — конкретно

```yaml
Backend:
  runtime: Python 3.12
  agent_framework: LangGraph          # уже в aqr_v2
  memory: 
    conversation: Letta OSS           # или свой поверх DuckDB
    facts: Zep / Graphiti             # temporal knowledge
  llm_gateway: LiteLLM                # унифицированный API
  db:
    metadata: Postgres                # users/teams/conversations
    analytics: DuckDB                 # hypotheses/backtests
    vector: FAISS or Qdrant
    graph: Neo4j (для Graphiti) или Kuzu
  queue: Redis Streams                # уже есть
  storage: MinIO/S3
  auth: Clerk / WorkOS / Ory Kratos
  
Frontend:
  framework: Next.js 15 (App Router)
  ui: Tremor + shadcn/ui              # уже начали
  realtime: 
    - SSE для agent output stream
    - WebSocket для presence + typing
    - Yjs (если хотите collaborative editing)
  auth: NextAuth или Clerk client
  
Observability:
  traces: Langfuse (self-host)
  metrics: OpenTelemetry → Prometheus
  logs: structured JSON → Loki
  alerts: Grafana

Deployment:
  orchestration: Docker Compose (dev) → Kubernetes (prod)
  ci: GitHub Actions
  secrets: SOPS or Doppler
```

---

## Три пути реализации

### Путь 1 — MVP на Slack (быстро, 2 недели)
```
Slack workspace + Slackbot MCP + наш agent backend
```
Плюсы:
- Все уже в Slack
- Notifications, threads, users бесплатно
- Multi-user из коробки

Минусы:
- Слабый UI для графиков (только карточки)
- Vendor lock

Кейс: если 2-5 человек и MVP.

### Путь 2 — Custom web platform (3-6 месяцев)
Next.js + agent backend + Langfuse + всё что описал выше.

Плюсы: полный контроль, красивые графики стратегий, брендинг.

Минусы: строить долго, много компонентов.

Кейс: если 10-50 человек, "продукт".

### Путь 3 — Гибрид (мой совет)
1. **Web chat + dashboard** — основной интерфейс (то что уже начали)
2. **Slack bridge** — оповещения и quick queries из Slack ("@aqr статус explorer'а")
3. **Telegram bridge** — для тебя лично
4. **CLI** — для скриптовых сценариев и cron

Один общий agent backend, четыре канала входа.

---

## Что делать прямо сейчас — по недельно

### Неделя 1: Foundation
- Postgres схема: users/teams/conversations/messages
- Auth: Clerk (быстрее) или NextAuth
- Extend workspace/aqr.duckdb: добавить owner/team/visibility во все таблицы

### Неделя 2: Chat backend
- LangGraph orchestrator слушает conversations table
- Streaming ответов через SSE
- Tool calls логируются в trace_id

### Неделя 3: Web chat UI
- Next.js /chat/[conversationId] с SSE
- Rich cards для гипотез/стратегий
- Artifact sidebar

### Неделя 4: Slack bridge
- Slack app + `@aqr` mention
- MCP client паттерн: всё что видит канал → agent context
- Ответы обратно в thread

### Неделя 5: Multi-agent handoffs
- @explorer / @critic / @coder / @analyst как pseudo-users в чате
- `handoff_to_agent` tool
- Presence indicators

### Неделя 6: Observability
- Langfuse self-host в docker-compose
- OpenTelemetry инструментация всех LLM+tool вызовов
- Dashboard "cost per validated strategy" по каждому юзеру/команде

### Неделя 7-8: Memory upgrade
- Letta OSS для conversation memory
- Graphiti для strategy facts (temporal)
- Migration L1-L4 в новую систему

---

## Открытые вопросы к вам

1. **Масштаб**: сколько людей будет работать? (2-5? 20+? open community?)  
   От этого зависит нужно ли RBAC, biling, ratelimiting уже сейчас.

2. **Slack vs Web как primary**?  
   Если у команды уже Slack — быстрая победа. Если ты хочешь "продукт" — Web.

3. **Хостинг**: self-host на своих серверах или SaaS-компоненты (Clerk auth, Langfuse Cloud)?

4. **Летта / Мем0 / свой memory**?  
   Свой = гибкость, но месяц работы. Летта = быстро, но dependency.
