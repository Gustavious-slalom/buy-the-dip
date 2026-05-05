"use client";
import type { AccountSummary as A } from "@/types/portfolio";
import { fmtUsd, fmtPct } from "@/lib/utils";

type Props = { account: A | null; loading: boolean; error: string | null };

export function AccountSummary({ account, loading, error }: Props) {
  if (error) {
    return (
      <section className="px-5 py-5 border-b border-[color:var(--hairline)] text-[12px] text-[color:var(--down)]">
        Account unavailable — {error}
      </section>
    );
  }
  if (loading || !account) {
    return (
      <section className="px-5 py-5 border-b border-[color:var(--hairline)] grid grid-cols-2 sm:grid-cols-4 gap-x-8 gap-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i}>
            <div className="smallcaps mb-1">—</div>
            <div className="num text-[20px] text-[color:var(--fg-mute)]">—</div>
          </div>
        ))}
      </section>
    );
  }
  const dayPlColor = (account.day_pl ?? 0) >= 0 ? "var(--up)" : "var(--down)";
  return (
    <section className="px-5 py-5 border-b border-[color:var(--hairline)] grid grid-cols-2 sm:grid-cols-4 gap-x-8 gap-y-3">
      <div>
        <div className="smallcaps mb-1">Equity</div>
        <div className="num text-[24px]">{fmtUsd(account.equity)}</div>
      </div>
      <div>
        <div className="smallcaps mb-1">Day P/L</div>
        <div className="num text-[24px]" style={{ color: dayPlColor }}>
          {fmtUsd(account.day_pl, { sign: true })}
          <span className="text-[12px] text-[color:var(--fg-mute)] ml-2">
            {fmtPct(account.day_pl_pct, { sign: true })}
          </span>
        </div>
      </div>
      <div>
        <div className="smallcaps mb-1">Cash</div>
        <div className="num text-[24px]">{fmtUsd(account.cash)}</div>
      </div>
      <div>
        <div className="smallcaps mb-1">Buying Power</div>
        <div className="num text-[24px]">{fmtUsd(account.buying_power)}</div>
      </div>
    </section>
  );
}
