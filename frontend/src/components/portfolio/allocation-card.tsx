"use client";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import type { Allocations } from "@/types/portfolio";
import { fmtPct, fmtUsd } from "@/lib/utils";

type Props = { allocations: Allocations | null; loading: boolean; error: string | null };

const COLORS = {
  stock: "var(--up)",
  option: "var(--signal)",
  cash: "var(--fg-dim)",
};

export function AllocationCard({ allocations, loading, error }: Props) {
  if (error) {
    return (
      <section className="p-5 border border-[color:var(--hairline)]">
        <h2 className="smallcaps panel-rule mb-4">Allocation</h2>
        <div className="text-[12px] text-[color:var(--down)]">{error}</div>
      </section>
    );
  }
  if (loading || !allocations) {
    return (
      <section className="p-5 border border-[color:var(--hairline)]">
        <h2 className="smallcaps panel-rule mb-4">Allocation</h2>
        <div className="text-[12px] text-[color:var(--fg-mute)] font-mono">loading…</div>
      </section>
    );
  }

  const pieData = [
    { name: "stock", value: allocations.by_kind.stock, color: COLORS.stock },
    { name: "option", value: allocations.by_kind.option, color: COLORS.option },
    { name: "cash", value: allocations.by_kind.cash, color: COLORS.cash },
  ].filter(d => d.value > 0);

  const topUnder = allocations.by_underlying.slice(0, 6);
  const maxWeight = Math.max(1, ...topUnder.map(u => u.weight_pct));

  return (
    <section className="p-5 border border-[color:var(--hairline)] h-full">
      <h2 className="smallcaps panel-rule mb-4">Allocation</h2>
      <div className="h-[160px]">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={48} outerRadius={70} paddingAngle={2}>
              {pieData.map((d, i) => <Cell key={i} fill={d.color} stroke="var(--ink)" />)}
            </Pie>
            <Tooltip
              contentStyle={{ background: "var(--ink-2)", border: "1px solid var(--hairline-2)" }}
              formatter={(v, name) => [`${Number(v).toFixed(2)}%`, String(name)]}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="grid grid-cols-3 gap-2 text-[11px] font-mono mt-2 mb-5">
        {pieData.map(d => (
          <div key={d.name} className="flex items-center gap-1.5">
            <span style={{ background: d.color, width: 8, height: 8, display: "inline-block" }} />
            <span className="text-[color:var(--fg-dim)]">{d.name}</span>
            <span className="num ml-auto">{d.value.toFixed(1)}%</span>
          </div>
        ))}
      </div>
      <div>
        <div className="smallcaps mb-2">By Underlying</div>
        {topUnder.length === 0 ? (
          <div className="text-[11.5px] font-mono text-[color:var(--fg-mute)]">—</div>
        ) : (
          <ul className="space-y-1.5">
            {topUnder.map(u => (
              <li key={u.ticker} className="grid grid-cols-[80px_1fr_auto] items-center gap-2 text-[12px] font-mono">
                <span>{u.ticker}</span>
                <span className="h-1.5 bg-[color:var(--ink-3)] relative">
                  <span
                    className="absolute inset-y-0 left-0 bg-[color:var(--signal)]"
                    style={{ width: `${(u.weight_pct / maxWeight) * 100}%` }}
                  />
                </span>
                <span className="num text-[color:var(--fg-dim)]">{fmtPct(u.weight_pct)} · {fmtUsd(u.market_value, { decimals: 0 })}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
