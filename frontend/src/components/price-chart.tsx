"use client";
import { useEffect, useState, useMemo } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, CartesianGrid } from "recharts";
import { useSession } from "@/lib/session-context";

type Bar = { t: string; c: number };

export function PriceChart() {
  const { events } = useSession();
  const [bars, setBars] = useState<Bar[]>([]);

  const ticker =
    (events.find(
      e => e.type === "agent.tool_call" && (e as { data: { name: string } }).data.name === "get_quote"
    ) as { data: { input: { symbol: string } } } | undefined)?.data.input.symbol;

  useEffect(() => {
    if (!ticker) return;
    fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/bars/${ticker}`)
      .then(r => r.json())
      .then((d: Bar[]) => setBars(d));
  }, [ticker]);

  const stats = useMemo(() => {
    if (bars.length < 2) return null;
    const last = bars[bars.length - 1].c;
    const first = bars[0].c;
    const change = last - first;
    const pct = (change / first) * 100;
    const min = Math.min(...bars.map(b => b.c));
    const max = Math.max(...bars.map(b => b.c));
    return { last, change, pct, min, max };
  }, [bars]);

  if (!ticker) return null;

  const up = (stats?.change ?? 0) >= 0;
  const stroke = up ? "var(--up)" : "var(--down)";

  return (
    <section className="border border-[color:var(--hairline-2)] bg-[color:var(--ink-2)]">
      <header className="flex items-center gap-5 px-4 py-3.5 border-b border-[color:var(--hairline)]">
        <div className="smallcaps">Price · 30D</div>
        <div className="num text-[28px] leading-none tracking-tight">
          {stats?.last?.toFixed(2) ?? "—"}
        </div>
        {stats && (
          <div
            className="num text-[13px]"
            style={{ color: up ? "var(--up)" : "var(--down)" }}
          >
            {up ? "▲" : "▼"} {stats.change.toFixed(2)} · {up ? "+" : ""}
            {stats.pct.toFixed(2)}%
          </div>
        )}
        <div className="ml-auto font-mono text-[11px] flex items-center text-[color:var(--fg-mute)]">
          {(["1D", "5D", "1M", "3M", "1Y"] as const).map((r) => (
            <span
              key={r}
              className={
                "px-2.5 py-[5px] " +
                (r === "1M"
                  ? "text-[color:var(--fg)] bg-[color:var(--ink-3)]"
                  : "")
              }
            >
              {r}
            </span>
          ))}
        </div>
      </header>

      <div style={{ height: 240 }}>
        <ResponsiveContainer>
          <LineChart data={bars} margin={{ top: 16, right: 16, left: 8, bottom: 8 }}>
            <defs>
              <linearGradient id="lineGrad" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0" stopColor={stroke} stopOpacity={0.35} />
                <stop offset="1" stopColor={stroke} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="oklch(1 0 0 / 0.04)" vertical={false} />
            <XAxis
              dataKey="t"
              hide
            />
            <YAxis
              domain={["auto", "auto"]}
              tick={{ fill: "var(--fg-mute)", fontSize: 10, fontFamily: "var(--font-jb)" }}
              axisLine={false}
              tickLine={false}
              width={48}
              tickFormatter={(v: number) => v.toFixed(0)}
            />
            <Tooltip
              cursor={{ stroke: "var(--signal)", strokeDasharray: "2 4", strokeWidth: 0.6 }}
              contentStyle={{
                background: "var(--ink-3)",
                border: "1px solid var(--hairline-2)",
                borderRadius: 0,
                fontFamily: "var(--font-jb)",
                fontSize: 11,
                color: "var(--fg)",
              }}
              labelStyle={{ color: "var(--fg-mute)", fontSize: 10, letterSpacing: ".1em" }}
              formatter={(value) => [Number(value).toFixed(2), "close"]}
            />
            {stats && (
              <ReferenceLine
                y={stats.last}
                stroke="var(--signal)"
                strokeDasharray="2 4"
                strokeWidth={0.6}
              />
            )}
            <Line
              type="monotone"
              dataKey="c"
              stroke={stroke}
              strokeWidth={1.4}
              dot={false}
              activeDot={{ r: 3, stroke: "var(--ink)", strokeWidth: 2, fill: stroke }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {stats && (
        <footer className="flex gap-6 px-4 py-2.5 border-t border-[color:var(--hairline)] text-[11px] text-[color:var(--fg-mute)]">
          <span>HIGH <span className="num text-[color:var(--fg)] ml-2">{stats.max.toFixed(2)}</span></span>
          <span>LOW <span className="num text-[color:var(--fg)] ml-2">{stats.min.toFixed(2)}</span></span>
          <span>RANGE <span className="num text-[color:var(--fg)] ml-2">{(stats.max - stats.min).toFixed(2)}</span></span>
          <span className="ml-auto">{ticker} · {bars.length} bars</span>
        </footer>
      )}
    </section>
  );
}
