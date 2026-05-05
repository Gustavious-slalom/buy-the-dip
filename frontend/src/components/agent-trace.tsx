"use client";
import { useSession } from "@/lib/session-context";

type Group =
  | { kind: "thinking"; ts: string; text: string }
  | { kind: "event"; ts: string; evt: ReturnType<typeof useSession>["events"][number] };

function fmtClock(ts: string) {
  try {
    return new Date(ts).toLocaleTimeString("en-US", { hour12: false });
  } catch {
    return ts;
  }
}

function eventLabel(t: string) {
  return t.replace("agent.", "").replace("_", " ");
}

export function AgentTrace() {
  const { events, status } = useSession();

  const grouped = events.reduce<Group[]>((acc, e) => {
    if (e.type === "agent.thinking") {
      const last = acc[acc.length - 1];
      const delta = (e as { data: { delta?: string } }).data.delta ?? "";
      if (last && last.kind === "thinking") {
        last.text += delta;
      } else {
        acc.push({ kind: "thinking", ts: e.ts, text: delta });
      }
    } else {
      acc.push({ kind: "event", ts: e.ts, evt: e });
    }
    return acc;
  }, []);

  return (
    <section className="px-4 py-5">
      <h3 className="smallcaps panel-rule mb-4">
        Agent Trace
        <span className="normal-case tracking-normal text-[11px] text-[color:var(--fg-mute)] font-mono ml-2">
          {grouped.length} step{grouped.length === 1 ? "" : "s"}
        </span>
      </h3>

      <div className="font-mono text-[12px] leading-[1.55]">
        {grouped.length === 0 && (
          <div className="text-[color:var(--fg-mute)]">awaiting session…</div>
        )}

        {grouped.map((g, i) => {
          const isLast = i === grouped.length - 1;
          const active = isLast && status === "running";

          if (g.kind === "thinking") {
            return (
              <div
                key={i}
                className="my-2 px-3 py-2.5 bg-[color:var(--ink-3)] border border-dashed border-[color:var(--hairline-2)] text-[11.5px] text-[color:var(--fg-dim)] leading-[1.6] whitespace-pre-wrap"
              >
                <span style={{ color: "var(--signal)", letterSpacing: ".18em" }}>
                  THINKING ▸{" "}
                </span>
                {g.text}
                {active && <span className="caret inline-block align-middle ml-0.5" />}
              </div>
            );
          }

          const evt = g.evt;
          const label = eventLabel(evt.type);
          const data = (evt as { data: Record<string, unknown> }).data;
          const summary =
            evt.type === "agent.status"
              ? String((data as { message?: string }).message ?? "")
              : evt.type === "agent.tool_call"
              ? `${(data as { name?: string }).name} (${JSON.stringify(
                  (data as { input?: unknown }).input ?? {}
                ).slice(0, 80)})`
              : evt.type === "agent.tool_result"
              ? `${(data as { name?: string }).name} → ok`
              : evt.type === "agent.complete"
              ? "session complete"
              : evt.type === "agent.error"
              ? `error: ${(data as { message?: string }).message ?? ""}`
              : JSON.stringify(data).slice(0, 120);

          const isError = evt.type === "agent.error";
          const isComplete = evt.type === "agent.complete";

          return (
            <div
              key={i}
              className="grid grid-cols-[auto_auto_1fr] gap-2.5 py-2 border-b border-dashed border-[color:var(--hairline)] items-start"
            >
              <span className="text-[10.5px] text-[color:var(--fg-mute)] pt-[3px] tabular-nums">
                {fmtClock(g.ts)}
              </span>
              <span
                className={
                  "w-3.5 h-3.5 mt-[3px] border " +
                  (active
                    ? "border-[color:var(--signal)] step-active"
                    : isError
                    ? "border-[color:var(--down)] bg-[color:var(--down)]"
                    : isComplete
                    ? "border-[color:var(--signal)] bg-[color:var(--signal)]"
                    : "border-[color:var(--up)] bg-[color:var(--up)]")
                }
                style={{ position: "relative" }}
              >
                {!active && !isError && (
                  <span
                    aria-hidden
                    style={{
                      position: "absolute",
                      left: 3,
                      top: 0,
                      width: 4,
                      height: 8,
                      border: "solid var(--ink)",
                      borderWidth: "0 2px 2px 0",
                      transform: "rotate(45deg)",
                    }}
                  />
                )}
              </span>
              <div>
                <div
                  style={{
                    color: active ? "var(--signal)" : isError ? "var(--down)" : "var(--fg)",
                  }}
                >
                  {label}
                </div>
                <div className="text-[11.5px] text-[color:var(--fg-dim)] mt-0.5 break-all">
                  {summary}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
