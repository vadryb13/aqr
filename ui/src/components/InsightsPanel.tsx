import { Card, Title, Badge, Text, Flex } from "@tremor/react";
import type { Insight } from "../lib/api";
import { LightBulbIcon, ExclamationTriangleIcon, SparklesIcon } from "@heroicons/react/24/outline";

interface Props {
  insights: Insight[] | undefined;
}

const iconFor = (type: string) => {
  if (type === "warning") return ExclamationTriangleIcon;
  if (type === "recommendation") return SparklesIcon;
  return LightBulbIcon;
};

const colorFor = (type: string) => {
  if (type === "warning") return "rose" as const;
  if (type === "recommendation") return "emerald" as const;
  return "amber" as const;
};

export function InsightsPanel({ insights }: Props) {
  const arr = insights ?? [];

  return (
    <Card>
      <Flex className="mb-4">
        <Title className="text-white">Meta-LLM Insights</Title>
        <Badge color="cyan">{arr.length} активных</Badge>
      </Flex>
      {arr.length === 0 && (
        <Text className="text-center text-gray-500 py-8">
          Ждём hourly insight loop (нужно ≥50 результатов за час)
        </Text>
      )}
      <div className="space-y-3">
        {arr.map((ins) => {
          const Icon = iconFor(ins.type);
          const color = colorFor(ins.type);
          return (
            <div
              key={ins.id}
              className="rounded-lg border border-gray-800 p-3 bg-gray-900/50"
            >
              <Flex className="mb-2" alignItems="start">
                <div className="flex items-start gap-2">
                  <Icon className={`h-5 w-5 mt-0.5 text-${color}-400 flex-shrink-0`} />
                  <Text className="text-sm text-gray-100">{ins.text}</Text>
                </div>
                <Badge color={color} size="xs">
                  {(ins.confidence * 100).toFixed(0)}%
                </Badge>
              </Flex>
              <Flex justifyContent="start" className="gap-1 ml-7">
                {ins.applies_to.map((g) => (
                  <Badge key={g} color="blue" size="xs">
                    → {g}
                  </Badge>
                ))}
              </Flex>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
