import useSWR from "swr";
import { fetcher, type OverallStats, type TopHypothesis, type Insight } from "./lib/api";
import { KpiCards } from "./components/KpiCards";
import { LiveFeed } from "./components/LiveFeed";
import { ThroughputChart } from "./components/ThroughputChart";
import { CostChart } from "./components/CostChart";
import { GeneratorTable } from "./components/GeneratorTable";
import { TopHypothesesTable } from "./components/TopHypothesesTable";
import { InsightsPanel } from "./components/InsightsPanel";
import { GeneratorMixDonut } from "./components/GeneratorMixDonut";
import { Header } from "./components/Header";
import { useThroughputHistory } from "./hooks/useThroughputHistory";
import { useMemo } from "react";

const DAILY_BUDGET = 50;   // из .env, MVP hardcode

export default function App() {
  // Polling 5s
  const { data: stats, error: statsErr } = useSWR<OverallStats>(
    "/api/stats", fetcher, { refreshInterval: 5000 }
  );
  const { data: top } = useSWR<TopHypothesis[]>(
    "/api/top?limit=25", fetcher, { refreshInterval: 15000 }
  );
  const { data: insights } = useSWR<Insight[]>(
    "/api/insights", fetcher, { refreshInterval: 30000 }
  );

  const history = useThroughputHistory(stats);

  const ratePerMin = useMemo(() => {
    if (history.length < 2) return 0;
    const recent = history.slice(-12);   // ≈ последняя минута (5с × 12)
    const total = recent.reduce((a, p) => a + p.generated, 0);
    return total;
  }, [history]);

  const lastUpdate = new Date().toLocaleTimeString("ru-RU");
  const online = !statsErr && !!stats;

  return (
    <div className="min-h-screen">
      <Header online={online} lastUpdate={lastUpdate} />

      <main className="max-w-[1600px] mx-auto p-6 space-y-6">
        {statsErr && (
          <div className="rounded-lg border border-rose-800 bg-rose-950/40 p-4">
            <p className="text-rose-300 text-sm">
              ⚠ API недоступен ({String(statsErr)}). Убедись что бэкенд запущен:{" "}
              <code className="text-rose-200">aqr-stream start</code>
            </p>
          </div>
        )}

        {/* KPI row */}
        <KpiCards stats={stats} budget={DAILY_BUDGET} ratePerMin={ratePerMin} />

        {/* Charts + Live feed */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          <div className="xl:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-4">
            <ThroughputChart data={history} />
            <CostChart data={history} budget={DAILY_BUDGET} />
            <div className="md:col-span-2">
              <GeneratorTable generators={stats?.generators ?? []} />
            </div>
          </div>
          <LiveFeed />
        </div>

        {/* Bottom: mix donut + insights + top table */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          <GeneratorMixDonut generators={stats?.generators ?? []} />
          <InsightsPanel insights={insights} />
          <TopHypothesesTable rows={top} />
        </div>

        <footer className="text-center text-gray-600 text-xs py-4">
          AQR Stream · {stats?.total?.toLocaleString("ru-RU") ?? 0} гипотез в базе ·
          обновление каждые 5 сек · SSE live feed
        </footer>
      </main>
    </div>
  );
}
