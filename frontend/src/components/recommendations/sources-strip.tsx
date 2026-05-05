"use client";
import type { CandidateSet } from "@/types/recommendations";

function Bucket({ label, tickers }: { label: string; tickers: string[] }) {
  if (tickers.length === 0) return null;
  return (
    <div className="flex items-baseline gap-2">
      <span className="smallcaps">{label}</span>
      <span className="font-mono text-[12px] text-[color:var(--fg-dim)]">{tickers.join(", ")}</span>
    </div>
  );
}

export function SourcesStrip({ sources }: { sources: CandidateSet | null }) {
  if (!sources) return null;
  const total = sources.watchlist.length + sources.positions.length + sources.discover.length;
  return (
    <section className="px-5 py-3 border-b border-[color:var(--hairline)]">
      <h3 className="smallcaps panel-rule mb-2">
        Sources
        <span className="num normal-case tracking-normal text-[11px] text-[color:var(--fg-dim)] ml-2">
          {total} candidate{total === 1 ? "" : "s"}
        </span>
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-x-6 gap-y-1.5">
        <Bucket label="Watchlist" tickers={sources.watchlist} />
        <Bucket label="Positions" tickers={sources.positions} />
        <Bucket label="Discover" tickers={sources.discover} />
      </div>
    </section>
  );
}
