"use client";
import { useSession } from "@/lib/session-context";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export function OptionsChainTable() {
  const { events } = useSession();
  const ev = [...events].reverse().find(e => e.type === "agent.tool_result" && (e as any).data.name === "get_options_chain");
  if (!ev) return null;
  const chain = (ev as any).data.output;
  const rows = (chain.contracts ?? []).slice(0, 20);
  return (
    <Card>
      <CardHeader><CardTitle>Options chain — {chain.underlying} {chain.expiry}</CardTitle></CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow>
            <TableHead>Symbol</TableHead><TableHead>Side</TableHead><TableHead>Bid</TableHead><TableHead>Ask</TableHead><TableHead>Δ</TableHead><TableHead>IV</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.map((c: any) => (
              <TableRow key={c.symbol}>
                <TableCell className="font-mono text-xs">{c.symbol}</TableCell>
                <TableCell>{c.side}</TableCell>
                <TableCell>{c.bid}</TableCell><TableCell>{c.ask}</TableCell>
                <TableCell>{c.delta?.toFixed?.(2)}</TableCell><TableCell>{(c.iv*100)?.toFixed?.(1)}%</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
