"use client";
import { createContext, useContext } from "react";
import { useAgentSession } from "./ws";

const Ctx = createContext<ReturnType<typeof useAgentSession> | null>(null);
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const v = useAgentSession();
  return <Ctx.Provider value={v}>{children}</Ctx.Provider>;
}
export function useSession() {
  const v = useContext(Ctx);
  if (!v) throw new Error("SessionProvider missing");
  return v;
}
