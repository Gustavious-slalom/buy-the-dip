"use client";
import { useState, useEffect } from "react";
import type { SellRule } from "@/types/sell";
import { setSellRule, deleteSellRule } from "@/lib/sell-api";
import { fmtPct } from "@/lib/utils";

type Props = {
  symbol: string;
  rule: SellRule | null;
  onRuleChange: (rule: SellRule | null) => void;
};

export function SellRulePanel({ symbol, rule, onRuleChange }: Props) {
  const [open, setOpen] = useState(false);
  const [tp, setTp] = useState(rule ? String(rule.take_profit * 100) : "1");
  const [sl, setSl] = useState(rule ? String(Math.abs(rule.stop_loss) * 100) : "0.3");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sync input state when rule changes (e.g. loaded asynchronously after mount)
  useEffect(() => {
    if (rule) {
      setTp(String(rule.take_profit * 100));
      setSl(String(Math.abs(rule.stop_loss) * 100));
    }
  }, [rule]);

  const isActive = rule?.active === true;

  async function handleSave() {
    const tpVal = parseFloat(tp) / 100;
    const slVal = -(parseFloat(sl) / 100);
    if (isNaN(tpVal) || tpVal <= 0 || tpVal > 1) {
      setError("Take-profit must be between 0.01% and 100%");
      return;
    }
    if (isNaN(slVal) || slVal >= 0 || slVal < -1) {
      setError("Stop-loss must be between 0.01% and 100%");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await setSellRule(symbol, tpVal, slVal);
      onRuleChange(updated);
      setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove() {
    setBusy(true);
    setError(null);
    try {
      await deleteSellRule(symbol);
      onRuleChange(null);
      setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Remove failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="text-[11px] font-mono">
      <button
        className="flex items-center gap-1 text-[color:var(--fg-mute)] hover:text-[color:var(--fg)] transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        <span>{open ? "▾" : "▸"}</span>
        {isActive ? (
          <span className="text-[color:var(--up)]">
            Auto rules: +{fmtPct(rule!.take_profit * 100)} / -{fmtPct(Math.abs(rule!.stop_loss) * 100)}
          </span>
        ) : (
          <span>Set auto rules</span>
        )}
      </button>

      {open && (
        <div className="mt-1.5 ml-3 flex flex-col gap-1.5 border-l border-[color:var(--hairline)] pl-3">
          <label className="flex items-center gap-2">
            <span className="w-24 text-[color:var(--fg-mute)]">Take-profit %</span>
            <input
              type="number"
              min="0.01"
              max="100"
              step="0.01"
              value={tp}
              onChange={e => setTp(e.target.value)}
              className="w-16 bg-transparent border border-[color:var(--hairline)] rounded px-1 py-0.5 text-right"
            />
          </label>
          <label className="flex items-center gap-2">
            <span className="w-24 text-[color:var(--fg-mute)]">Stop-loss %</span>
            <input
              type="number"
              min="0.01"
              max="100"
              step="0.01"
              value={sl}
              onChange={e => setSl(e.target.value)}
              className="w-16 bg-transparent border border-[color:var(--hairline)] rounded px-1 py-0.5 text-right"
            />
          </label>
          {error && <div className="text-[color:var(--down)]">{error}</div>}
          <div className="flex gap-2 mt-0.5">
            <button
              className="px-2 py-0.5 rounded bg-[color:var(--up)] text-white disabled:opacity-50"
              onClick={handleSave}
              disabled={busy}
            >
              {busy ? "…" : "Save"}
            </button>
            {isActive && (
              <button
                className="px-2 py-0.5 rounded border border-[color:var(--hairline)] disabled:opacity-50"
                onClick={handleRemove}
                disabled={busy}
              >
                Remove
              </button>
            )}
            <button
              className="px-2 py-0.5 rounded border border-[color:var(--hairline)]"
              onClick={() => { setOpen(false); setError(null); }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
