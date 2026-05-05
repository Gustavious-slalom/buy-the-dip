"use client";
import type { MarketBrief } from "@/types/recommendations";

const BIAS_COLOR: Record<string, string> = {
  bullish: "var(--up)",
  bearish: "var(--down)",
  neutral: "var(--fg-dim)",
};

export function MarketBriefBanner({ brief }: { brief: MarketBrief | null }) {
  if (!brief) return null;
  const color = BIAS_COLOR[brief.bias] ?? "var(--fg-dim)";
  return (
    <section className="px-5 py-4 border-b border-[color:var(--hairline)] flex items-start gap-4">
      <span
        className="font-mono text-[10.5px] tracking-[.22em] px-2 py-[3px] mt-[3px]"
        style={{ background: color, color: "var(--ink)", fontWeight: 700 }}
      >
        {brief.bias.toUpperCase()}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-[14px] leading-snug">{brief.headline}</p>
        {brief.drivers.length > 0 && (
          <p className="text-[11.5px] font-mono text-[color:var(--fg-mute)] mt-1 truncate">
            {brief.drivers.join(" · ")}
          </p>
        )}
      </div>
    </section>
  );
}
