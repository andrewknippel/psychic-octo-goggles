"""Same-day "most active" screen.

IMPORTANT: this is NOT a same-day round-trip prediction. Genuine intraday
trading signals need real-time, minute-by-minute price/volume data and
live order flow -- this tool only has daily bars (refreshed at most every
few minutes while --interval polls) and news/social data, so it cannot
tell you whether a stock will keep moving favorably before the closing
bell. What it CAN do, honestly, is surface which tickers are showing an
unusually large price move *today* (or as of the most recent available
bar) on unusually high volume -- the unusual-activity signal, not a
direction guarantee. Buying and selling the same day is high-risk
speculation regardless of what this list says.

Note on timing: if run while the market is open, the "latest" daily bar
from the data source is typically still-forming, so change_1d_pct reflects
today's move so far, not a finished day. If run after close/before open,
it reflects the most recently completed session.
"""
from dataclasses import dataclass, field
from typing import List, Optional

import config
from src.analysis.technical import TechnicalSnapshot
from src.models import PriceSeries


@dataclass
class DayMover:
    ticker: str
    last_price: float
    change_1d_pct: float
    volume_surge: float
    rsi: Optional[float]
    reasons: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return f"{self.ticker} {self.change_1d_pct:+.1f}% today -- " + "; ".join(self.reasons)


def find_day_mover(ticker: str, price_series: Optional[PriceSeries]) -> Optional[DayMover]:
    if price_series is None:
        return None
    tech = TechnicalSnapshot(price_series)

    if tech.last_price < config.MIN_PRICE:
        return None
    if tech.avg_volume_20 and tech.avg_volume_20 < config.MIN_AVG_VOLUME:
        return None
    if tech.change_1d_pct is None or tech.change_1d_pct < config.DAY_MOVER_MIN_CHANGE_PCT:
        return None  # not up enough today to be a "mover"
    if tech.volume_surge < config.DAY_MOVER_MIN_VOLUME_SURGE:
        return None  # up, but not on unusual volume -- less likely to be a real catalyst

    reasons = [
        f"volume {tech.volume_surge:.1f}x its 20-day average",
    ]
    if tech.rsi is not None:
        reasons.append(f"RSI {tech.rsi:.0f}")

    return DayMover(
        ticker=ticker,
        last_price=round(tech.last_price, 2),
        change_1d_pct=round(tech.change_1d_pct, 2),
        volume_surge=round(tech.volume_surge, 2),
        rsi=round(tech.rsi, 1) if tech.rsi is not None else None,
        reasons=reasons,
    )


def scan_for_day_movers(ticker_data) -> List[DayMover]:
    """ticker_data: iterable of rows starting with (ticker, ..., price_series, ...)
    -- accepts the same raw_data rows used by the dip scanner (4- or
    5-element tuples), since only the ticker and price_series are used."""
    movers = []
    for row in ticker_data:
        ticker, price_series = row[0], row[3]
        mover = find_day_mover(ticker, price_series)
        if mover is not None:
            movers.append(mover)
    return movers


def rank_day_movers(movers: List[DayMover]) -> List[DayMover]:
    """Biggest same-day gain first."""
    return sorted(movers, key=lambda m: m.change_1d_pct, reverse=True)
