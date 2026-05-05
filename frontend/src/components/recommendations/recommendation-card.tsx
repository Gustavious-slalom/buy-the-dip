"use client";
import Link from "next/link";
import type { RecommendationCard as Card } from "@/types/recommendations";

const BIAS_COLOR: Record<string, string> = {
  bullish: "var(--up)",
  bearish: "var(--down)",
  neutral: "var(--fg-dim)",
};

const SOURCE_LABEL: Record<string, string> = {
  watchlist: "from watchlist",
  positions: "from positions",
  discover: "from discover",
};

function ConfidenceBar({ value }: { value: number }) {
  const filled = Math.max(0, Math.min(10, Math.round(value * 10)));
  const segments = Array.from({ length: 10 }, (_, i) => i < filled);
  return (
    <span className="inline-flex gap-[2px] align-middle">
      {segments.map((on, i) => (
        <span
          key={i}
          className="block"
          style={{ width: 7, height: 9, background: on ? "var(--signal)" : "var(--ink-3)" }}
        />
      ))}
    </span>
  );
}

export function RecommendationCard({ card }: { card: Card }) {
  if (card.error) {
    return (
      <li className="px-5 py-4 border-b border-[color:var(--hairline)] flex items-center gap-3">
        <span className="font-mono text-[14px] text-[color:var(--down)]">⚠ {card.symbol}</span>
        <span className="text-[12px] text-[color:var(--fg-dim)]">
          couldn’t analyze — {card.error}
        </span>
      </li>
    );
  }
  const biasColor = BIAS_COLOR[card.bias] ?? "var(--fg-dim)";
  return (
    <li className="px-5 py-4 border-b border-[color:var(--hairline)]">
      <div className="flex items-center gap-3 flex-wrap">
        <span className="font-mono text-[18px] tracking-[.04em]">{card.symbol}</span>
        <span
          className="font-mono text-[10.5px] tracking-[.22em] px-2 py-[3px]"
          style={{ background: biasColor, color: "var(--ink)", fontWeight: 700 }}
        >
          {card.bias.toUpperCase()}
        </span>
        <ConfidenceBar value={card.confidence} />
        <span className="num text-[12px] text-[color:var(--fg-dim)]">{card.confidence.toFixed(2)}</span>
        <span className="text-[11px] text-[color:var(--fg-mute)] ml-auto">{SOURCE_LABEL[card.source] ?? card.source}</span>
      </div>

      <p className="text-[13px] text-[color:var(--fg)] mt-3 leading-[1.55]">{card.rationale}</p>

      {card.top_headlines.length > 0 && (
        <ul className="mt-2 text-[11.5px] font-mono text-[color:var(--fg-mute)] space-y-1">
          {card.top_headlines.map((h, i) => (
            <li key={i}>
              •{" "}
              <a href={h.url} target="_blank" rel="noopener noreferrer" className="hover:text-[color:var(--signal)] underline-offset-2 hover:underline">
                {h.headline}
              </a>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3">
        <Link
          href={`/?ticker=${encodeURIComponent(card.symbol)}&autosubmit=1`}
          className="inline-block px-4 py-2 text-[11px] tracking-[.22em] uppercase border border-[color:var(--hairline-2)] hover:border-[color:var(--signal)] hover:text-[color:var(--signal)] transition-colors"
        >
          Analyze →
        </Link>
      </div>
    </li>
  );
}
