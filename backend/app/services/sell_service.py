import uuid
from datetime import datetime, timezone
from sqlmodel import select
from app.db import get_session
from app.models import SellOrder, SellRule
from app.services import alpaca_service


def sell_position(
    symbol: str,
    qty: float,
    avg_entry: float,
    trigger: str = "manual",
    trigger_price: float | None = None,
) -> dict:
    """Execute a market sell and persist a SellOrder record."""
    order = alpaca_service.sell_stock_position(symbol, qty)
    record_id = str(uuid.uuid4())
    record = SellOrder(
        id=record_id,
        symbol=symbol,
        qty=qty,
        trigger=trigger,
        avg_entry=avg_entry,
        trigger_price=trigger_price,
        alpaca_order_id=order["id"],
        status=order["status"],
        raw_response_json=order["raw"],
    )
    with get_session() as s:
        s.add(record)
        s.commit()
    return {
        "ok": True,
        "sell_order_id": record_id,
        "alpaca_order_id": order["id"],
        "status": order["status"],
    }


def set_rule(
    symbol: str,
    take_profit: float,
    stop_loss: float,
    qty: float | None = None,
) -> SellRule:
    """Upsert a SellRule for the given symbol."""
    with get_session() as s:
        rule = s.get(SellRule, symbol)
        if rule:
            rule.take_profit = take_profit
            rule.stop_loss = stop_loss
            rule.qty = qty
            rule.active = True
            rule.updated_at = datetime.now(timezone.utc)
        else:
            rule = SellRule(
                symbol=symbol,
                take_profit=take_profit,
                stop_loss=stop_loss,
                qty=qty,
            )
        s.add(rule)
        s.commit()
        s.refresh(rule)
        return rule


def delete_rule(symbol: str) -> None:
    """Deactivate the rule for the given symbol (soft delete)."""
    with get_session() as s:
        rule = s.get(SellRule, symbol)
        if rule:
            rule.active = False
            s.add(rule)
            s.commit()


def list_rules() -> list[SellRule]:
    """Return all active sell rules."""
    with get_session() as s:
        return list(s.exec(select(SellRule).where(SellRule.active == True)).all())  # noqa: E712
