"use client";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { useSession } from "@/lib/session-context";
import { useMemo } from "react";

export function PortfolioPanel() {
  const { events } = useSession();
  const portfolio = useMemo(() => {
    const ev = [...events].reverse().find(e => e.type === "agent.tool_result" && (e as any).data.name === "get_portfolio");
    return ev ? (ev as any).data.output : null;
  }, [events]);
  if (!portfolio) return null;
  return (
    <Card>
      <CardHeader><CardTitle>Portfolio</CardTitle></CardHeader>
      <CardContent className="text-sm space-y-1">
        <div>Cash: ${portfolio.cash?.toFixed(2)}</div>
        <div>Equity: ${portfolio.equity?.toFixed(2)}</div>
        <div>Buying power: ${portfolio.buying_power?.toFixed(2)}</div>
      </CardContent>
    </Card>
  );
}
