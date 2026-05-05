export type Bias = "bullish" | "bearish" | "neutral";
export type Source = "watchlist" | "positions" | "discover";

export type Headline = { headline: string; url: string };

export type RecommendationCard = {
  symbol: string;
  source: Source;
  bias: Bias;
  confidence: number;
  rationale: string;
  top_headlines: Headline[];
  error?: string;
};

export type CandidateSet = {
  watchlist: string[];
  positions: string[];
  discover: string[];
};

export type RecommendationRun = {
  run_id: string | null;
  generated_at: string | null;
  cards: RecommendationCard[];
  sources: CandidateSet;
};

export type StreamEvent =
  | { type: "recommendation.discovery"; ts?: string; data: { sources: CandidateSet } }
  | { type: "recommendation.card"; ts?: string; data: RecommendationCard }
  | { type: "recommendation.complete"; ts?: string; data: { run_id: string; generated_at: string; count: number } }
  | { type: "recommendation.discovery_warning"; ts?: string; data: { message: string } }
  | { type: "recommendation.error"; ts?: string; data: { message: string } }
  | { type: "error"; ts?: string; data: { message: string } };
