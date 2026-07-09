"""Shared data structures passed between pipeline stages."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


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
class CompanyInfo:
    """Fundamentals/company snapshot for the single-ticker deep-dive report."""

    ticker: str
    name: str = ""
    sector: str = ""
    industry: str = ""
    market_cap: Optional[float] = None
    trailing_pe: Optional[float] = None
    forward_pe: Optional[float] = None
    dividend_yield: Optional[float] = None
    beta: Optional[float] = None
    target_mean_price: Optional[float] = None
    recommendation_key: str = ""
    summary: str = ""


@dataclass
class Recommendation:
    """Rule-based buy/hold/sell verdict for the single-ticker deep-dive report."""

    ticker: str
    action: str  # "BUY MORE" | "HOLD" | "TRIM" | "SELL"
    overall_score: float
    trend_score: float
    sentiment_score: Optional[float]
    reasons: List[str]
    risk_flags: List[str]
    stop_loss: Optional[float]
    stop_loss_pct: Optional[float]
    take_profit: Optional[float]
    take_profit_pct: Optional[float]
    take_profit_basis: str
    hold_horizon: str
    hold_horizon_reason: str


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
    volatility_pct: Optional[float]
    earnings_date: Optional[str]  # ISO date string, None if unknown/not upcoming
    risk_flags: List[str]
    rationale: str
