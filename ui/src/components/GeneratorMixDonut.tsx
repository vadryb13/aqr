import { Card, Title, DonutChart, Legend } from "@tremor/react";
import type { GeneratorStats } from "../lib/api";

interface Props { generators: GeneratorStats[] }

export function GeneratorMixDonut({ generators }: Props) {
  const data = generators.map((g) => ({
    name: g.type,
    value: g.n_generated,
  }));

  return (
    <Card>
      <Title className="text-white">Микс генерации</Title>
      <DonutChart
        className="h-48 mt-4"
        data={data}
        category="value"
        index="name"
        colors={["blue", "emerald", "amber", "rose", "violet"]}
        valueFormatter={(v) => v.toLocaleString("ru-RU")}
      />
      <Legend
        className="mt-3 justify-center"
        categories={data.map((d) => d.name)}
        colors={["blue", "emerald", "amber", "rose", "violet"]}
      />
    </Card>
  );
}
