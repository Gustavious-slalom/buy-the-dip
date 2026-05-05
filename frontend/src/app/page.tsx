import { Suspense } from "react";
import { TickerInput } from "@/components/ticker-input";
import { AgentTrace } from "@/components/agent-trace";
import { ProposalCard } from "@/components/proposal-card";
import { PriceChart } from "@/components/price-chart";
import { OptionsChainTable } from "@/components/options-chain-table";
import { PortfolioPanel } from "@/components/portfolio-panel";

export default function Page() {
  return (
    <div
      className="grid grid-cols-1 lg:grid-cols-[300px_1fr_380px]"
      style={{ height: "calc(100vh - 36px)" }}
    >
      <aside className="overflow-auto border-r border-[color:var(--hairline)] reveal reveal-1">
        <Suspense fallback={null}>
          <TickerInput />
        </Suspense>
        <PortfolioPanel />
      </aside>
      <main className="overflow-auto p-5 space-y-5 reveal reveal-2">
        <ProposalCard />
        <PriceChart />
        <OptionsChainTable />
      </main>
      <aside className="overflow-auto border-l border-[color:var(--hairline)] reveal reveal-3">
        <AgentTrace />
      </aside>
    </div>
  );
}
