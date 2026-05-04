export type AgentEvent =
  | { type: "agent.status"; ts: string; session_id: string; data: { message: string } }
  | { type: "agent.thinking"; ts: string; session_id: string; data: { delta: string } }
  | { type: "agent.tool_call"; ts: string; session_id: string; data: { tool_use_id: string; name: string; input: any } }
  | { type: "agent.tool_result"; ts: string; session_id: string; data: { tool_use_id: string; name: string; output: any; error?: string } }
  | { type: "agent.proposal"; ts: string; session_id: string; data: Proposal }
  | { type: "agent.complete"; ts: string; session_id: string; data: any }
  | { type: "agent.error"; ts: string; session_id: string; data: { message: string } };

export type Proposal = {
  proposal_id: string;
  ticker: string;
  legs: Array<{ action: "buy"|"sell"; side: "call"|"put"; qty: number; strike: number; premium: number; contract_symbol: string }>;
  max_risk: number;
  max_reward: number | null;
  breakeven: number | null;
  expiry: string;
  rationale: string;
  confidence: number;
  risks: string[];
};
