import json, uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select
from app.db import get_session
from app.models import Proposal, Execution
from app.config import settings
from app.services import alpaca_service

router = APIRouter()

class ApproveBody(BaseModel):
    proposal_id: str

@router.get("/proposals")
def list_proposals():
    with get_session() as s:
        return [p.model_dump() for p in s.exec(select(Proposal).order_by(Proposal.created_at.desc())).all()]

@router.post("/proposals/approve")
def approve(body: ApproveBody):
    with get_session() as s:
        p = s.get(Proposal, body.proposal_id)
        if not p:
            raise HTTPException(404, "not found")
        if p.status != "pending":
            raise HTTPException(409, f"status is {p.status}")
        if p.max_risk > settings.max_risk_usd:
            raise HTTPException(400, "exceeds MAX_RISK_USD")
        legs = json.loads(p.legs_json)
        alpaca_order_id = None
        try:
            order = alpaca_service.submit_multileg_order(legs)
            alpaca_order_id = order["id"]
            p.status = "executed"
            ex = Execution(
                id=str(uuid.uuid4()), proposal_id=p.id,
                alpaca_order_id=alpaca_order_id,
                submitted_at=datetime.now(timezone.utc),
                status=order["status"],
                raw_response_json=order["raw"],
            )
            s.add(p); s.add(ex); s.commit()
            return {"ok": True, "alpaca_order_id": alpaca_order_id, "status": order["status"]}
        except HTTPException:
            raise
        except Exception as e:
            p.status = "failed"
            ex = Execution(
                id=str(uuid.uuid4()), proposal_id=p.id,
                alpaca_order_id=alpaca_order_id,  # preserve ID if order was submitted before DB error
                submitted_at=datetime.now(timezone.utc), status="failed",
                raw_response_json=str(e),
            )
            s.add(p); s.add(ex); s.commit()
            detail = f"execution failed: {e}"
            if alpaca_order_id:
                detail += f" (WARNING: Alpaca order {alpaca_order_id} may be live)"
            raise HTTPException(500, detail)

@router.post("/proposals/reject")
def reject(body: ApproveBody):
    with get_session() as s:
        p = s.get(Proposal, body.proposal_id)
        if not p:
            raise HTTPException(404)
        if p.status != "pending":
            raise HTTPException(409)
        p.status = "rejected"
        s.add(p); s.commit()
    return {"ok": True}
