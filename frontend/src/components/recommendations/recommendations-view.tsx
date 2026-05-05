"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { RecommendationCard as Card, RecommendationRun } from "@/types/recommendations";
import { getLatestRecommendations } from "@/lib/api";
import { useRecommendationsStream } from "@/lib/recommendations-ws";
import { fmtTime } from "@/lib/utils";
import { RecommendationCard } from "./recommendation-card";
import { SourcesStrip } from "./sources-strip";

const SOURCE_RANK: Record<string, number> = { watchlist: 0, positions: 1, discover: 2 };

function sortCards(cards: Card[]): Card[] {
  return [...cards].sort((a, b) => {
    const aErr = a.error ? 1 : 0;
    const bErr = b.error ? 1 : 0;
    if (aErr !== bErr) return aErr - bErr;
    const sa = SOURCE_RANK[a.source] ?? 99;
    const sb = SOURCE_RANK[b.source] ?? 99;
    if (sa !== sb) return sa - sb;
    return (b.confidence ?? 0) - (a.confidence ?? 0);
  });
}

export function RecommendationsView() {
  const [latest, setLatest] = useState<RecommendationRun | null>(null);
  const [latestError, setLatestError] = useState<string | null>(null);
  const { state, start } = useRecommendationsStream();

  useEffect(() => {
    getLatestRecommendations()
      .then(setLatest)
      .catch((e: Error) => setLatestError(e.message));
  }, []);

  const liveActive = state.status === "running" || state.status === "done" || state.status === "error";
  const cards = liveActive ? state.cards : (latest?.cards ?? []);
  const sources = liveActive ? state.sources : (latest?.sources ?? null);
  const generatedAt = liveActive ? state.generatedAt : (latest?.generated_at ?? null);

  const sorted = useMemo(() => sortCards(cards), [cards]);
  const running = state.status === "running" || state.status === "connecting";
  const totalSources = sources
    ? sources.watchlist.length + sources.positions.length + sources.discover.length
    : 0;
  const hasAnything = sorted.length > 0 || totalSources > 0;

  return (
    <div className="flex flex-col">
      <header className="flex items-center justify-between px-5 py-4 border-b border-[color:var(--hairline)]">
        <h1 className="font-mono text-[18px] tracking-[.18em]">IDEAS</h1>
        <div className="flex items-center gap-4 text-[12px] text-[color:var(--fg-dim)]">
          <span className="num">
            {running
              ? `generating ${state.cards.length} of ${state.expectedCount || "…"}`
              : generatedAt
                ? `generated ${fmtTime(generatedAt)}`
                : "—"}
          </span>
          <button
            disabled={running}
            onClick={start}
            className="px-3 py-1.5 text-[11px] tracking-[.18em] uppercase border border-[color:var(--hairline-2)] hover:border-[color:var(--signal)] hover:text-[color:var(--signal)] disabled:opacity-40 transition-colors"
          >
            {running ? "Generating…" : "⟳ Generate"}
          </button>
          <Link
            href="/"
            className="px-3 py-1.5 text-[11px] tracking-[.18em] uppercase border border-[color:var(--hairline-2)] hover:border-[color:var(--signal)] hover:text-[color:var(--signal)] transition-colors"
          >
            ← Trade
          </Link>
        </div>
      </header>

      {state.warning === "no_candidates" && (
        <div className="px-5 py-4 text-[12px] text-[color:var(--amber)]">
          Add tickers to your watchlist or open a position to get started.
        </div>
      )}

      {state.warning && state.warning !== "no_candidates" && (
        <div className="px-5 py-3 text-[11.5px] text-[color:var(--amber)] font-mono">
          ⚠ {state.warning}
        </div>
      )}

      {state.errorMessage && (
        <div className="px-5 py-3 text-[12px] text-[color:var(--down)]">
          {state.errorMessage}
        </div>
      )}

      {latestError && !liveActive && (
        <div className="px-5 py-3 text-[12px] text-[color:var(--down)]">
          Couldn’t load latest run — {latestError}
        </div>
      )}

      {totalSources > 0 && <SourcesStrip sources={sources} />}

      {sorted.length === 0 && !running && !hasAnything && (
        <div className="px-5 py-12 text-center text-[12px] text-[color:var(--fg-mute)]">
          No ideas generated yet. Click <span className="text-[color:var(--fg-dim)]">⟳ Generate</span> to start.
        </div>
      )}

      <ul className="divide-y divide-[color:var(--hairline)]">
        {sorted.map(card => (
          <RecommendationCard key={`${card.symbol}-${card.source}`} card={card} />
        ))}
      </ul>
    </div>
  );
}
