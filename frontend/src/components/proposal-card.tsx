"use client";
import { useSession } from "@/lib/session-context";
import { approveProposal, rejectProposal } from "@/lib/api";
import { emitPortfolioInvalidate } from "@/lib/portfolio-events";
import { useState } from "react";

const fmtUsd = (n: number | null | undefined) =>
  typeof n === "number"
    ? "$" + n.toLocaleString("en-US", { maximumFractionDigits: 2, minimumFractionDigits: 2 })
    : "—";

export function ProposalCard() {
  const { proposal } = useSession();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  if (!proposal) return null;

  const conf = Math.round(proposal.confidence * 100);

  return (
    <section
      className="relative border border-[color:var(--hairline-2)] bg-[color:var(--ink-2)] p-5"
      style={{
        backgroundImage: "linear-gradient(180deg, oklch(0.92 0.21 130 / 0.04), transparent 30%)",
        boxShadow: "inset 0 1px 0 oklch(1 0 0 / 0.04)",
      }}
    >
      <span
        className="absolute -top-2.5 left-5 px-2.5 font-mono text-[10.5px] tracking-[.22em] bg-[color:var(--ink)] text-[color:var(--signal)]"
      >
        PROPOSAL · {proposal.proposal_id?.slice(0, 8) ?? "—"}
      </span>

      <header className="flex items-end gap-5 mb-4">
        <div>
          <div className="text-[12px] tracking-[.04em] text-[color:var(--fg-dim)] mb-1">
            EXPIRY <b className="num text-[color:var(--fg)]">{proposal.expiry}</b>
          </div>
          <div className="font-mono text-[42px] leading-none tracking-[.02em] font-medium">
            {proposal.ticker}
          </div>
        </div>
        <div className="ml-auto text-right">
          <div className="smallcaps">Confidence</div>
          <div className="num text-[24px] font-medium" style={{ color: "var(--signal)" }}>
            {(proposal.confidence).toFixed(2)}
            <span className="text-[12px] text-[color:var(--fg-mute)] ml-1">· {conf}%</span>
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 my-4">
        {proposal.legs.map((l, i) => {
          const isBuy = l.action === "buy";
          return (
            <div
              key={i}
              className="grid grid-cols-[auto_1fr_auto] gap-2 items-center px-3 py-3 border border-[color:var(--hairline-2)] bg-[color:var(--ink-3)]"
            >
              <span
                className="font-mono text-[10.5px] tracking-[.18em] px-2 py-[3px]"
                style={{
                  background: isBuy ? "var(--up)" : "var(--amber)",
                  color: "var(--ink)",
                  fontWeight: 700,
                }}
              >
                {isBuy ? "BUY" : "SELL"}
              </span>
              <span className="font-mono text-[13px] truncate">
                <span className="text-[color:var(--fg-mute)] mr-1">×{l.qty}</span>
                {l.contract_symbol}
              </span>
              <span className="num text-[color:var(--fg-dim)]">@ {l.premium.toFixed(2)}</span>
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap gap-x-6 gap-y-1.5 text-[12px] text-[color:var(--fg-dim)] mt-2">
        <span>
          MAX RISK <span className="num text-[color:var(--down)] ml-1">{fmtUsd(-Math.abs(proposal.max_risk))}</span>
        </span>
        <span>
          MAX REWARD{" "}
          <span className="num text-[color:var(--up)] ml-1">
            {proposal.max_reward != null ? fmtUsd(proposal.max_reward) : "Unlimited"}
          </span>
        </span>
        <span>
          BREAKEVEN <span className="num text-[color:var(--fg)] ml-1">{fmtUsd(proposal.breakeven)}</span>
        </span>
      </div>

      <p className="text-[13px] text-[color:var(--fg)] mt-4 leading-[1.55]">
        {proposal.rationale}
      </p>

      {proposal.risks?.length > 0 && (
        <div className="mt-3 text-[11.5px] text-[color:var(--fg-mute)] font-mono leading-[1.55]">
          <span style={{ color: "var(--amber)", letterSpacing: ".18em" }}>RISKS ▸</span>{" "}
          {proposal.risks.join(" · ")}
        </div>
      )}

      {result && (
        <div className="mt-3 px-3 py-2 border border-[color:var(--hairline-2)] bg-[color:var(--ink-3)] font-mono text-[12px]">
          {result}
        </div>
      )}

      <div className="flex gap-2 mt-5">
        <button
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              const r = await approveProposal(proposal.proposal_id);
              setResult(`Order ${r.alpaca_order_id} · ${r.status}`);
              emitPortfolioInvalidate();
            } catch (e) {
              setResult(`Error: ${(e as Error).message}`);
            } finally {
              setBusy(false);
            }
          }}
          className="px-5 py-3 text-[11px] font-bold tracking-[.22em] uppercase bg-[color:var(--signal)] text-[color:var(--ink)] disabled:opacity-40 hover:shadow-[0_0_24px_rgba(198,255,59,.30)] transition-shadow"
        >
          Approve · Submit
        </button>
        <button
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await rejectProposal(proposal.proposal_id);
              setResult("Rejected");
              emitPortfolioInvalidate();
            } catch (e) {
              setResult(`Error: ${(e as Error).message}`);
            } finally {
              setBusy(false);
            }
          }}
          className="px-5 py-3 text-[11px] tracking-[.22em] uppercase border border-[color:var(--hairline-2)] hover:border-[color:var(--down)] hover:text-[color:var(--down)] disabled:opacity-40 transition-colors"
        >
          Reject
        </button>
      </div>
    </section>
  );
}
