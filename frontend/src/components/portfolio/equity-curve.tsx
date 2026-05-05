"use client";
import { useCallback, useEffect, useState } from "react";
import { LineChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine } from "recharts";
import type { EquityCurve as EC, Period } from "@/types/portfolio";
import { getEquityCurve } from "@/lib/api";
import { usePortfolioInvalidate } from "@/lib/portfolio-events";
import { fmtUsd, fmtPct } from "@/lib/utils";

const PERIODS: Period[] = ["1D", "1W", "1M", "3M", "ALL"];

export function EquityCurve() {
  const [period, setPeriod] = useState<Period>("1D");
  const [data, setData] = useState<EC | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getEquityCurve(period)
      .then(d => {
        if (!cancelled) setData(d);
      })
      .catch(e => {
        if (!cancelled) setError(String(e?.message ?? e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [period]);

  const refetch = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getEquityCurve(period)
      .then(d => { if (!cancelled) { setData(d); setLoading(false); } })
      .catch((e: Error) => { if (!cancelled) { setError(e.message); setLoading(false); } });
    return () => { cancelled = true; };
  }, [period]);
  usePortfolioInvalidate(refetch);

  const plColor = (data?.profit_loss ?? 0) >= 0 ? "var(--up)" : "var(--down)";

  return (
    <section className="p-5 border border-[color:var(--hairline)] h-full">
      <div className="flex items-baseline justify-between mb-4">
        <h2 className="smallcaps panel-rule">Equity Curve</h2>
        <div className="flex gap-1 font-mono text-[11px]">
          {PERIODS.map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={
                "px-2 py-0.5 border " +
                (p === period
                  ? "border-[color:var(--fg)] text-[color:var(--fg)]"
                  : "border-[color:var(--hairline)] text-[color:var(--fg-mute)] hover:text-[color:var(--fg-dim)]")
              }
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {error ? (
        <div className="text-[12px] text-[color:var(--down)]">Couldn’t load equity curve — {error}</div>
      ) : loading || !data ? (
        <div className="text-[12px] text-[color:var(--fg-mute)] font-mono">loading…</div>
      ) : data.points.length === 0 ? (
        <div className="text-[12px] text-[color:var(--fg-mute)] font-mono">No data for {period}.</div>
      ) : (
        <>
          <div className="flex items-baseline gap-3 mb-3 font-mono">
            <span className="num text-[20px]" style={{ color: plColor }}>
              {fmtUsd(data.profit_loss, { sign: true })}
            </span>
            <span className="text-[12px]" style={{ color: plColor }}>
              {fmtPct(data.profit_loss_pct, { sign: true })}
            </span>
            <span className="text-[11px] text-[color:var(--fg-mute)] ml-auto">
              base {fmtUsd(data.base_value)}
            </span>
          </div>
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.points} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <XAxis
                  dataKey="t"
                  hide
                />
                <YAxis
                  domain={["auto", "auto"]}
                  hide
                />
                <ReferenceLine y={data.base_value} stroke="var(--hairline-2)" strokeDasharray="2 3" />
                <Tooltip
                  contentStyle={{ background: "var(--ink-2)", border: "1px solid var(--hairline-2)", fontFamily: "var(--font-mono, monospace)", fontSize: 11 }}
                  labelFormatter={(l) => new Date(String(l)).toLocaleString()}
                  formatter={(v) => [fmtUsd(Number(v)), "equity"]}
                />
                <Line
                  type="monotone"
                  dataKey="equity"
                  stroke={plColor}
                  strokeWidth={1.25}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </section>
  );
}
