import { TickerInput } from "@/components/ticker-input";
import { AgentTrace } from "@/components/agent-trace";
import { ProposalCard } from "@/components/proposal-card";
import { PriceChart } from "@/components/price-chart";
import { OptionsChainTable } from "@/components/options-chain-table";
import { PortfolioPanel } from "@/components/portfolio-panel";

export default function Page() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr_380px] gap-4 p-4 h-screen">
      <aside className="space-y-4">
        <TickerInput />
        <PortfolioPanel />
      </aside>
      <main className="space-y-4 overflow-auto">
        <ProposalCard />
        <PriceChart />
        <OptionsChainTable />
      </main>
      <aside className="overflow-auto">
        <AgentTrace />
      </aside>
    </div>
  );
}
