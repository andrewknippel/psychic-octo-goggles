"""Shared data structures passed between pipeline stages."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Mention:
    """A single mention of a ticker pulled from news, Reddit, or StockTwits."""

    ticker: str
    source: str  # "news" | "reddit" | "stocktwits"
    text: str
    timestamp: datetime
    url: str = ""
    engagement: int = 0  # upvotes / likes / comment count, source-dependent
    # StockTwits messages are self-tagged "Bullish"/"Bearish" by the author.
    # When present this is trusted over VADER's text-derived sentiment.
    explicit_sentiment: Optional[str] = None


@dataclass
class PriceSeries:
    """Daily OHLCV bars for a ticker, most-recent last."""

    ticker: str
    dates: list = field(default_factory=list)
    close: list = field(default_factory=list)
    volume: list = field(default_factory=list)


@dataclass
class ScoreBreakdown:
    """Final ranked output for one ticker."""

    ticker: str
    final_score: float
    sentiment_score: float
    momentum_score: float
    buzz_score: float
    technical_score: float
    confidence: float
    mention_count: int
    last_price: float
    change_3d_pct: float
    change_5d_pct: float
    bullish_ratio: Optional[float]
    volume_surge: float
    rsi: Optional[float]
    rationale: str
