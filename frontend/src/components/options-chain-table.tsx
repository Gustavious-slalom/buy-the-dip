"use client";
import { useSession } from "@/lib/session-context";

type Contract = {
  symbol: string;
  side: "call" | "put" | string;
  strike?: number;
  bid?: number;
  ask?: number;
  delta?: number;
  iv?: number;
  open_interest?: number;
  volume?: number;
};

export function OptionsChainTable() {
  const { events } = useSession();
  const ev = [...events].reverse().find(
    e => e.type === "agent.tool_result" && (e as { data: { name: string } }).data.name === "get_options_chain"
  );
  if (!ev) return null;

  const chain = (ev as { data: { output: { underlying: string; expiry: string; contracts?: Contract[] } } }).data.output;
  const rows: Contract[] = (chain.contracts ?? []).slice(0, 24);

  return (
    <section className="border border-[color:var(--hairline-2)] bg-[color:var(--ink-2)]">
      <header className="flex justify-between items-center px-4 py-3 border-b border-[color:var(--hairline)]">
        <h4 className="smallcaps">
          Options Chain · <span className="text-[color:var(--fg)] tracking-normal normal-case font-medium">{chain.underlying}</span>
        </h4>
        <span className="font-mono text-[11px] text-[color:var(--fg-mute)]">
          EXP {chain.expiry}
        </span>
      </header>

      <div className="overflow-auto">
        <table className="w-full font-mono text-[12px] num">
          <thead>
            <tr>
              {["Symbol", "Side", "Bid", "Ask", "Δ", "IV", "OI", "Vol"].map((h, i) => (
                <th
                  key={h}
                  className={
                    "px-3 py-2 text-[10px] tracking-[.18em] uppercase font-normal text-[color:var(--fg-mute)] border-b border-[color:var(--hairline)] " +
                    (i === 0 ? "text-left" : "text-right")
                  }
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => {
              const isCall = c.side === "call";
              return (
                <tr
                  key={c.symbol}
                  className="hover:bg-[oklch(0.92_0.21_130/0.04)] hover:text-[color:var(--fg)] text-[color:var(--fg-dim)] transition-colors"
                >
                  <td className="px-3 py-1.5 text-left text-[color:var(--fg)] truncate max-w-[260px]">{c.symbol}</td>
                  <td className="px-3 py-1.5 text-right">
                    <span style={{ color: isCall ? "var(--up)" : "var(--down)" }}>
                      {isCall ? "C" : "P"}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 text-right" style={{ color: "var(--up)" }}>
                    {c.bid?.toFixed(2) ?? "—"}
                  </td>
                  <td className="px-3 py-1.5 text-right" style={{ color: "var(--down)" }}>
                    {c.ask?.toFixed(2) ?? "—"}
                  </td>
                  <td className="px-3 py-1.5 text-right">{c.delta?.toFixed(2) ?? "—"}</td>
                  <td className="px-3 py-1.5 text-right">
                    {typeof c.iv === "number" ? (c.iv * 100).toFixed(1) + "%" : "—"}
                  </td>
                  <td className="px-3 py-1.5 text-right">{c.open_interest ?? "—"}</td>
                  <td className="px-3 py-1.5 text-right">{c.volume ?? "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {rows.length === 0 && (
        <div className="px-4 py-6 text-center text-[12px] font-mono text-[color:var(--fg-mute)]">
          no contracts in window
        </div>
      )}
    </section>
  );
}
