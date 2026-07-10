import { Card, Metric, Text, Flex, ProgressBar, Badge } from "@tremor/react";
import type { OverallStats } from "../lib/api";
import { BoltIcon, CurrencyDollarIcon, FireIcon, CircleStackIcon } from "@heroicons/react/24/outline";

interface Props {
  stats: OverallStats | undefined;
  budget: number;
  ratePerMin: number;
}

export function KpiCards({ stats, budget, ratePerMin }: Props) {
  const s = stats ?? {
    total: 0, pending: 0, tested: 0, duplicates: 0,
    sharpe_gt_3: 0, sharpe_gt_5: 0, cost_today_usd: 0, generators: [],
  };
  const budgetPct = Math.min(100, (s.cost_today_usd / budget) * 100);
  const dupRate = s.total > 0 ? (s.duplicates / s.total) * 100 : 0;
  const hitRate = s.tested > 0 ? (s.sharpe_gt_3 / s.tested) * 100 : 0;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <Card decoration="top" decorationColor="blue">
        <Flex justifyContent="between" alignItems="start">
          <div>
            <Text>Гипотезы всего</Text>
            <Metric className="text-white">{s.total.toLocaleString("ru-RU")}</Metric>
            <Text className="text-xs mt-1">
              ~{ratePerMin.toFixed(0)} / мин
            </Text>
          </div>
          <CircleStackIcon className="h-8 w-8 text-blue-400" />
        </Flex>
      </Card>

      <Card decoration="top" decorationColor="emerald">
        <Flex justifyContent="between" alignItems="start">
          <div>
            <Text>Backtested</Text>
            <Metric className="text-white">{s.tested.toLocaleString("ru-RU")}</Metric>
            <Text className="text-xs mt-1">
              в очереди: {s.pending}
            </Text>
          </div>
          <BoltIcon className="h-8 w-8 text-emerald-400" />
        </Flex>
      </Card>

      <Card decoration="top" decorationColor="amber">
        <Flex justifyContent="between" alignItems="start">
          <div>
            <Text>Sharpe {">"} 3 / {">"} 5</Text>
            <Metric className="text-white">
              {s.sharpe_gt_3}
              <span className="text-amber-400 text-xl"> / {s.sharpe_gt_5}</span>
            </Metric>
            <Text className="text-xs mt-1">hit-rate {hitRate.toFixed(2)}%</Text>
          </div>
          <FireIcon className="h-8 w-8 text-amber-400" />
        </Flex>
      </Card>

      <Card decoration="top" decorationColor={budgetPct > 80 ? "rose" : "cyan"}>
        <Flex justifyContent="between" alignItems="start" className="mb-2">
          <div>
            <Text>Расход сегодня</Text>
            <Metric className="text-white">${s.cost_today_usd.toFixed(2)}</Metric>
          </div>
          <CurrencyDollarIcon className="h-8 w-8 text-cyan-400" />
        </Flex>
        <ProgressBar value={budgetPct} color={budgetPct > 80 ? "rose" : "cyan"} className="mt-2" />
        <Flex className="mt-1">
          <Text className="text-xs">${budget} лимит</Text>
          <Badge color={budgetPct > 80 ? "rose" : "cyan"} size="xs">
            {budgetPct.toFixed(0)}%
          </Badge>
        </Flex>
      </Card>

      <Card className="md:col-span-2 lg:col-span-4">
        <Flex>
          <div>
            <Text>Semantic dedup rate</Text>
            <Metric className="text-white">{dupRate.toFixed(1)}%</Metric>
          </div>
          <div className="flex-1 mx-6">
            <ProgressBar value={dupRate} color="violet" />
          </div>
          <div className="text-right">
            <Text>Дубликатов найдено</Text>
            <Text className="text-2xl text-violet-300 font-semibold">
              {s.duplicates.toLocaleString("ru-RU")}
            </Text>
          </div>
        </Flex>
      </Card>
    </div>
  );
}
