"use client";
import Link from "next/link";
import { fmtTime } from "@/lib/utils";

type Props = {
  fetchedAt: string | null;
  refreshing: boolean;
  onRefresh: () => void;
};

export function PortfolioHeader({ fetchedAt, refreshing, onRefresh }: Props) {
  return (
    <header className="flex items-center justify-between px-5 py-4 border-b border-[color:var(--hairline)]">
      <h1 className="font-mono text-[18px] tracking-[.18em]">PORTFOLIO</h1>
      <div className="flex items-center gap-4 text-[12px] text-[color:var(--fg-dim)]">
        <span className="num">
          {fetchedAt ? `last updated ${fmtTime(fetchedAt)}` : "—"}
        </span>
        <button
          disabled={refreshing}
          onClick={onRefresh}
          className="px-3 py-1.5 text-[11px] tracking-[.18em] uppercase border border-[color:var(--hairline-2)] hover:border-[color:var(--signal)] hover:text-[color:var(--signal)] disabled:opacity-40 transition-colors"
        >
          {refreshing ? "Refreshing…" : "⟳ Refresh"}
        </button>
        <Link
          href="/"
          className="px-3 py-1.5 text-[11px] tracking-[.18em] uppercase border border-[color:var(--hairline-2)] hover:border-[color:var(--signal)] hover:text-[color:var(--signal)] transition-colors"
        >
          ← Trade
        </Link>
      </div>
    </header>
  );
}
