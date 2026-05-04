# Architecture Documentation — Trader Agent

> Diagrams rendered with [Mermaid](https://mermaid.js.org/). All diagrams follow the [C4 model](https://c4model.com/) levels where applicable.

---

## 1. Context Diagram (C4 Level 1)

Who uses the system and what external services does it depend on.

```mermaid
C4Context
    title System Context — Trader Agent

    Person(trader, "Trader", "Views streamed analysis, approves or rejects proposed options trades")

    System(traderagent, "Trader Agent", "Claude-powered options trading copilot. Analyzes tickers, proposes paper trades, executes only after human approval.")

    System_Ext(anthropic, "Anthropic API", "Claude Sonnet 4.5 (agent reasoning + streaming)\nClaude Haiku 4.5 (news summarization)")
    System_Ext(alpaca, "Alpaca Markets (Paper)", "Real-time stock quotes, options chains, Greeks, portfolio data, paper order execution")
    System_Ext(finnhub, "Finnhub", "Company news feed for sentiment analysis")

    Rel(trader, traderagent, "Enters ticker, reads streamed analysis, approves/rejects trade", "Browser / HTTPS+WSS")
    Rel(traderagent, anthropic, "Streams tool-use conversation", "HTTPS / SSE")
    Rel(traderagent, alpaca, "Fetches quotes, chains, portfolio; submits paper orders", "HTTPS REST")
    Rel(traderagent, finnhub, "Fetches company news", "HTTPS REST")
```

---

## 2. Container Diagram (C4 Level 2)

The two runnable processes and their communication.

```mermaid
C4Container
    title Container Diagram — Trader Agent

    Person(trader, "Trader", "Browser")

    Container_Boundary(fe, "Frontend — Next.js 15 App Router") {
        Container(nextjs, "Next.js App", "TypeScript / React 19", "Single-page dashboard. Manages WebSocket lifecycle. Renders streamed events, proposal card, price chart, options chain.")
    }

    Container_Boundary(be, "Backend — FastAPI") {
        Container(api, "HTTP + WebSocket API", "FastAPI / Python 3.11", "Accepts WS session.start and replay messages. Exposes REST: /proposals, /proposals/approve, /proposals/reject, /bars/{symbol}")
        Container(agent, "Claude Agent Loop", "anthropic SDK (async streaming)", "Iterative tool-use loop. Streams thinking deltas. Dispatches tool calls to services. Enforces 12-iteration safety cap.")
        Container(services, "Services", "alpaca-py / finnhub-python / anthropic", "alpaca_service: quotes, chains, portfolio, order submit\nnews_service: news + Haiku summary\nproposal_service: risk/reward math + persistence")
        ContainerDb(db, "SQLite", "SQLModel / SQLite file", "Stores Proposals, Executions, Traces (full session replay), Watchlist")
    }

    Rel(trader, nextjs, "Opens dashboard, sends ticker, approves/rejects", "HTTPS / WSS")
    Rel(nextjs, api, "WebSocket: session.start, replay", "WSS ws://host:8000/ws")
    Rel(nextjs, api, "REST: approve, reject, /bars", "HTTPS JSON")
    Rel(api, agent, "Calls run_session(emit, session_id, user_msg)", "In-process async")
    Rel(agent, services, "Dispatches tool calls via run_in_executor", "In-process / thread pool")
    Rel(services, db, "Reads/writes proposals, traces", "SQLModel ORM")
    Rel(api, db, "Reads traces for replay; writes Execution on approve", "SQLModel ORM")
```

---

## 3. Deployment Diagram

How the system runs locally (hackathon setup) and the network topology.

```mermaid
graph TB
    subgraph developer["Developer machine"]
        subgraph browser["Browser — localhost:3000"]
            UI["Next.js SPA<br/>(React)"]
        end

        subgraph node["Node.js process — pnpm dev"]
            NEXT["Next.js dev server<br/>port 3000"]
        end

        subgraph python["Python venv — uvicorn"]
            FASTAPI["FastAPI app<br/>port 8000<br/>(uvicorn --reload)"]
            SQLITE[("trading.db<br/>SQLite file")]
        end
    end

    subgraph internet["External services (HTTPS)"]
        ANTHROPIC["Anthropic API<br/>api.anthropic.com"]
        ALPACA["Alpaca Paper API<br/>paper-api.alpaca.markets"]
        FINNHUB["Finnhub API<br/>finnhub.io"]
    end

    UI -- "WSS ws://localhost:8000/ws" --> FASTAPI
    UI -- "HTTP localhost:8000" --> FASTAPI
    FASTAPI -- "SQLite r/w" --> SQLITE
    FASTAPI -- "HTTPS streaming" --> ANTHROPIC
    FASTAPI -- "HTTPS REST" --> ALPACA
    FASTAPI -- "HTTPS REST" --> FINNHUB

    style SQLITE fill:#f5f5f5,stroke:#999
    style ANTHROPIC fill:#e8f4fd,stroke:#2196f3
    style ALPACA fill:#e8f4fd,stroke:#2196f3
    style FINNHUB fill:#e8f4fd,stroke:#2196f3
```

**Startup safety check:** FastAPI refuses to boot if `ALPACA_BASE_URL` does not contain `"paper"`.

**Fixtures mode:** Set `FIXTURES_MODE=1` to skip all external HTTP calls. Every service returns canned data from `backend/tests/fixtures/`. Enables fully offline demos.

---

## 4. Backend Micro-Design

Internal module responsibilities and call flow.

```mermaid
graph TD
    subgraph api_layer["API Layer (app/api/)"]
        WS["ws.py<br/>WebSocket router<br/>• session.start → run_session<br/>• replay → re-emit Trace rows"]
        HTTP["http.py<br/>REST router<br/>• GET /proposals<br/>• POST /proposals/approve<br/>• POST /proposals/reject<br/>• GET /bars/{symbol}"]
    end

    subgraph agent_layer["Agent Layer (app/agent/)"]
        LOOP["loop.py<br/>run_session(emit, session_id, user_msg)<br/>• AsyncAnthropic.messages.stream()<br/>• emits agent.thinking deltas<br/>• dispatches tool_use blocks<br/>• safety cap: 12 iterations"]
        TOOLS["tools.py<br/>TOOLS list (no execute_trade!)<br/>dispatch(name, input, session_id)<br/>• wraps all I/O in run_in_executor"]
        PROMPTS["prompts.py<br/>SYSTEM_PROMPT (cached)<br/>6-step workflow instructions"]
    end

    subgraph service_layer["Services (app/services/)"]
        ALPACA_SVC["alpaca_service.py<br/>get_quote · get_options_chain<br/>get_greeks · get_portfolio<br/>get_positions · submit_multileg_order"]
        NEWS_SVC["news_service.py<br/>get_news(symbol)<br/>Finnhub fetch + Haiku summary<br/>(degrades gracefully on error)"]
        PROPOSAL_SVC["proposal_service.py<br/>compute_risk_reward(legs)<br/>create_proposal() → persists + returns dict"]
    end

    subgraph infra["Infrastructure (app/)"]
        CONFIG["config.py<br/>Settings (pydantic-settings)<br/>assert_paper()"]
        DB["db.py<br/>SQLModel engine<br/>init_db() · get_session()"]
        MODELS["models.py<br/>Proposal · Execution<br/>Trace · Watchlist"]
    end

    WS -- "await run_session(emit,...)" --> LOOP
    HTTP -- "alpaca_service.submit_multileg_order()" --> ALPACA_SVC
    HTTP -- "s.get(Proposal,...)" --> DB
    LOOP -- "await dispatch()" --> TOOLS
    LOOP -- "uses" --> PROMPTS
    TOOLS -- "run_in_executor" --> ALPACA_SVC
    TOOLS -- "run_in_executor" --> NEWS_SVC
    TOOLS -- "run_in_executor" --> PROPOSAL_SVC
    PROPOSAL_SVC -- "get_session()" --> DB
    DB --- MODELS
    ALPACA_SVC -- "reads" --> CONFIG
    NEWS_SVC -- "reads" --> CONFIG

    classDef api fill:#fff3e0,stroke:#fb8c00
    classDef agent fill:#e8f5e9,stroke:#43a047
    classDef svc fill:#e3f2fd,stroke:#1e88e5
    classDef infra fill:#f3e5f5,stroke:#8e24aa
    class WS,HTTP api
    class LOOP,TOOLS,PROMPTS agent
    class ALPACA_SVC,NEWS_SVC,PROPOSAL_SVC svc
    class CONFIG,DB,MODELS infra
```

### Agent loop sequence

```mermaid
sequenceDiagram
    participant UI as Next.js
    participant WS as api/ws.py
    participant AgentLoop as agent/loop.py
    participant Tools as agent/tools.py
    participant Claude as Anthropic API
    participant Svc as Services

    UI->>WS: {type: "session.start", data: {ticker}}
    WS->>AgentLoop: run_session(emit, session_id, user_msg)
    AgentLoop->>WS: emit agent.status
    AgentLoop->>Claude: messages.stream(system, tools, messages)
    Claude-->>AgentLoop: text delta stream
    AgentLoop->>WS: emit agent.thinking {delta} (per token)
    Claude-->>AgentLoop: final message (tool_use blocks)
    AgentLoop->>WS: emit agent.tool_call {name, input}
    AgentLoop->>Tools: await dispatch(name, input)
    Tools->>Svc: run_in_executor(service_fn)
    Svc-->>Tools: result dict
    Tools-->>AgentLoop: result dict
    AgentLoop->>WS: emit agent.tool_result {output}
    Note over AgentLoop: if name == "propose_trade"
    AgentLoop->>WS: emit agent.proposal {legs, risk, reward, ...}
    AgentLoop->>Claude: next turn with tool_results
    Claude-->>AgentLoop: stop_reason = end_turn
    AgentLoop->>WS: emit agent.complete

    UI->>WS: {type: "proposal.approve", data: {proposal_id}}
    WS->>WS: POST /proposals/approve (HTTP)
    WS->>Svc: alpaca_service.submit_multileg_order(legs)
    Svc-->>WS: {id, status}
    WS->>UI: execution.result toast
```

---

## 5. Frontend Micro-Design

Component tree, state ownership, and data flow.

```mermaid
graph TD
    subgraph layout["app/layout.tsx"]
        SP["SessionProvider<br/>(lib/session-context.tsx)<br/>single instance of useAgentSession()"]
    end

    subgraph hook["lib/ws.ts — useAgentSession()"]
        WS_REF["ws: useRef&lt;WebSocket&gt;<br/>single connection lifecycle"]
        STATE["events: AgentEvent[]<br/>proposal: Proposal | null<br/>status: idle|running|done|error<br/>lastSessionId: useRef&lt;string&gt;"]
        ACTIONS["sendIdea(ticker, idea?)<br/>→ session.start message<br/><br/>sendReplay(sid?)<br/>→ replay message"]
    end

    subgraph components["src/components/"]
        TI["TickerInput<br/>• Input + Analyze button<br/>• Replay last button<br/>reads: status<br/>calls: sendIdea, sendReplay"]
        AT["AgentTrace<br/>• Collapses thinking deltas<br/>  into growing paragraph<br/>reads: events[]"]
        PC["ProposalCard<br/>• Shows when proposal != null<br/>• Approve → POST /proposals/approve<br/>• Reject → POST /proposals/reject<br/>reads: proposal"]
        PP["PortfolioPanel<br/>• Visible after get_portfolio result<br/>reads: events[] (last tool_result)"]
        CHART["PriceChart<br/>• Fetches GET /bars/{symbol}<br/>  when first get_quote call seen<br/>reads: events[]"]
        OCT["OptionsChainTable<br/>• Shows last get_options_chain result<br/>reads: events[]"]
    end

    subgraph rest["lib/api.ts"]
        APPROVE["approveProposal(id)"]
        REJECT["rejectProposal(id)"]
    end

    subgraph types["src/types/events.ts"]
        TYPES["AgentEvent union type<br/>Proposal type"]
    end

    SP --> hook
    SP --> components

    WS_REF --> STATE
    STATE --> ACTIONS

    TI -- "useSession()" --> SP
    AT -- "useSession()" --> SP
    PC -- "useSession()" --> SP
    PP -- "useSession()" --> SP
    CHART -- "useSession()" --> SP
    OCT -- "useSession()" --> SP

    PC --> APPROVE
    PC --> REJECT

    hook --- TYPES
    components --- TYPES
```

### Page layout (3-column desktop)

```mermaid
graph LR
    subgraph page["app/page.tsx — 3-column grid"]
        subgraph left["Left 320px"]
            TI2["TickerInput"]
            PP2["PortfolioPanel"]
        end
        subgraph center["Center flex"]
            PC2["ProposalCard (sticky)"]
            CHART2["PriceChart"]
            OCT2["OptionsChainTable"]
        end
        subgraph right["Right 380px"]
            AT2["AgentTrace (scrollable)"]
        end
    end
```

### WebSocket event flow (frontend perspective)

```mermaid
stateDiagram-v2
    [*] --> idle: WebSocket onopen
    idle --> running: sendIdea() or sendReplay()
    running --> running: agent.status / agent.thinking / agent.tool_call / agent.tool_result
    running --> running: agent.proposal → proposal state set
    running --> done: agent.complete
    running --> error: agent.error
    done --> running: sendIdea() (new analysis)
    error --> running: sendIdea() (retry)
```

---

## Event Schema Reference

```mermaid
classDiagram
    class AgentEvent {
        +type: string
        +ts: string ISO8601
        +session_id: string UUID
        +data: object
    }
    class Proposal {
        +proposal_id: string UUID
        +ticker: string
        +legs: Leg[]
        +max_risk: number
        +max_reward: number | null
        +breakeven: number | null
        +expiry: string YYYY-MM-DD
        +rationale: string
        +confidence: number 0-1
        +risks: string[]
    }
    class Leg {
        +action: buy | sell
        +side: call | put
        +qty: number
        +strike: number
        +premium: number
        +contract_symbol: string OCC
    }
    AgentEvent --> Proposal : data (when type=agent.proposal)
    Proposal --> Leg : legs[]
```

---

*Generated from source — last updated with commit `8f9b1b4`.*
