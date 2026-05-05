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
