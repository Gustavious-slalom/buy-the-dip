import pytest


def test_build_user_message_lists_headlines_and_quote():
    from app.agent.recommendation_prompt import build_user_message
    msg = build_user_message(
        symbol="NVDA",
        quote_price=920.50,
        news_items=[
            {"headline": "NVDA beats Q3", "summary": "Record numbers."},
            {"headline": "Wall St raises target", "summary": "$1,250."},
        ],
    )
    assert "NVDA" in msg
    assert "920.50" in msg
    assert "NVDA beats Q3" in msg
    assert "Wall St raises target" in msg
    assert "JSON" in msg


def test_strict_retry_message_explicit():
    from app.agent.recommendation_prompt import build_strict_retry_message
    msg = build_strict_retry_message()
    assert "JSON" in msg
    assert "no markdown" in msg.lower() or "no fences" in msg.lower() or "no code block" in msg.lower()
