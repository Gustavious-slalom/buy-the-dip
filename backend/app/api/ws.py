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
            evt["session_id"] = session_id
            await ws.send_text(json.dumps(evt))
            with get_session() as s:
                s.add(Trace(session_id=session_id, ts=datetime.now(timezone.utc),
                            event_type=evt["type"], payload_json=json.dumps(evt)))
                s.commit()
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)
            if data.get("type") == "session.start":
                user_msg = data["data"].get("idea") or f"analyze {data['data'].get('ticker')}"
                await run_session(emit, session_id, user_msg)
            elif data.get("type") == "replay":
                from sqlmodel import select
                sid = data["data"]["session_id"]
                import asyncio
                with get_session() as s:
                    rows = s.exec(select(Trace).where(Trace.session_id == sid).order_by(Trace.ts)).all()
                for r in rows:
                    await ws.send_text(r.payload_json)
                    await asyncio.sleep(0.4)
    except WebSocketDisconnect:
        return
