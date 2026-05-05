"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import type { AgentEvent, Proposal } from "@/types/events";

const MAX_RETRIES = 5;

export type ConnectionStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected"
  | "running"
  | "done"
  | "error";

export function useAgentSession() {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("idle");
  const ws = useRef<WebSocket | null>(null);
  const lastSessionId = useRef<string | null>(null);
  const retryCount = useRef(0);
  const isManualClose = useRef(false);

  const connect = useCallback(() => {
    const url = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws";
    setStatus("connecting");
    const socket = new WebSocket(url);
    ws.current = socket;

    socket.onopen = () => {
      retryCount.current = 0;
      setStatus("idle");
    };

    socket.onmessage = (m) => {
      const evt: AgentEvent = JSON.parse(m.data);
      if ((evt as any).session_id) lastSessionId.current = (evt as any).session_id;
      setEvents(prev => [...prev, evt]);
      if (evt.type === "agent.proposal") setProposal(evt.data as Proposal);
      if (evt.type === "agent.complete") setStatus("done");
      if (evt.type === "agent.error") setStatus("error");
    };

    socket.onclose = () => {
      ws.current = null;
      if (isManualClose.current) return;
      if (retryCount.current < MAX_RETRIES) {
        const delay = Math.min(1000 * Math.pow(2, retryCount.current), 30000);
        retryCount.current += 1;
        setStatus("reconnecting");
        setTimeout(connect, delay);
      } else {
        setStatus("disconnected");
      }
    };
  }, []);

  useEffect(() => {
    isManualClose.current = false;
    connect();
    return () => {
      isManualClose.current = true;
      ws.current?.close();
      ws.current = null;
    };
  }, [connect]);

  const sendIdea = useCallback((ticker: string, idea?: string) => {
    setEvents([]); setStatus("running");
    ws.current?.send(JSON.stringify({ type: "session.start", data: { ticker, idea } }));
  }, []);

  const sendReplay = useCallback((sid?: string) => {
    const target = sid ?? lastSessionId.current;
    if (!target) return;
    setEvents([]); setStatus("running");
    ws.current?.send(JSON.stringify({ type: "replay", data: { session_id: target } }));
  }, []);

  return { events, proposal, status, sendIdea, sendReplay };
}
