"use client";
import { useState } from "react";
import type { StrategyGroup } from "@/types/portfolio";
import { fmtUsd, fmtPct } from "@/lib/utils";

type Props = { strategies: StrategyGroup[]; loading: boolean; error: string | null };

export function StrategiesList({ strategies, loading, error }: Props) {
  const [open, setOpen] = useState<Record<string, boolean>>({});

  return (
    <section className="px-5 py-5 border-b border-[color:var(--hairline)]">
      <h2 className="smallcaps panel-rule mb-4">Strategies</h2>
      {error ? (
        <div className="text-[12px] text-[color:var(--down)]">Couldn’t load strategies — {error}</div>
      ) : loading ? (
        <div className="text-[12px] text-[color:var(--fg-mute)] font-mono">loading…</div>
      ) : strategies.length === 0 ? (
        <div className="text-[12px] text-[color:var(--fg-mute)] font-mono">No active strategies.</div>
      ) : (
        <ul className="divide-y divide-[color:var(--hairline)]">
          {strategies.map(g => {
            const plColor = (g.unrealized_pl ?? 0) > 0 ? "var(--up)" : (g.unrealized_pl ?? 0) < 0 ? "var(--down)" : "var(--fg)";
            const isOpen = open[g.proposal_id];
            return (
              <li key={g.proposal_id} className="py-3">
                <button
                  onClick={() => setOpen(o => ({ ...o, [g.proposal_id]: !isOpen }))}
                  className="w-full flex items-center justify-between gap-4 text-left"
                >
                  <span className="font-mono text-[13px]">
                    <span className="text-[color:var(--fg)] mr-2">{isOpen ? "▾" : "▸"}</span>
                    <b>{g.ticker}</b>{" "}
                    <span className="text-[color:var(--fg-dim)]">{g.type}</span>{" "}
                    <span className="text-[color:var(--fg-mute)]">exp {g.expiry}</span>
                  </span>
                  <span className="num text-[12.5px]" style={{ color: plColor }}>
                    {fmtUsd(g.unrealized_pl, { sign: true })}
                    <span className="ml-2 text-[color:var(--fg-mute)]">{fmtPct(g.unrealized_pl_pct, { sign: true })}</span>
                  </span>
                </button>
                {isOpen && (
                  <div className="mt-2 ml-5 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[12px] font-mono">
                    <span className="smallcaps">Cost</span>
                    <span className="num">{fmtUsd(g.cost_basis)}</span>
                    <span className="smallcaps">Now</span>
                    <span className="num">{fmtUsd(g.current_value)}</span>
                    <span className="smallcaps">Legs</span>
                    <span>{g.legs_open} of {g.legs_total} open</span>
                    <span className="smallcaps">Contracts</span>
                    <ul className="space-y-0.5">
                      {g.legs.map((l, i) => (
                        <li key={i} className="text-[color:var(--fg-dim)]">
                          <span className="text-[color:var(--fg)] mr-2">{l.side.toUpperCase()}</span>×{l.qty} {l.symbol}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
