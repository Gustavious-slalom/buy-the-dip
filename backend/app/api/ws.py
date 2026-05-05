import json, uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.agent.loop import run_session
from app.db import get_session
from app.models import Trace
from datetime import datetime, timezone

router = APIRouter()

@router.websocket("/ws")
async def ws(ws: WebSocket):
    await ws.accept()
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
                import asyncio
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
