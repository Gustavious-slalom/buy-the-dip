export type SellOrder = {
  ok: boolean;
  sell_order_id: string;
  alpaca_order_id: string;
  status: string;
};

export type SellRule = {
  symbol: string;
  take_profit: number;   // e.g. 0.01 = 1%
  stop_loss: number;     // e.g. -0.003 = -0.3%
  qty: number | null;
  active: boolean;
  created_at: string;
  updated_at: string;
};
