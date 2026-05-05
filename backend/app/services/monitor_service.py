import asyncio
import logging
from app.services import alpaca_service, sell_service
from app.services.portfolio_service import OCC_MIN_LEN

log = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 15


async def check_thresholds_once() -> list[dict]:
    """Single evaluation pass. Returns list of triggered sells (for testing)."""
    triggered: list[dict] = []
    rules = sell_service.list_rules()
    if not rules:
        return triggered

    # Only stock positions — skip OCC option symbols (len >= OCC_MIN_LEN)
    stock_rules = [r for r in rules if len(r.symbol) < OCC_MIN_LEN]
    if not stock_rules:
        return triggered

    positions = alpaca_service.get_positions()
    pos_by_sym = {p["symbol"]: p for p in positions}

    symbols = [r.symbol for r in stock_rules if r.symbol in pos_by_sym]
    if not symbols:
        return triggered

    prices = alpaca_service.get_latest_prices(symbols)

    for rule in stock_rules:
        pos = pos_by_sym.get(rule.symbol)
        price = prices.get(rule.symbol)
        if not pos or price is None:
            continue

        avg_entry = float(pos["avg_entry_price"])
        if avg_entry == 0:
            continue

        pct_change = (price - avg_entry) / avg_entry
        qty = rule.qty if rule.qty is not None else float(pos["qty"])

        if pct_change >= rule.take_profit:
            log.info("take_profit triggered %s pct=%.4f", rule.symbol, pct_change)
            result = sell_service.sell_position(
                rule.symbol, qty, avg_entry,
                trigger="take_profit",
                trigger_price=price,
            )
            # Deactivate rule after firing to prevent double-sell
            sell_service.delete_rule(rule.symbol)
            triggered.append(result)
        elif pct_change <= rule.stop_loss:
            log.info("stop_loss triggered %s pct=%.4f", rule.symbol, pct_change)
            result = sell_service.sell_position(
                rule.symbol, qty, avg_entry,
                trigger="stop_loss",
                trigger_price=price,
            )
            # Deactivate rule after firing to prevent double-sell
            sell_service.delete_rule(rule.symbol)
            triggered.append(result)

    return triggered


async def run_monitor() -> None:
    """Infinite polling loop — called from FastAPI lifespan."""
    while True:
        try:
            await check_thresholds_once()
        except Exception as e:
            log.warning("monitor error: %s", e)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
