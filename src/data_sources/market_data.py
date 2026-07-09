"""Price/volume history via yfinance (no API key required)."""
import logging
from datetime import date, datetime, timezone
from typing import Optional

from src.models import CompanyInfo, PriceSeries

logger = logging.getLogger(__name__)


def fetch_price_series(ticker: str, period: str = "3mo") -> Optional[PriceSeries]:
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed; skipping market data for %s", ticker)
        return None

    try:
        hist = yf.Ticker(ticker).history(period=period, interval="1d")
    except Exception as exc:  # yfinance raises assorted exception types
        logger.warning("Market data fetch failed for %s: %s", ticker, exc)
        return None

    if hist is None or hist.empty or len(hist) < 10:
        return None

    return PriceSeries(
        ticker=ticker,
        dates=[str(d.date()) for d in hist.index],
        close=hist["Close"].tolist(),
        volume=hist["Volume"].tolist(),
    )


def fetch_next_earnings_date(ticker: str) -> Optional[date]:
    """Nearest upcoming earnings date, or None if unknown/already reported.

    Used purely as an event-risk flag -- earnings inside a 2-7 day holding
    window can move a stock far more than any sentiment/momentum signal.
    """
    try:
        import yfinance as yf
    except ImportError:
        return None

    try:
        earnings = yf.Ticker(ticker).get_earnings_dates(limit=8)
    except Exception as exc:
        logger.warning("Earnings date fetch failed for %s: %s", ticker, exc)
        return None

    if earnings is None or earnings.empty:
        return None

    today = datetime.now(timezone.utc).date()
    upcoming = sorted(ts.date() for ts in earnings.index if ts.date() >= today)
    return upcoming[0] if upcoming else None


def fetch_company_info(ticker: str) -> Optional[CompanyInfo]:
    """Fundamentals/company snapshot for the deep-dive report. Best-effort --
    yfinance's `.info` scrape is unofficial and fields are frequently
    missing (ETFs, foreign listings, thinly-covered names), so every field
    is read defensively and the caller must treat None as "unknown", not
    "zero"."""
    try:
        import yfinance as yf
    except ImportError:
        return None

    try:
        info = yf.Ticker(ticker).info
    except Exception as exc:
        logger.warning("Company info fetch failed for %s: %s", ticker, exc)
        return None

    if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
        return None

    return CompanyInfo(
        ticker=ticker,
        name=info.get("longName") or info.get("shortName") or ticker,
        sector=info.get("sector") or "",
        industry=info.get("industry") or "",
        market_cap=info.get("marketCap"),
        trailing_pe=info.get("trailingPE"),
        forward_pe=info.get("forwardPE"),
        dividend_yield=info.get("dividendYield"),
        beta=info.get("beta"),
        target_mean_price=info.get("targetMeanPrice"),
        recommendation_key=info.get("recommendationKey") or "",
        summary=info.get("longBusinessSummary") or "",
    )
