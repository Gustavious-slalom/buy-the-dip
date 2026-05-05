import asyncio
import json, uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.agent.loop import run_session
from app.db import get_session
from app.models import Trace
from datetime import datetime, timezone

router = APIRouter()

MAX_CONCURRENT_SESSIONS = 5
MAX_MESSAGE_BYTES = 4096
_SESSION_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_SESSIONS)

@router.websocket("/ws")
async def ws(ws: WebSocket):
    await ws.accept()
    if _SESSION_SEMAPHORE.locked() and _SESSION_SEMAPHORE._value == 0:
        await ws.send_text(json.dumps({"type": "error", "data": {"message": "server busy, try again shortly"}}))
        await ws.close()
        return
    async with _SESSION_SEMAPHORE:
        session_id = str(uuid.uuid4())
        try:
            async def emit(evt: dict):
                # Write to DB first so replay is consistent with what clients receive.
                # If the DB write fails, the event is never sent — preventing ghost events.
                evt["session_id"] = session_id
                with get_session() as s:
                    s.add(Trace(session_id=session_id, ts=datetime.now(timezone.utc),
                                event_type=evt["type"], payload_json=json.dumps(evt)))
                    s.commit()
                await ws.send_text(json.dumps(evt))
            while True:
                msg = await ws.receive_text()
                if len(msg.encode()) > MAX_MESSAGE_BYTES:
                    await ws.send_text(json.dumps({"type": "error", "data": {"message": "message too large"}}))
                    continue
                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    await ws.send_text(json.dumps({"type": "error", "data": {"message": "invalid JSON"}}))
                    continue
                if data.get("type") == "session.start":
                    try:
                        user_msg = data["data"].get("idea") or f"analyze {data['data'].get('ticker', '')}"
                    except (KeyError, TypeError):
                        await ws.send_text(json.dumps({"type": "error", "data": {"message": "missing data field"}}))
                        continue
                    try:
                        await run_session(emit, session_id, user_msg)
                    except Exception as e:
                        await ws.send_text(json.dumps({"type": "agent.error", "data": {"message": str(e)}}))
                elif data.get("type") == "replay":
                    from sqlmodel import select
                    try:
                        sid = data["data"]["session_id"]
                    except (KeyError, TypeError):
                        await ws.send_text(json.dumps({"type": "error", "data": {"message": "missing session_id"}}))
                        continue
                    with get_session() as s:
                        rows = s.exec(select(Trace).where(Trace.session_id == sid).order_by(Trace.ts)).all()
                    for r in rows:
                        await ws.send_text(r.payload_json)
                        await asyncio.sleep(0.4)
        except WebSocketDisconnect:
            return
