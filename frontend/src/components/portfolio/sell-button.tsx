"use client";
import { useState } from "react";
import { sellPosition } from "@/lib/sell-api";

type Props = {
  symbol: string;
  qty: number;
  avg_entry: number;
  onSold: () => void;
};

export function SellButton({ symbol, qty, avg_entry, onSold }: Props) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConfirm() {
    setBusy(true);
    setError(null);
    try {
      await sellPosition(symbol, qty, avg_entry);
      setConfirming(false);
      onSold();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sell failed");
    } finally {
      setBusy(false);
    }
  }

  if (confirming) {
    return (
      <span className="inline-flex items-center gap-1">
        <button
          className="px-1.5 py-0.5 text-[11px] font-mono rounded bg-[color:var(--down)] text-white disabled:opacity-50"
          onClick={handleConfirm}
          disabled={busy}
        >
          {busy ? "…" : "Confirm"}
        </button>
        <button
          className="px-1.5 py-0.5 text-[11px] font-mono rounded bg-[color:var(--hairline)]"
          onClick={() => { setConfirming(false); setError(null); }}
          disabled={busy}
        >
          Cancel
        </button>
        {error && <span className="text-[10px] text-[color:var(--down)]">{error}</span>}
      </span>
    );
  }

  return (
    <button
      className="px-1.5 py-0.5 text-[11px] font-mono rounded border border-[color:var(--hairline)] hover:bg-[color:var(--down)] hover:text-white hover:border-transparent transition-colors"
      onClick={() => setConfirming(true)}
    >
      Sell
    </button>
  );
}
