"use client";
import { useState, useEffect } from "react";
import type { Position } from "@/types/portfolio";
import type { SellRule } from "@/types/sell";
import { fmtUsd, fmtPct } from "@/lib/utils";
import { listSellRules } from "@/lib/sell-api";
import { SellButton } from "./sell-button";
import { SellRulePanel } from "./sell-rule-panel";

type Props = { positions: Position[]; loading: boolean; error: string | null; onRefresh: () => void };

type SortKey = "symbol" | "weight_pct" | "unrealized_pl";

export function PositionsTable({ positions, loading, error, onRefresh }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("weight_pct");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [rules, setRules] = useState<Record<string, SellRule>>({});

  useEffect(() => {
    listSellRules()
      .then(list => {
        const map: Record<string, SellRule> = {};
        for (const r of list) map[r.symbol] = r;
        setRules(map);
      })
      .catch(() => {/* ignore — sell rules are optional */});
  }, []);

  const sorted = [...positions].sort((a, b) => {
    const av = a[sortKey];
    const bv = b[sortKey];
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;
    if (av === bv) return 0;
    const cmp = av > bv ? 1 : -1;
    return sortDir === "asc" ? cmp : -cmp;
  });

  function toggle(k: SortKey) {
    if (sortKey === k) setSortDir(d => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir("desc"); }
  }

  return (
    <section className="px-5 py-5 border-b border-[color:var(--hairline)]">
      <h2 className="smallcaps panel-rule mb-4">Positions</h2>
      {error ? (
        <div className="text-[12px] text-[color:var(--down)]">Couldn't load positions — {error}</div>
      ) : loading ? (
        <div className="text-[12px] text-[color:var(--fg-mute)] font-mono">loading…</div>
      ) : positions.length === 0 ? (
        <div className="text-[12px] text-[color:var(--fg-mute)] font-mono">No open positions.</div>
      ) : (
        <table className="w-full text-[12.5px] font-mono">
          <thead>
            <tr className="text-[color:var(--fg-mute)] text-left">
              <th className="py-1 cursor-pointer" onClick={() => toggle("symbol")}>Symbol</th>
              <th>Kind</th>
              <th className="num text-right">Qty</th>
              <th className="num text-right">Avg</th>
              <th className="num text-right">Current</th>
              <th className="num text-right">Mkt Val</th>
              <th className="num text-right cursor-pointer" onClick={() => toggle("unrealized_pl")}>P/L</th>
              <th className="num text-right cursor-pointer" onClick={() => toggle("weight_pct")}>Weight</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(p => {
              const plColor = (p.unrealized_pl ?? 0) > 0 ? "var(--up)" : (p.unrealized_pl ?? 0) < 0 ? "var(--down)" : "var(--fg)";
              const isStock = p.kind === "stock";
              return (
                <>
                  <tr key={p.symbol} className="border-t border-[color:var(--hairline)]">
                    <td className="py-1.5 truncate max-w-[180px]">{p.symbol}</td>
                    <td className="text-[color:var(--fg-dim)]">{p.kind}</td>
                    <td className="num text-right">{p.qty}</td>
                    <td className="num text-right">{fmtUsd(p.avg_entry)}</td>
                    <td className="num text-right">{fmtUsd(p.current_price)}</td>
                    <td className="num text-right">{fmtUsd(p.market_value)}</td>
                    <td className="num text-right" style={{ color: plColor }}>{fmtUsd(p.unrealized_pl, { sign: true })}</td>
                    <td className="num text-right">{fmtPct(p.weight_pct)}</td>
                    <td className="pl-2 text-right">
                      {isStock && (
                        <SellButton
                          symbol={p.symbol}
                          qty={p.qty}
                          avg_entry={p.avg_entry}
                          onSold={onRefresh}
                        />
                      )}
                    </td>
                  </tr>
                  {isStock && (
                    <tr key={`${p.symbol}-rules`} className="border-t-0">
                      <td colSpan={9} className="pb-1.5 pt-0">
                        <SellRulePanel
                          symbol={p.symbol}
                          rule={rules[p.symbol] ?? null}
                          onRuleChange={r => setRules(prev => {
                            const next = { ...prev };
                            if (r) next[r.symbol] = r;
                            else delete next[p.symbol];
                            return next;
                          })}
                        />
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
