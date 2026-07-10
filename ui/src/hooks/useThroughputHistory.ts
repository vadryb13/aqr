import { useEffect, useRef, useState } from "react";
import type { OverallStats } from "../lib/api";

export interface ThroughputPoint {
  time: string;
  generated: number;
  tested: number;
  duplicates: number;
  cost: number;
}

/**
 * Хранит rolling history для графиков — берёт снапшоты каждые 5 сек.
 */
export function useThroughputHistory(stats: OverallStats | undefined, maxPoints = 60) {
  const [history, setHistory] = useState<ThroughputPoint[]>([]);
  const prevRef = useRef<{ generated: number; tested: number; duplicates: number } | null>(null);

  useEffect(() => {
    if (!stats) return;
    const now = new Date();
    const time = now.toLocaleTimeString("ru-RU", { hour12: false });
    const cur = { generated: stats.total, tested: stats.tested, duplicates: stats.duplicates };
    // Разница между снапшотами = throughput за интервал
    const delta = prevRef.current
      ? {
          generated: Math.max(0, cur.generated - prevRef.current.generated),
          tested: Math.max(0, cur.tested - prevRef.current.tested),
          duplicates: Math.max(0, cur.duplicates - prevRef.current.duplicates),
        }
      : { generated: 0, tested: 0, duplicates: 0 };
    prevRef.current = cur;
    setHistory((h) => [
      ...h.slice(-(maxPoints - 1)),
      { time, ...delta, cost: stats.cost_today_usd },
    ]);
  }, [stats, maxPoints]);

  return history;
}
