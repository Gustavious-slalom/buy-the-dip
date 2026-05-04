"use client";
import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { useSession } from "@/lib/session-context";

export function PriceChart() {
  const { events } = useSession();
  const [bars, setBars] = useState<{t:string;c:number}[]>([]);
  const ticker = (events.find(e => e.type === "agent.tool_call" && (e as any).data.name === "get_quote") as any)?.data.input.symbol;
  useEffect(() => {
    if (!ticker) return;
    fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/bars/${ticker}`).then(r => r.json()).then(setBars);
  }, [ticker]);
  if (!ticker) return null;
  return (
    <Card>
      <CardHeader><CardTitle>{ticker} — 30d</CardTitle></CardHeader>
      <CardContent style={{height: 220}}>
        <ResponsiveContainer><LineChart data={bars}>
          <XAxis dataKey="t" hide /><YAxis domain={["auto","auto"]} /><Tooltip />
          <Line type="monotone" dataKey="c" dot={false} />
        </LineChart></ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
