import type { SellOrder, SellRule } from "@/types/sell";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function parseError(r: Response): Promise<string> {
  const raw = await r.text();
  try {
    const json = JSON.parse(raw);
    if (typeof json?.detail === "string") return json.detail;
  } catch {
    // not JSON
  }
  return `Request failed (${r.status})`;
}

export async function sellPosition(
  symbol: string,
  qty: number,
  avg_entry: number,
): Promise<SellOrder> {
  const r = await fetch(`${BASE}/positions/sell`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ symbol, qty, avg_entry }),
  });
  if (!r.ok) throw new Error(await parseError(r));
  return r.json();
}

export async function setSellRule(
  symbol: string,
  take_profit: number,
  stop_loss: number,
  qty?: number,
): Promise<SellRule> {
  const r = await fetch(`${BASE}/positions/rules`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ symbol, take_profit, stop_loss, qty: qty ?? null }),
  });
  if (!r.ok) throw new Error(await parseError(r));
  return r.json();
}

export async function deleteSellRule(symbol: string): Promise<void> {
  const r = await fetch(`${BASE}/positions/rules/${encodeURIComponent(symbol)}`, {
    method: "DELETE",
  });
  if (!r.ok) throw new Error(await parseError(r));
}

export async function listSellRules(): Promise<SellRule[]> {
  const r = await fetch(`${BASE}/positions/rules`, { cache: "no-store" });
  if (!r.ok) throw new Error(await parseError(r));
  return r.json();
}
