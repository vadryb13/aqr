import { Card, Title, Badge, Text, Flex } from "@tremor/react";
import { useSSE } from "../hooks/useSSE";
import type { LiveHypothesis } from "../lib/api";
import { useMemo } from "react";

const generatorColor: Record<string, "blue" | "emerald" | "amber" | "rose" | "violet"> = {
  explorer: "blue",
  exploiter: "emerald",
  mutator: "amber",
  adversary: "rose",
  regime: "violet",
};

export function LiveFeed() {
  const { events, connected, lastEventAt } = useSSE<LiveHypothesis>(
    "/api/stream/top",
    50
  );

  const staleness = useMemo(() => {
    if (!lastEventAt) return "нет данных";
    const sec = Math.round((Date.now() - lastEventAt) / 1000);
    if (sec < 60) return `${sec}с назад`;
    return `${Math.round(sec / 60)}м назад`;
  }, [lastEventAt]);

  return (
    <Card className="h-[520px] flex flex-col">
      <Flex className="mb-3">
        <Title className="text-white">🔥 Live Feed — Sharpe {">"} 5</Title>
        <div className="flex items-center gap-2">
          <div
            className={`w-2 h-2 rounded-full ${
              connected ? "bg-emerald-400 pulse-dot" : "bg-rose-500"
            }`}
          />
          <Text className="text-xs">
            {connected ? "connected" : "reconnecting..."} · last: {staleness}
          </Text>
        </div>
      </Flex>

      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {events.length === 0 && (
          <div className="text-center text-gray-500 py-16">
            Ждём находок… (Sharpe {">"} 5 появляются сюда моментально)
          </div>
        )}
        {events.map((e, i) => {
          const gen = e.generator_type || "unknown";
          const color = generatorColor[gen] ?? "blue";
          return (
            <div
              key={`${e.id}-${i}`}
              className={`rounded-lg border border-gray-800 p-3 bg-gray-900/50 ${
                i === 0 ? "flash-in" : ""
              }`}
            >
              <Flex className="mb-1">
                <div className="flex items-center gap-2">
                  <Badge color={color} size="xs">
                    {gen}
                  </Badge>
                  <Text className="text-xs text-gray-500">{e.category ?? "—"}</Text>
                </div>
                <div className="flex items-center gap-2">
                  {e.sharpe !== undefined && (
                    <Badge color="amber" size="sm">
                      Sh {e.sharpe.toFixed(2)}
                    </Badge>
                  )}
                  {e.best_regime && (
                    <Badge color="violet" size="xs">
                      {e.best_regime}
                    </Badge>
                  )}
                </div>
              </Flex>
              <Text className="text-sm text-gray-200 line-clamp-2">
                {e.hypothesis}
              </Text>
              {e.block_name && (
                <Text className="text-xs text-gray-500 mt-1 font-mono">
                  {e.block_name}
                </Text>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
