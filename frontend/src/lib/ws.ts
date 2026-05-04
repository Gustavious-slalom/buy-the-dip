"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import type { AgentEvent, Proposal } from "@/types/events";

export function useAgentSession() {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [status, setStatus] = useState<"idle"|"connecting"|"running"|"done"|"error">("idle");
  const ws = useRef<WebSocket | null>(null);
  const lastSessionId = useRef<string | null>(null);

  useEffect(() => {
    const url = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws";
    const socket = new WebSocket(url);
    ws.current = socket;
    socket.onopen = () => setStatus("idle");
    socket.onmessage = (m) => {
      const evt: AgentEvent = JSON.parse(m.data);
      if ((evt as any).session_id) lastSessionId.current = (evt as any).session_id;
      setEvents(prev => [...prev, evt]);
      if (evt.type === "agent.proposal") setProposal(evt.data as Proposal);
      if (evt.type === "agent.complete") setStatus("done");
      if (evt.type === "agent.error") setStatus("error");
    };
    socket.onclose = () => { ws.current = null; };
    return () => { ws.current?.close(); ws.current = null; };
  }, []);

  const sendIdea = useCallback((ticker: string, idea?: string) => {
    setEvents([]); setStatus("running"); // keep proposal visible until new one arrives
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
