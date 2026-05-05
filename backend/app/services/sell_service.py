import uuid
from datetime import datetime, timezone
from sqlmodel import select
from app.db import get_session
from app.models import SellOrder, SellRule
from app.services import alpaca_service
from app.services.portfolio_service import OCC_MIN_LEN


class SellValidationError(ValueError):
    """Raised when a sell request fails server-side validation."""


def _validate_stock_sell(symbol: str, qty: float) -> dict:
    """Validate that `symbol` is a currently-held stock position with sufficient qty.

    Returns the broker position dict on success.
    Raises SellValidationError on any validation failure.
    """
    if len(symbol) >= OCC_MIN_LEN:
        raise SellValidationError(
            f"{symbol} is an option contract and cannot be sold via this endpoint"
        )
    if qty <= 0:
        raise SellValidationError("qty must be positive")
    positions = alpaca_service.get_positions()
    pos_by_sym = {p["symbol"]: p for p in positions}
    pos = pos_by_sym.get(symbol)
    if pos is None:
        raise SellValidationError(f"no open position for {symbol}")
    held = float(pos["qty"])
    if held <= 0:
        raise SellValidationError(
            f"position for {symbol} is not long (qty={held})"
        )
    if qty > held:
        raise SellValidationError(
            f"qty {qty} exceeds held position {held} for {symbol}"
        )
    return pos


def sell_position(
    symbol: str,
    qty: float,
    avg_entry: float,
    trigger: str = "manual",
    trigger_price: float | None = None,
) -> dict:
    """Execute a market sell and persist a SellOrder record.

    For manual triggers, the caller must have already validated the position
    and derived avg_entry from broker data (see http.py).
    """
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
    """Upsert a SellRule for the given symbol.

    Validation (take_profit > 0, stop_loss < 0, qty > 0) is enforced at the
    HTTP layer via Pydantic; this function trusts its inputs.
    """
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


def try_deactivate_rule(symbol: str) -> bool:
    """Atomically deactivate the rule if it is currently active.

    Returns True if this call deactivated it; False if it was already inactive
    (e.g. claimed by another worker). Used by the monitor to prevent duplicate
    broker submissions.
    """
    with get_session() as s:
        rule = s.exec(
            select(SellRule)
            .where(SellRule.symbol == symbol)
            .where(SellRule.active == True)  # noqa: E712
        ).first()
        if rule is None:
            return False
        rule.active = False
        s.add(rule)
        s.commit()
        return True


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
