# backend/app/services/news_service.py
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import finnhub
from anthropic import Anthropic
from app.config import settings

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
_anthropic = Anthropic(api_key=settings.anthropic_api_key)

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
    if items:
        joined = "\n".join(f"- {i['headline']}: {i['summary'][:200]}" for i in items)
        try:
            msg = _anthropic.messages.create(
                model=settings.anthropic_haiku_model, max_tokens=300,
                messages=[{"role": "user", "content": f"Summarize the market-moving themes for {symbol} in 3 bullets:\n{joined}"}],
            )
            summary = msg.content[0].text if msg.content else ""
        except Exception:
            pass  # degrade gracefully — agent still gets raw news items
    return {"symbol": symbol, "items": items, "summary": summary}

def get_general_news() -> list[dict]:
    """Market-wide news. Returns up to 30 items with {headline, summary, url, datetime, related}."""
    if settings.fixtures_mode:
        return json.loads((FIXTURES / "general_news.json").read_text())
    client = finnhub.Client(api_key=settings.finnhub_api_key)
    raw = client.general_news("general")[:30]
    return [
        {
            "headline": i["headline"],
            "summary": i.get("summary", ""),
            "url": i["url"],
            "datetime": i["datetime"],
            "related": i.get("related", ""),
        }
        for i in raw
    ]
