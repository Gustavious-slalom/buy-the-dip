from app.db import init_db, get_session
from app.models import Watchlist
init_db()
with get_session() as s:
    for t in ["AAPL", "NVDA", "SPY"]:
        s.merge(Watchlist(ticker=t))
    s.commit()
print("seeded")
