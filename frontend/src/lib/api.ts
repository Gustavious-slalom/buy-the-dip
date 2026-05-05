const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function parseErrorMessage(r: Response): Promise<string> {
  const raw = await r.text();
  console.error(`API error ${r.status}:`, raw);
  try {
    const json = JSON.parse(raw);
    if (typeof json?.detail === "string") return json.detail;
    if (typeof json?.message === "string") return json.message;
  } catch {
    // not JSON — fall through to generic message
  }
  return `Request failed (${r.status})`;
}

export async function approveProposal(id: string) {
  const r = await fetch(`${BASE}/proposals/approve`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ proposal_id: id }),
  });
  if (!r.ok) throw new Error(await parseErrorMessage(r));
  return r.json();
}

export async function rejectProposal(id: string) {
  const r = await fetch(`${BASE}/proposals/reject`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ proposal_id: id }),
  });
  if (!r.ok) throw new Error(await parseErrorMessage(r));
  return r.json();
}
