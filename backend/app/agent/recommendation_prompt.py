"""Per-ticker recommendation prompt. Strict JSON output."""

SYSTEM_PROMPT = (
    "You are an options-trading copilot generating a one-line recommendation for a single ticker "
    "based on recent news + the latest quote. Respond ONLY with a JSON object. No markdown, no "
    "code fences, no commentary. Schema: "
    '{"bias": "bullish"|"bearish"|"neutral", "confidence": float in [0,1], '
    '"rationale": string up to 280 chars, "top_headlines": array of up to 3 strings each '
    "EXACTLY matching one of the provided headlines}."
)


def build_user_message(symbol: str, quote_price: float, news_items: list[dict]) -> str:
    if not news_items:
        headlines_block = "(no recent news available)"
    else:
        headlines_block = "\n".join(
            f"- {i['headline']}: {(i.get('summary') or '')[:200]}"
            for i in news_items[:8]
        )
    return (
        f"Ticker: {symbol}\n"
        f"Latest mid price: {quote_price:.2f}\n\n"
        f"Recent headlines:\n{headlines_block}\n\n"
        "Output ONLY the JSON object as specified."
    )


def build_strict_retry_message() -> str:
    return (
        "Your previous response was not valid JSON. Respond again with ONLY the JSON object. "
        "No markdown, no code fences, no prose. Schema: "
        '{"bias": "bullish"|"bearish"|"neutral", "confidence": number in [0,1], '
        '"rationale": string, "top_headlines": string[]}.'
    )


MARKET_BRIEF_SYSTEM_PROMPT = (
    "You are a market-tone summarizer. Given quotes for SPY/QQQ/IWM and a sample of "
    "market-wide news, produce ONE short headline + 1-3 driver phrases capturing the "
    "current tape. Respond ONLY with a JSON object. No markdown, no code fences, no "
    "commentary. Schema: "
    '{"bias": "bullish"|"bearish"|"neutral", "headline": string up to 100 chars, '
    '"drivers": array of 1..3 short strings each up to 60 chars}.'
)


def build_market_brief_user_message(index_quotes: dict, news_items: list[dict]) -> str:
    quote_lines = []
    for sym in ("SPY", "QQQ", "IWM"):
        v = index_quotes.get(sym)
        if v is None:
            quote_lines.append(f"{sym}: (unavailable)")
        else:
            quote_lines.append(f"{sym}: {float(v):.2f}")
    quotes_block = "\n".join(quote_lines)

    if not news_items:
        news_block = "(no recent news available)"
    else:
        news_block = "\n".join(
            f"- {i['headline']}: {(i.get('summary') or '')[:200]}"
            for i in news_items[:8]
        )

    return (
        f"Index quotes (latest mid):\n{quotes_block}\n\n"
        f"Market-wide headlines:\n{news_block}\n\n"
        "Output ONLY the JSON object as specified."
    )
