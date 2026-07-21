"""Buy alerts: the strict, actionable subset of dip candidates the
phone/computer app surfaces with a one-tap "Buy in Fidelity" button.

The rebound scan (`dip_scanner.py`) is intentionally permissive -- it flags a
sharp dip that shows EITHER an oversold RSI OR a merely decelerating decline,
so it can catch setups early. A *buy alert* is the stricter thing the user
actually asked to be told about: a stock that has both

  1. dropped at least `BUY_ALERT_DROP_PCT` over the past week (5 trading days),
     and
  2. a low RSI (at/below `BUY_ALERT_RSI_MAX`)

at the same time. Everything here is still an automated screen, NOT investment
advice and NOT a prediction -- an oversold stock can keep falling (a "falling
knife"). The app never places or authorizes a trade: the Fidelity link opens a
pre-filled order ticket that the user reviews and submits themselves.
"""
from dataclasses import dataclass
from typing import List, Optional

import config
from src.analysis.dip_scanner import DipCandidate


def fidelity_buy_url(ticker: str) -> str:
    """Deep link to Fidelity's order-entry ticket, pre-filled to BUY `ticker`.

    Opening it requires the user to be logged in to Fidelity; they review and
    submit the order themselves. Nothing here authorizes or places a trade.
    """
    return config.FIDELITY_TRADE_URL.format(ticker=ticker.upper())


@dataclass
class BuyAlert:
    ticker: str
    last_price: float
    change_5d_pct: float          # one-week (5 trading day) return, negative
    change_3d_pct: float
    rsi: float                    # always present for a buy alert (see below)
    sentiment_score: float
    earnings_date: Optional[str]  # ISO date if inside the risk window, else None
    reasons: List[str]

    @property
    def fidelity_url(self) -> str:
        return fidelity_buy_url(self.ticker)

    @property
    def action(self) -> str:
        return (
            f"{self.ticker}: down {self.change_5d_pct:.1f}% this week with RSI "
            f"{self.rsi:.0f} (low). Review a buy on Fidelity."
        )


def is_buy_alert(candidate: DipCandidate) -> bool:
    """True when a dip candidate meets BOTH the weekly-drop and low-RSI bars.

    The dip scanner already enforces the drop threshold, but we re-check it
    here against the buy-alert threshold so the two can be tuned independently
    (e.g. a stricter -12% for alerts while the rebound list stays at -8%).
    """
    if candidate.rsi is None:
        return False
    if candidate.rsi > config.BUY_ALERT_RSI_MAX:
        return False
    if candidate.change_5d_pct > -config.BUY_ALERT_DROP_PCT:
        return False
    return True


def _to_alert(c: DipCandidate) -> BuyAlert:
    return BuyAlert(
        ticker=c.ticker,
        last_price=c.last_price,
        change_5d_pct=c.change_5d_pct,
        change_3d_pct=c.change_3d_pct,
        rsi=c.rsi,  # is_buy_alert guarantees this is not None
        sentiment_score=c.sentiment_score,
        earnings_date=c.earnings_date,
        reasons=list(c.reasons),
    )


def select_buy_alerts(candidates: List[DipCandidate]) -> List[BuyAlert]:
    """Filter dip candidates down to actionable buy alerts, most-oversold
    (lowest RSI) first."""
    alerts = [_to_alert(c) for c in candidates if is_buy_alert(c)]
    alerts.sort(key=lambda a: a.rsi)
    return alerts
