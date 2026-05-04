"use client";
import { useSession } from "@/lib/session-context";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export function AgentTrace() {
  const { events } = useSession();

  const grouped = events.reduce<Array<{ kind: "thinking"; ts: string; text: string } | { kind: "event"; ts: string; evt: (typeof events)[number] }>>((acc, e) => {
    if (e.type === "agent.thinking") {
      const last = acc[acc.length - 1];
      const delta = (e as any).data.delta ?? "";
      if (last && last.kind === "thinking") {
        last.text += delta;
      } else {
        acc.push({ kind: "thinking", ts: e.ts, text: delta });
      }
    } else {
      acc.push({ kind: "event", ts: e.ts, evt: e });
    }
    return acc;
  }, []);

  return (
    <Card className="h-full">
      <CardHeader><CardTitle>Agent trace</CardTitle></CardHeader>
      <CardContent className="space-y-3 text-sm overflow-auto max-h-[80vh]">
        {grouped.map((g, i) => (
          <div key={i} className="border-l-2 pl-2 border-muted">
            <Badge variant="outline" className="mr-2">
              {g.kind === "thinking" ? "thinking" : g.evt.type.replace("agent.", "")}
            </Badge>
            <span className="text-muted-foreground text-xs">{new Date(g.ts).toLocaleTimeString()}</span>
            <pre className="text-xs whitespace-pre-wrap mt-1">
              {g.kind === "thinking" ? g.text :
               g.evt.type === "agent.status" ? (g.evt as any).data.message :
               JSON.stringify((g.evt as any).data, null, 2).slice(0, 600)}
            </pre>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
