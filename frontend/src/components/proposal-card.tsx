"use client";
import { useSession } from "@/lib/session-context";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { approveProposal, rejectProposal } from "@/lib/api";
import { useState } from "react";

export function ProposalCard() {
  const { proposal } = useSession();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  if (!proposal) return null;
  return (
    <Card className="border-primary">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Proposed trade — {proposal.ticker}
          <Badge>{(proposal.confidence * 100).toFixed(0)}% conf</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-3 gap-2 text-sm">
          <div><div className="text-muted-foreground">Max risk</div>${proposal.max_risk.toFixed(2)}</div>
          <div><div className="text-muted-foreground">Max reward</div>{proposal.max_reward != null ? "$"+proposal.max_reward.toFixed(2) : "Unlimited"}</div>
          <div><div className="text-muted-foreground">Breakeven</div>${proposal.breakeven?.toFixed(2) ?? "—"}</div>
        </div>
        <div>
          <div className="text-muted-foreground text-sm mb-1">Legs (expiry {proposal.expiry})</div>
          <ul className="text-sm">
            {proposal.legs.map((l, i) => <li key={i}>{l.action.toUpperCase()} {l.qty}x {l.contract_symbol} @ ${l.premium.toFixed(2)}</li>)}
          </ul>
        </div>
        <p className="text-sm">{proposal.rationale}</p>
        <div className="text-xs text-muted-foreground">Risks: {proposal.risks.join("; ")}</div>
        {result && <div className="text-sm">{result}</div>}
        <div className="flex gap-2">
          <Button disabled={busy} onClick={async () => { setBusy(true); try { const r = await approveProposal(proposal.proposal_id); setResult(`Order submitted: ${r.alpaca_order_id} (${r.status})`); } catch(e:any){ setResult(`Error: ${e.message}`);} finally { setBusy(false);} }}>
            Approve
          </Button>
          <Button variant="outline" disabled={busy} onClick={async () => { setBusy(true); await rejectProposal(proposal.proposal_id); setResult("Rejected"); setBusy(false); }}>
            Reject
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
