"use client";
import { useSession } from "@/lib/session-context";
import { useMemo } from "react";

const fmtUsd = (n: number | undefined) =>
  typeof n === "number"
    ? n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 })
    : "—";

export function PortfolioPanel() {
  const { events } = useSession();
  const portfolio = useMemo(() => {
    const ev = [...events].reverse().find(
      e => e.type === "agent.tool_result" && (e as { data: { name: string } }).data.name === "get_portfolio"
    );
    return ev ? (ev as { data: { output: { cash?: number; equity?: number; buying_power?: number } } }).data.output : null;
  }, [events]);

  return (
    <section className="px-4 py-5 border-b border-[color:var(--hairline)]">
      <h3 className="smallcaps panel-rule mb-4">
        Portfolio
        {portfolio?.equity != null && (
          <span className="num normal-case tracking-normal text-[11px] text-[color:var(--fg-dim)] ml-2">
            {fmtUsd(portfolio.equity)}
          </span>
        )}
      </h3>

      {!portfolio ? (
        <div className="text-[12px] text-[color:var(--fg-mute)] font-mono">
          waiting for snapshot…
        </div>
      ) : (
        <div className="grid grid-cols-[1fr_auto] gap-y-2 text-[12.5px]">
          <span className="smallcaps">Cash</span>
          <span className="num">{fmtUsd(portfolio.cash)}</span>
          <span className="smallcaps">Equity</span>
          <span className="num">{fmtUsd(portfolio.equity)}</span>
          <span className="smallcaps">Buying Pwr</span>
          <span className="num">{fmtUsd(portfolio.buying_power)}</span>
        </div>
      )}
    </section>
  );
}
