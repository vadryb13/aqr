# AQR Stream — UI Dashboard

React + Vite + Tremor dashboard для live-мониторинга фабрики гипотез.

## Что показывает

- **KPI cards**: гипотез всего, backtested, Sharpe>3/>5, расход, dedup rate
- **Throughput chart**: Δ каждые 5 сек (generated / tested / duplicates)
- **Cost chart**: расход за день с лимитом
- **Live Feed (SSE)**: моментальные находки Sharpe>5 с flash-in анимацией
- **Generators Performance**: таблица со всеми 5 генераторами, кнопки pause/resume
- **Generator Mix**: donut chart по типам
- **Meta-LLM Insights**: активные insights с типом (pattern/warning/recommendation)
- **Топ гипотезы**: таблица с p-value, регимом, max DD

## Запуск

### С реальным backend'ом

```bash
# терминал 1: backend
cd ..
aqr-stream start          # FastAPI на :8080

# терминал 2: frontend
cd ui
npm install
npm run dev               # Vite на :5173, /api → :8080
```

Открой http://localhost:5173

### С mock-данными (без backend'а)

Раскомментируй в `src/App.tsx`:

```ts
import { installMockSSE, mockStats, mockTop, mockInsights } from "./lib/mock-api";
// installMockSSE();  // подменит window.EventSource
```

Или используй `msw` для перехвата fetch — см. TODO в mock-api.ts.

## Стек

- **Vite** — dev server + build
- **React 18** + TypeScript
- **@tremor/react** — dashboards компоненты (dark palette)
- **Tailwind CSS** — стилизация
- **SWR** — data fetching с polling
- **EventSource** — SSE для live feed
- **Heroicons** — иконки

## Структура

```
src/
├── App.tsx                    # главный layout
├── main.tsx                   # entry
├── index.css                  # Tailwind + custom animations
├── lib/
│   ├── api.ts                 # типы + fetcher
│   └── mock-api.ts            # mock для dev без backend
├── hooks/
│   ├── useSSE.ts              # SSE hook с reconnect
│   └── useThroughputHistory.ts # rolling snapshot
└── components/
    ├── Header.tsx
    ├── KpiCards.tsx
    ├── ThroughputChart.tsx
    ├── CostChart.tsx
    ├── LiveFeed.tsx
    ├── GeneratorTable.tsx
    ├── GeneratorMixDonut.tsx
    ├── InsightsPanel.tsx
    └── TopHypothesesTable.tsx
```

## Требования к backend

UI ожидает следующие endpoints на `/api/*` (проксируется Vite → `:8080`):

| Endpoint | Метод | Формат |
|---|---|---|
| `/stats` | GET | `OverallStats` |
| `/top?limit=25` | GET | `TopHypothesis[]` |
| `/insights` | GET | `Insight[]` |
| `/stream/top` | GET SSE | `data: {…LiveHypothesis…}\n\n` |
| `/generators/{type}/pause` | POST | `{ ok: true }` |
| `/generators/{type}/resume` | POST | `{ ok: true }` |

Первые 4 уже реализованы в `aqr/api/server.py`. Pause/resume — TODO (см. patch внизу файла server.py).

## Скриншот layout

```
┌──────────────────────────────────────────────────────────────────┐
│ 🌊 AQR Stream v0.1                    ● API online · 22:37       │
├──────────────────────────────────────────────────────────────────┤
│ [Total 12K] [Backtested 8K] [Sh>3: 341/87] [Cost $12/50 ▓░░]   │
│ [Semantic dedup rate 33.1% ▓▓▓░░░░░░░]                          │
├──────────────────────────────────────────────────────────────────┤
│ ┌─ Throughput ──┐ ┌─ Cost ────────┐  ┌─ 🔥 Live Feed (SSE) ──┐ │
│ │ area chart    │ │ line chart    │  │ [exploiter] Sh 29.1  │ │
│ └───────────────┘ └───────────────┘  │ [mutator] Sh 5.7     │ │
│ ┌─ Generators Performance ─────────┐  │ [explorer] Sh 3.2    │ │
│ │ table + pause/resume buttons     │  │ ...                  │ │
│ └──────────────────────────────────┘  └──────────────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│ ┌─ Mix Donut ──┐ ┌─ Insights ───────┐ ┌─ Top hypotheses ─────┐ │
│ │ 5 generators │ │ pattern/warning/  │ │ table with sharpe   │ │
│ │              │ │ recommendation    │ │ pvalue, dd, regime  │ │
│ └──────────────┘ └───────────────────┘ └─────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```
