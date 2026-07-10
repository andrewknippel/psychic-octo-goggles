"""Detects tickers that have dropped sharply but show early signs of
stabilizing -- a mean-reversion ("buy the dip") setup, as distinct from
`scoring.py`'s main scorer, which favors names already trending *up*.

IMPORTANT: this flags *candidates worth a closer look*, not predictions.
A sharp drop can just as easily keep falling (a "falling knife") as bounce,
and there is no way for this -- or any other tool -- to guarantee a bounce
happens within any specific window. "Rebound within ~4 weeks" describes
the horizon this kind of oversold-bounce setup is typically evaluated
over, not a promise of what will happen. The sentiment filter below exists
specifically to weed out drops driven by genuinely bad, ongoing news, and
the earnings check flags a real risk that could blow through that window
-- but both are heuristics, not guarantees.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import List, Optional

import config
from src.analysis.sentiment import compute_sentiment_score
from src.analysis.technical import TechnicalSnapshot
from src.models import Mention, PriceSeries


@dataclass
class DipCandidate:
    ticker: str
    last_price: float
    change_3d_pct: float
    change_5d_pct: float
    rsi: Optional[float]
    sentiment_score: float
    earnings_date: Optional[str] = None  # ISO date string, None if unknown/not upcoming
    reasons: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return f"{self.ticker} {self.change_5d_pct:+.1f}% (5d) -- " + "; ".join(self.reasons)


def find_dip_candidate(
    ticker: str,
    news_mentions: List[Mention],
    social_mentions: List[Mention],
    price_series: Optional[PriceSeries],
    now: Optional[datetime] = None,
    earnings_date: Optional[date] = None,
) -> Optional[DipCandidate]:
    if price_series is None:
        return None
    now = now or datetime.now(timezone.utc)
    tech = TechnicalSnapshot(price_series)

    if tech.last_price < config.MIN_PRICE:
        return None
    if tech.avg_volume_20 and tech.avg_volume_20 < config.MIN_AVG_VOLUME:
        return None
    if tech.change_5d_pct is None or tech.change_5d_pct > -config.DIP_DROP_PCT:
        return None  # hasn't dropped enough to qualify as a "big dip"

    sentiment_score = compute_sentiment_score(news_mentions, social_mentions, now)
    if sentiment_score < config.DIP_MIN_SENTIMENT:
        return None  # sentiment is actively bearish -- more likely a falling knife

    oversold = tech.rsi is not None and tech.rsi <= config.DIP_RSI_OVERSOLD
    stabilizing = (
        tech.change_3d_pct is not None and tech.change_3d_pct > tech.change_5d_pct
    )
    if not (oversold or stabilizing):
        return None  # still falling with no sign yet of leveling off

    reasons = [f"down {tech.change_5d_pct:.1f}% over 5 days"]
    if oversold:
        reasons.append(f"RSI oversold at {tech.rsi:.0f}")
    if stabilizing:
        reasons.append("decline decelerating over the last 3 days")
    reasons.append(f"sentiment not panicking ({sentiment_score:.0f}/100)")

    days_to_earnings = None
    if earnings_date is not None:
        days_to_earnings = (earnings_date - now.date()).days
        if 0 <= days_to_earnings <= config.DIP_EARNINGS_WINDOW_DAYS:
            reasons.append(
                f"earnings in {days_to_earnings}d ({earnings_date.isoformat()}) -- "
                "added event risk inside the rebound window"
            )
        else:
            days_to_earnings = None  # outside the window: not relevant, don't report it

    return DipCandidate(
        ticker=ticker,
        last_price=round(tech.last_price, 2),
        change_3d_pct=round(tech.change_3d_pct, 2) if tech.change_3d_pct is not None else 0.0,
        change_5d_pct=round(tech.change_5d_pct, 2),
        rsi=round(tech.rsi, 1) if tech.rsi is not None else None,
        sentiment_score=round(sentiment_score, 2),
        earnings_date=earnings_date.isoformat() if days_to_earnings is not None else None,
        reasons=reasons,
    )


def scan_for_dips(ticker_data) -> List[DipCandidate]:
    """ticker_data: iterable of (ticker, news_mentions, social_mentions,
    price_series, earnings_date) -- earnings_date may be omitted/None."""
    candidates = []
    for row in ticker_data:
        if len(row) == 5:
            ticker, news_mentions, social_mentions, price_series, earnings_date = row
        else:
            ticker, news_mentions, social_mentions, price_series = row
            earnings_date = None
        candidate = find_dip_candidate(
            ticker, news_mentions, social_mentions, price_series, earnings_date=earnings_date
        )
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def rank_dip_candidates(candidates: List[DipCandidate]) -> List[DipCandidate]:
    """Most-oversold (lowest RSI) first -- the clearest, most directly
    "low RSI" signal of how stretched a candidate is. Candidates with no
    RSI (too little price history) sort last, not excluded."""
    return sorted(candidates, key=lambda c: c.rsi if c.rsi is not None else 999.0)
