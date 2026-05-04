# backend/app/services/news_service.py
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import finnhub
from anthropic import AnthropicBedrock
from app.config import settings

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
# AWS_BEARER_TOKEN_BEDROCK is read automatically from the environment by the SDK
_anthropic = AnthropicBedrock(aws_region=settings.aws_region)

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
