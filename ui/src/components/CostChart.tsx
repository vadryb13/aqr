import { Card, Title, LineChart } from "@tremor/react";
import type { ThroughputPoint } from "../hooks/useThroughputHistory";

interface Props {
  data: ThroughputPoint[];
  budget: number;
}

export function CostChart({ data, budget }: Props) {
  return (
    <Card>
      <Title className="text-white">
        Cost today (${budget} лимит)
      </Title>
      <LineChart
        className="h-64 mt-4"
        data={data}
        index="time"
        categories={["cost"]}
        colors={["cyan"]}
        valueFormatter={(v) => `$${v.toFixed(2)}`}
        showLegend={false}
        showGridLines={false}
        curveType="monotone"
        yAxisWidth={50}
      />
    </Card>
  );
}
