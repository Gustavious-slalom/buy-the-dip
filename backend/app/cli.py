# backend/app/cli.py
import asyncio, json, sys
from app.agent.loop import run_session
from app.db import init_db

async def main(prompt: str):
    init_db()
    async def emit(evt): print(json.dumps(evt, default=str))
    await run_session(emit, "cli-session", prompt)

if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or "analyze AAPL"))
