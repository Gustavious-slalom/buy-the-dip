export type Period = "1D" | "1W" | "1M" | "3M" | "ALL";

export type PositionKind = "stock" | "option";

export type Position = {
  symbol: string;
  kind: PositionKind;
  qty: number;
  avg_entry: number;
  current_price: number | null;
  market_value: number | null;
  unrealized_pl: number | null;
  unrealized_pl_pct: number | null;
  weight_pct: number | null;
  underlying: string;
  strike?: number;
  side?: "call" | "put";
  expiry?: string;
};

export type StrategyLeg = { symbol: string; qty: number; side: "buy" | "sell" };

export type StrategyGroup = {
  proposal_id: string;
  ticker: string;
  type: string;
  legs: StrategyLeg[];
  cost_basis: number;
  current_value: number | null;
  unrealized_pl: number | null;
  unrealized_pl_pct: number | null;
  expiry: string;
  legs_open: number;
  legs_total: number;
};

export type Allocations = {
  by_kind: { stock: number; option: number; cash: number };
  by_underlying: { ticker: string; weight_pct: number; market_value: number }[];
};

export type HistoryRow = {
  proposal_id: string;
  ticker: string;
  status: "pending" | "approved" | "rejected" | "executed" | "failed";
  created_at: string;
  executed_at: string | null;
  alpaca_order_id: string | null;
};

export type AccountSummary = {
  cash: number | null;
  equity: number | null;
  buying_power: number | null;
  day_pl: number | null;
  day_pl_pct: number | null;
};

export type PortfolioSnapshot = {
  fetched_at: string;
  account: AccountSummary;
  positions: Position[];
  strategies: StrategyGroup[];
  allocations: Allocations;
  history: HistoryRow[];
  errors: string[];
};

export type EquityCurve = {
  period: Period;
  points: { t: string; equity: number }[];
  base_value: number;
  profit_loss: number;
  profit_loss_pct: number;
};
