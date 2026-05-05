"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { RecommendationCard, CandidateSet, StreamEvent } from "@/types/recommendations";

export type RecommendationsStatus = "idle" | "connecting" | "running" | "done" | "error";

export type RecommendationsState = {
  status: RecommendationsStatus;
  sources: CandidateSet | null;
  cards: RecommendationCard[];
  runId: string | null;
  generatedAt: string | null;
  warning: string | null;
  errorMessage: string | null;
  expectedCount: number;
};

const initial: RecommendationsState = {
  status: "idle",
  sources: null,
  cards: [],
  runId: null,
  generatedAt: null,
  warning: null,
  errorMessage: null,
  expectedCount: 0,
};

export function useRecommendationsStream() {
  const [state, setState] = useState<RecommendationsState>(initial);
  const ws = useRef<WebSocket | null>(null);

  const close = useCallback(() => {
    ws.current?.close();
    ws.current = null;
  }, []);

  useEffect(() => () => close(), [close]);

  const start = useCallback(() => {
    close();
    setState({ ...initial, status: "connecting" });

    const url = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws";
    const socket = new WebSocket(url);
    ws.current = socket;

    socket.onopen = () => {
      setState(s => ({ ...s, status: "running" }));
      socket.send(JSON.stringify({ type: "recommendation.start" }));
    };

    socket.onmessage = (m) => {
      let evt: StreamEvent;
      try {
        evt = JSON.parse(m.data) as StreamEvent;
      } catch {
        return;
      }
      setState(prev => {
        switch (evt.type) {
          case "recommendation.discovery": {
            const sources = evt.data.sources;
            const expected = sources.watchlist.length + sources.positions.length + sources.discover.length;
            return { ...prev, sources, expectedCount: expected };
          }
          case "recommendation.card":
            return { ...prev, cards: [...prev.cards, evt.data] };
          case "recommendation.discovery_warning":
            return { ...prev, warning: evt.data.message };
          case "recommendation.complete":
            return {
              ...prev,
              status: "done",
              runId: evt.data.run_id,
              generatedAt: evt.data.generated_at,
            };
          case "recommendation.error":
          case "error":
            return { ...prev, status: "error", errorMessage: evt.data.message };
          default:
            return prev;
        }
      });
    };

    socket.onerror = () => {
      setState(s => ({ ...s, status: "error", errorMessage: "WebSocket error" }));
    };

    socket.onclose = () => {
      setState(s => (s.status === "running" ? { ...s, status: "error", errorMessage: "stream interrupted" } : s));
      ws.current = null;
    };
  }, [close]);

  const reset = useCallback(() => setState(initial), []);

  return { state, start, reset };
}
