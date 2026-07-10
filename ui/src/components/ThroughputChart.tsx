import { Card, Title, AreaChart, Legend } from "@tremor/react";
import type { ThroughputPoint } from "../hooks/useThroughputHistory";

interface Props {
  data: ThroughputPoint[];
}

const rusFmt = (n: number) => n.toLocaleString("ru-RU");

export function ThroughputChart({ data }: Props) {
  return (
    <Card>
      <Title className="text-white">Throughput (Δ каждые 5 сек)</Title>
      <Legend
        className="mt-2"
        categories={["generated", "tested", "duplicates"]}
        colors={["blue", "emerald", "violet"]}
      />
      <AreaChart
        className="h-64 mt-4"
        data={data}
        index="time"
        categories={["generated", "tested", "duplicates"]}
        colors={["blue", "emerald", "violet"]}
        showLegend={false}
        showGridLines={false}
        valueFormatter={rusFmt}
        curveType="monotone"
        yAxisWidth={40}
      />
    </Card>
  );
}
