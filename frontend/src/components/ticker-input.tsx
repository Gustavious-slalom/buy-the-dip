"use client";
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { useSession } from "@/lib/session-context";

export function TickerInput() {
  const { sendIdea, sendReplay, status } = useSession();
  const [v, setV] = useState("AAPL");
  return (
    <Card>
      <CardHeader><CardTitle>New analysis</CardTitle></CardHeader>
      <CardContent className="space-y-2">
        <Input value={v} onChange={e => setV(e.target.value.toUpperCase())} placeholder="Ticker (AAPL)" />
        <Button className="w-full" disabled={status === "running"} onClick={() => sendIdea(v)}>
          {status === "running" ? "Thinking…" : "Analyze"}
        </Button>
        <Button variant="outline" className="w-full" disabled={status === "running"} onClick={() => sendReplay()}>
          Replay last
        </Button>
      </CardContent>
    </Card>
  );
}
