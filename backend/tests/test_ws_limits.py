"""Tests verifying WebSocket connection limits and message size guards."""
import asyncio
import pytest


def test_semaphore_limit_is_configured():
    """Session semaphore must be bounded to prevent resource exhaustion."""
    from app.api.ws import MAX_CONCURRENT_SESSIONS, _SESSION_SEMAPHORE
    assert MAX_CONCURRENT_SESSIONS == 5
    assert _SESSION_SEMAPHORE._value == 5


def test_max_message_size_is_configured():
    """Message size cap must exist to prevent memory exhaustion."""
    from app.api.ws import MAX_MESSAGE_BYTES
    assert MAX_MESSAGE_BYTES == 4096
