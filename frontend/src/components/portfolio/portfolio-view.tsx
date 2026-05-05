"use client";
import { useCallback, useEffect, useState } from "react";
import type { PortfolioSnapshot } from "@/types/portfolio";
import { getPortfolioSnapshot } from "@/lib/api";
import { usePortfolioInvalidate } from "@/lib/portfolio-events";
import { PortfolioHeader } from "./portfolio-header";
import { AccountSummary } from "./account-summary";
import { EquityCurve } from "./equity-curve";
import { AllocationCard } from "./allocation-card";
import { StrategiesList } from "./strategies-list";
import { PositionsTable } from "./positions-table";
import { HistoryTable } from "./history-table";

function hasError(snap: PortfolioSnapshot | null, key: string): string | null {
  return snap?.errors.includes(key) ? key : null;
}

export function PortfolioView() {
  const [snap, setSnap] = useState<PortfolioSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    setError(null);
    getPortfolioSnapshot()
      .then(d => { setSnap(d); setLoading(false); })
      .catch((e: Error) => { setError(e.message); setLoading(false); });
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  usePortfolioInvalidate(refresh);

  return (
    <div className="flex flex-col">
      <PortfolioHeader fetchedAt={snap?.fetched_at ?? null} refreshing={loading} onRefresh={refresh} />

      {error && !snap && (
        <div className="px-5 py-4 text-[12px] text-[color:var(--down)]">
          Couldn’t load snapshot — {error} <button onClick={refresh} className="ml-2 underline">retry</button>
        </div>
      )}

      <AccountSummary
        account={snap?.account ?? null}
        loading={loading && !snap}
        error={hasError(snap, "account_unavailable")}
      />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 px-5 py-5 border-b border-[color:var(--hairline)]">
        <div className="lg:col-span-8">
          <EquityCurve />
        </div>
        <div className="lg:col-span-4">
          <AllocationCard
            allocations={snap?.allocations ?? null}
            loading={loading && !snap}
            error={null}
          />
        </div>
      </div>

      <StrategiesList
        strategies={snap?.strategies ?? []}
        loading={loading && !snap}
        error={hasError(snap, "strategies_unavailable")}
      />

      <PositionsTable
        positions={snap?.positions ?? []}
        loading={loading && !snap}
        error={hasError(snap, "positions_unavailable")}
      />

      <HistoryTable
        rows={snap?.history ?? []}
        loading={loading && !snap}
        error={hasError(snap, "history_unavailable")}
      />
    </div>
  );
}
