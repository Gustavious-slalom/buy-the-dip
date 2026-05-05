"use client";
import { useState } from "react";
import { useSession } from "@/lib/session-context";

export function TickerInput() {
  const { sendIdea, sendReplay, status } = useSession();
  const [v, setV] = useState("AAPL");
  const running = status === "running";

  return (
    <section className="px-4 py-5 border-b border-[color:var(--hairline)]">
      <h3 className="smallcaps panel-rule mb-4">Symbol</h3>

      <label
        className="flex items-center gap-2 px-3 py-2.5 bg-[color:var(--ink-2)] border border-[color:var(--hairline-2)] focus-within:border-[color:var(--signal)] transition-colors"
      >
        <span className="font-mono text-[color:var(--fg-mute)]">$</span>
        <input
          value={v}
          onChange={e => setV(e.target.value.toUpperCase())}
          placeholder="AAPL"
          className="flex-1 bg-transparent outline-none border-0 font-mono text-[18px] tracking-[.05em] uppercase placeholder:text-[color:var(--fg-mute)]"
          onKeyDown={(e) => { if (e.key === "Enter" && !running && v.trim()) sendIdea(v.trim()); }}
        />
        <span className="caret" />
      </label>

      <div className="flex gap-2 mt-3">
        <button
          disabled={running || !v.trim()}
          onClick={() => sendIdea(v.trim())}
          className="flex-1 py-2.5 text-[11px] font-bold tracking-[.22em] uppercase bg-[color:var(--signal)] text-[color:var(--ink)] disabled:opacity-40 disabled:cursor-not-allowed hover:shadow-[0_0_24px_rgba(198,255,59,.30)] transition-shadow"
        >
          {running ? "Thinking…" : "Analyze ▸"}
        </button>
        <button
          disabled={running}
          onClick={() => sendReplay()}
          className="px-3 py-2.5 text-[11px] tracking-[.22em] uppercase border border-[color:var(--hairline-2)] hover:border-[color:var(--fg-dim)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          title="Replay last session"
        >
          Replay
        </button>
      </div>

      <div className="mt-4 grid grid-cols-[1fr_auto] gap-y-1.5 text-[12px]">
        <span className="smallcaps">Status</span>
        <span className="num text-[color:var(--fg)]">
          {status}
        </span>
      </div>
    </section>
  );
}
