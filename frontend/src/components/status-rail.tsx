"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession } from "@/lib/session-context";

function useClock() {
  const [t, setT] = useState<string>("--:--:--");
  useEffect(() => {
    const tick = () => {
      const d = new Date();
      const fmt = new Intl.DateTimeFormat("en-US", {
        hour: "2-digit", minute: "2-digit", second: "2-digit",
        hour12: false, timeZone: "America/New_York",
      });
      setT(fmt.format(d));
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return t;
}

export function StatusRail() {
  const clock = useClock();
  const { status, events } = useSession();
  const pathname = usePathname();
  const lastTool = [...events].reverse().find(e => e.type === "agent.tool_call") as { data: { name: string } } | undefined;

  const stateLabel =
    status === "running" ? "thinking" :
    status === "done"    ? "ready"    :
    status === "error"   ? "error"    :
    status === "connecting" ? "connecting" : "idle";

  const stateColor =
    status === "error" ? "var(--down)" :
    status === "running" ? "var(--signal)" :
    "var(--fg-dim)";

  return (
    <div
      className="reveal flex items-center gap-6 px-4 border-b border-[color:var(--hairline)] text-[11px]"
      style={{
        height: 36,
        letterSpacing: ".14em",
        textTransform: "uppercase",
        color: "var(--fg-dim)",
        background: "linear-gradient(180deg, rgba(255,255,255,.02), transparent)",
      }}
    >
      <span className="font-bold" style={{ color: "var(--fg)", letterSpacing: ".22em" }}>
        <span className="signal-dot inline-block mr-2 align-middle" />
        BUY·THE·DIP
      </span>

      <span className="w-px h-3.5 bg-[color:var(--hairline-2)]" />

      <span className="num" style={{ color: "var(--fg)", letterSpacing: ".06em" }}>
        {clock} ET
      </span>

      <span className="w-px h-3.5 bg-[color:var(--hairline-2)]" />

      <span className="hidden md:inline">
        TOOL <b className="num ml-2" style={{ color: "var(--fg)", letterSpacing: ".06em" }}>
          {lastTool ? lastTool.data.name : "—"}
        </b>
      </span>

      <span className="ml-auto flex items-center gap-6">
        <span>
          AGENT <b className="ml-2" style={{ color: stateColor, letterSpacing: ".18em" }}>
            ▸ {stateLabel}
          </b>
        </span>
        <span className="w-px h-3.5 bg-[color:var(--hairline-2)]" />
        <nav className="flex items-center gap-1">
          <Link
            href="/"
            className={`px-2 py-0.5 text-[10.5px] tracking-[.18em] uppercase border ${pathname === "/" ? "border-[color:var(--signal)] text-[color:var(--signal)]" : "border-transparent text-[color:var(--fg-dim)] hover:text-[color:var(--fg)]"}`}
          >
            Trade
          </Link>
          <Link
            href="/portfolio"
            className={`px-2 py-0.5 text-[10.5px] tracking-[.18em] uppercase border ${pathname === "/portfolio" ? "border-[color:var(--signal)] text-[color:var(--signal)]" : "border-transparent text-[color:var(--fg-dim)] hover:text-[color:var(--fg)]"}`}
          >
            Portfolio
          </Link>
        </nav>
        <span className="w-px h-3.5 bg-[color:var(--hairline-2)]" />
        <span className="hidden sm:inline">NYSE OPEN</span>
        <span className="w-px h-3.5 bg-[color:var(--hairline-2)] hidden sm:inline-block" />
        <span className="hidden lg:inline" style={{ color: "var(--fg-mute)" }}>v0.4.2</span>
      </span>
    </div>
  );
}
