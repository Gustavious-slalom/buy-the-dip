# backend/app/services/news_service.py
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import finnhub
from anthropic import Anthropic
from app.config import settings

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
_anthropic = Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None

def get_news(symbol: str, since_days: int = 7) -> dict:
    if settings.fixtures_mode:
        items = json.loads((FIXTURES / "aapl_news.json").read_text())
        return {"symbol": symbol, "items": items, "summary": ""}
    client = finnhub.Client(api_key=settings.finnhub_api_key)
    today = datetime.now(timezone.utc).date()
    items = client.company_news(symbol, _from=str(today - timedelta(days=since_days)), to=str(today))[:8]
    items = [
        {"headline": i["headline"], "summary": i.get("summary", ""), "url": i["url"], "datetime": i["datetime"]}
        for i in items
    ]
    summary = ""
    if _anthropic and items:
        joined = "\n".join(f"- {i['headline']}: {i['summary'][:200]}" for i in items)
        msg = _anthropic.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=300,
            messages=[{"role": "user", "content": f"Summarize the market-moving themes for {symbol} in 3 bullets:\n{joined}"}],
        )
        summary = msg.content[0].text if msg.content else ""
    return {"symbol": symbol, "items": items, "summary": summary}
