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


@dataclass
class Fundamentals:
    """A company-fundamentals snapshot for the long-term (3-5 year) screen.

    All growth/margin/return fields are percentages (e.g. 18.5 means 18.5%),
    not fractions -- see data_sources/fundamentals.py. Any field can be
    None when yfinance doesn't report it for a given company.
    """

    ticker: str
    current_price: Optional[float] = None
    market_cap: Optional[float] = None
    sector: Optional[str] = None
    trailing_pe: Optional[float] = None
    forward_pe: Optional[float] = None
    peg_ratio: Optional[float] = None
    revenue_growth: Optional[float] = None
    earnings_growth: Optional[float] = None
    gross_margins: Optional[float] = None
    operating_margins: Optional[float] = None
    profit_margins: Optional[float] = None
    return_on_equity: Optional[float] = None
    debt_to_equity: Optional[float] = None
    free_cashflow: Optional[float] = None
    total_debt: Optional[float] = None
    total_cash: Optional[float] = None
    dividend_yield: Optional[float] = None
    recommendation_mean: Optional[float] = None  # 1 (Strong Buy) - 5 (Sell)
    target_mean_price: Optional[float] = None
    beta: Optional[float] = None


@dataclass
class LongTermScoreBreakdown:
    """Final ranked output for one ticker in the long-term screen."""

    ticker: str
    final_score: float
    growth_score: float
    profitability_score: float
    financial_health_score: float
    valuation_score: float
    analyst_score: float
    trend_score: float
    confidence: float
    data_completeness: float
    current_price: float
    market_cap: Optional[float]
    sector: Optional[str]
    revenue_growth_pct: Optional[float]
    earnings_growth_pct: Optional[float]
    peg_ratio: Optional[float]
    forward_pe: Optional[float]
    debt_to_equity: Optional[float]
    analyst_upside_pct: Optional[float]
    risk_flags: List[str]
    rationale: str
