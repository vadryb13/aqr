import {
  Card, Title, Table, TableHead, TableRow, TableHeaderCell,
  TableBody, TableCell, Badge, Flex, Text,
} from "@tremor/react";
import type { TopHypothesis } from "../lib/api";

interface Props {
  rows: TopHypothesis[] | undefined;
}

export function TopHypothesesTable({ rows }: Props) {
  return (
    <Card>
      <Flex>
        <Title className="text-white">Топ гипотезы (p{"<"}0.05, n{">"}200)</Title>
        <Badge color="amber">{rows?.length ?? 0}</Badge>
      </Flex>
      <div className="mt-4 max-h-[540px] overflow-y-auto">
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Гипотеза</TableHeaderCell>
              <TableHeaderCell>Категория</TableHeaderCell>
              <TableHeaderCell className="text-right">Sharpe</TableHeaderCell>
              <TableHeaderCell className="text-right">p-val</TableHeaderCell>
              <TableHeaderCell>Режим</TableHeaderCell>
              <TableHeaderCell className="text-right">Max DD</TableHeaderCell>
              <TableHeaderCell className="text-right">n</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(rows ?? []).map((r) => (
              <TableRow key={r.id}>
                <TableCell className="max-w-md">
                  <Text className="text-sm text-gray-200 truncate" title={r.hypothesis}>
                    {r.hypothesis}
                  </Text>
                  <Text className="text-xs text-gray-500 font-mono">
                    {r.block_name}
                  </Text>
                </TableCell>
                <TableCell>
                  <Badge color="blue" size="xs">{r.category}</Badge>
                </TableCell>
                <TableCell className="text-right font-mono text-amber-400 font-semibold">
                  {r.sharpe.toFixed(2)}
                </TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {r.pvalue < 0.0001 ? "<0.0001" : r.pvalue.toFixed(4)}
                </TableCell>
                <TableCell>
                  {r.best_regime ? (
                    <Badge color="violet" size="xs">{r.best_regime}</Badge>
                  ) : (
                    <Text className="text-xs text-gray-500">—</Text>
                  )}
                </TableCell>
                <TableCell className="text-right font-mono text-rose-400">
                  {(r.max_dd * 100).toFixed(1)}%
                </TableCell>
                <TableCell className="text-right font-mono text-xs">{r.n}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </Card>
  );
}
