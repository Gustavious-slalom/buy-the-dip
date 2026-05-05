import type { PortfolioSnapshot, EquityCurve, Period } from "@/types/portfolio";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function approveProposal(id: string) {
  const r = await fetch(`${BASE}/proposals/approve`, { method: "POST", headers: {"content-type":"application/json"}, body: JSON.stringify({ proposal_id: id })});
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function rejectProposal(id: string) {
  const r = await fetch(`${BASE}/proposals/reject`, { method: "POST", headers: {"content-type":"application/json"}, body: JSON.stringify({ proposal_id: id })});
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function getPortfolioSnapshot(): Promise<PortfolioSnapshot> {
  const r = await fetch(`${BASE}/portfolio/snapshot`, { cache: "no-store" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function getEquityCurve(period: Period): Promise<EquityCurve> {
  const r = await fetch(`${BASE}/portfolio/equity-curve?period=${period}`, { cache: "no-store" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
