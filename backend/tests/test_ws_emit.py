"""Tests verifying the WebSocket emit ordering invariant."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_emit_db_failure_prevents_ws_send():
    """If DB write fails, the WS send must NOT have occurred (DB first invariant).

    With the buggy ordering (send → DB write), a DB failure still delivers the
    event to the client, creating ghost events that never appear in replay.
    With the correct ordering (DB write → send), a DB failure raises before send.
    """
    sent_events = []
    mock_ws = AsyncMock()
    mock_ws.send_text = AsyncMock(side_effect=lambda data: sent_events.append(data))

    session_id = "test-ordering"

    failing_ctx = MagicMock()
    failing_ctx.__enter__ = MagicMock(return_value=MagicMock(
        add=MagicMock(),
        commit=MagicMock(side_effect=RuntimeError("DB unavailable")),
    ))
    failing_ctx.__exit__ = MagicMock(return_value=False)

    from datetime import datetime, timezone
    from app.models import Trace

    async def emit_correct_order(evt: dict):
        """Correct ordering: DB write first, then WS send."""
        evt["session_id"] = session_id
        with failing_ctx as s:
            s.add(Trace(session_id=session_id, ts=datetime.now(timezone.utc),
                        event_type=evt["type"], payload_json=json.dumps(evt)))
            s.commit()  # raises RuntimeError
        await mock_ws.send_text(json.dumps(evt))

    with pytest.raises(RuntimeError, match="DB unavailable"):
        await emit_correct_order({"type": "agent.thinking", "data": {"text": "test"}})

    assert len(sent_events) == 0, (
        "Event was sent to WebSocket client despite DB failure — "
        "this creates ghost events that never appear in replay"
    )


@pytest.mark.asyncio
async def test_emit_success_stores_and_sends():
    """Happy path: event is stored in DB and sent over WS."""
    from sqlmodel import create_engine, Session, SQLModel, select
    from app.models import Trace
    from datetime import datetime, timezone

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    sent_events = []
    mock_ws = AsyncMock()
    mock_ws.send_text = AsyncMock(side_effect=lambda data: sent_events.append(json.loads(data)))

    session_id = "test-happy"

    async def emit(evt: dict):
        evt["session_id"] = session_id
        with Session(engine) as s:
            s.add(Trace(session_id=session_id, ts=datetime.now(timezone.utc),
                        event_type=evt["type"], payload_json=json.dumps(evt)))
            s.commit()
        await mock_ws.send_text(json.dumps(evt))

    await emit({"type": "agent.thinking", "data": {"text": "analyzing..."}})

    assert len(sent_events) == 1
    with Session(engine) as s:
        traces = s.exec(select(Trace).where(Trace.session_id == session_id)).all()
    assert len(traces) == 1
    assert traces[0].event_type == "agent.thinking"
