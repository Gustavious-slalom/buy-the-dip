"use client";
import type { HistoryRow } from "@/types/portfolio";

type Props = { history: HistoryRow[]; loading: boolean; error: string | null };

const STATUS_COLOR: Record<HistoryRow["status"], string> = {
  pending: "var(--fg-dim)",
  approved: "var(--signal)",
  rejected: "var(--fg-mute)",
  executed: "var(--up)",
  failed: "var(--down)",
};

function fmtDt(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function HistoryTable({ history, loading, error }: Props) {
  return (
    <section className="px-5 py-5 border-b border-[color:var(--hairline)]">
      <h2 className="smallcaps panel-rule mb-4">History</h2>
      {error ? (
        <div className="text-[12px] text-[color:var(--down)]">Couldn’t load history — {error}</div>
      ) : loading ? (
        <div className="text-[12px] text-[color:var(--fg-mute)] font-mono">loading…</div>
      ) : history.length === 0 ? (
        <div className="text-[12px] text-[color:var(--fg-mute)] font-mono">No proposals yet.</div>
      ) : (
        <table className="w-full text-[12.5px] font-mono">
          <thead>
            <tr className="text-[color:var(--fg-mute)] text-left">
              <th className="py-1">Created</th>
              <th>Ticker</th>
              <th>Status</th>
              <th>Executed</th>
              <th>Order ID</th>
            </tr>
          </thead>
          <tbody>
            {history.map(h => (
              <tr key={h.proposal_id} className="border-t border-[color:var(--hairline)]">
                <td className="py-1.5 text-[color:var(--fg-dim)]">{fmtDt(h.created_at)}</td>
                <td>{h.ticker}</td>
                <td className="uppercase tracking-wide" style={{ color: STATUS_COLOR[h.status] }}>
                  {h.status}
                </td>
                <td className="text-[color:var(--fg-dim)]">{fmtDt(h.executed_at)}</td>
                <td className="text-[color:var(--fg-mute)] truncate max-w-[180px]" title={h.alpaca_order_id ?? ""}>
                  {h.alpaca_order_id ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
