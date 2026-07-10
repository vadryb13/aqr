import {
  Card, Title, Table, TableHead, TableRow, TableHeaderCell,
  TableBody, TableCell, Badge, Button, Flex,
} from "@tremor/react";
import { PauseIcon, PlayIcon } from "@heroicons/react/24/outline";
import { useState } from "react";
import type { GeneratorStats } from "../lib/api";
import { pauseGenerator, resumeGenerator } from "../lib/api";

const generatorColor: Record<string, "blue" | "emerald" | "amber" | "rose" | "violet"> = {
  explorer: "blue",
  exploiter: "emerald",
  mutator: "amber",
  adversary: "rose",
  regime: "violet",
};

interface Props {
  generators: GeneratorStats[];
}

export function GeneratorTable({ generators }: Props) {
  const [paused, setPaused] = useState<Set<string>>(new Set());

  const toggle = async (id: string) => {
    if (paused.has(id)) {
      await resumeGenerator(id);
      const next = new Set(paused); next.delete(id); setPaused(next);
    } else {
      await pauseGenerator(id);
      setPaused(new Set(paused).add(id));
    }
  };

  return (
    <Card>
      <Flex>
        <Title className="text-white">Generators Performance</Title>
        <Badge color="blue">{generators.length} активных</Badge>
      </Flex>
      <Table className="mt-4">
        <TableHead>
          <TableRow>
            <TableHeaderCell>Тип</TableHeaderCell>
            <TableHeaderCell className="text-right">Сгенер.</TableHeaderCell>
            <TableHeaderCell className="text-right">Bt</TableHeaderCell>
            <TableHeaderCell className="text-right">Dup</TableHeaderCell>
            <TableHeaderCell className="text-right">avg Sh</TableHeaderCell>
            <TableHeaderCell className="text-right">max Sh</TableHeaderCell>
            <TableHeaderCell className="text-right">Sh {">"} 3</TableHeaderCell>
            <TableHeaderCell className="text-right">Sh {">"} 5</TableHeaderCell>
            <TableHeaderCell className="text-right">$</TableHeaderCell>
            <TableHeaderCell className="text-right">$/hit</TableHeaderCell>
            <TableHeaderCell></TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {generators.map((g) => {
            const costPerHit =
              g.n_sharpe_gt_3 > 0 && g.total_cost
                ? (g.total_cost / g.n_sharpe_gt_3).toFixed(3)
                : "—";
            const isPaused = paused.has(g.type);
            return (
              <TableRow key={g.type}>
                <TableCell>
                  <Badge color={generatorColor[g.type] ?? "blue"}>{g.type}</Badge>
                </TableCell>
                <TableCell className="text-right font-mono">
                  {g.n_generated.toLocaleString("ru-RU")}
                </TableCell>
                <TableCell className="text-right font-mono">
                  {g.n_tested.toLocaleString("ru-RU")}
                </TableCell>
                <TableCell className="text-right font-mono text-gray-500">
                  {g.n_duplicate}
                </TableCell>
                <TableCell className="text-right font-mono">
                  {g.avg_sharpe?.toFixed(2) ?? "—"}
                </TableCell>
                <TableCell className="text-right font-mono text-amber-400">
                  {g.max_sharpe?.toFixed(2) ?? "—"}
                </TableCell>
                <TableCell className="text-right font-mono">{g.n_sharpe_gt_3}</TableCell>
                <TableCell className="text-right font-mono text-emerald-400">
                  {g.n_sharpe_gt_5}
                </TableCell>
                <TableCell className="text-right font-mono">
                  ${g.total_cost?.toFixed(2) ?? "0.00"}
                </TableCell>
                <TableCell className="text-right font-mono text-cyan-400">
                  {costPerHit === "—" ? "—" : `$${costPerHit}`}
                </TableCell>
                <TableCell>
                  <Button
                    variant="secondary"
                    size="xs"
                    icon={isPaused ? PlayIcon : PauseIcon}
                    color={isPaused ? "emerald" : "amber"}
                    onClick={() => toggle(g.type)}
                  >
                    {isPaused ? "Resume" : "Pause"}
                  </Button>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Card>
  );
}
