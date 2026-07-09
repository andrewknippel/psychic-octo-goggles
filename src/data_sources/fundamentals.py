"""Company fundamentals via yfinance (no API key required).

A 3-5 year hold should hinge on the underlying business -- growth,
profitability, balance-sheet health, valuation, analyst coverage -- not
short-term news/social buzz, so this pulls a different slice of yfinance
than market_data.py: the `.info` snapshot instead of daily OHLCV bars.
"""
import logging
from typing import Optional

from src.models import Fundamentals

logger = logging.getLogger(__name__)


def _pct(info: dict, key: str) -> Optional[float]:
    """yfinance reports growth/margin/return fields as fractions (0.18 ==
    18%); convert to a plain percentage for readability and scoring."""
    value = info.get(key)
    return value * 100 if isinstance(value, (int, float)) else None


def fetch_fundamentals(ticker: str) -> Optional[Fundamentals]:
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed; skipping fundamentals for %s", ticker)
        return None

    try:
        info = yf.Ticker(ticker).info
    except Exception as exc:  # yfinance raises assorted exception types
        logger.warning("Fundamentals fetch failed for %s: %s", ticker, exc)
        return None

    current_price = info.get("currentPrice") or info.get("regularMarketPrice")
    if not info or current_price is None:
        return None

    # yfinance has historically been inconsistent about whether dividendYield
    # is a fraction (0.006) or already a percentage (0.58) depending on
    # version -- normalize the common "fraction" case, leave the rest as-is.
    dividend_yield = info.get("dividendYield")
    if isinstance(dividend_yield, (int, float)) and dividend_yield < 1:
        dividend_yield *= 100

    return Fundamentals(
        ticker=ticker,
        current_price=current_price,
        market_cap=info.get("marketCap"),
        sector=info.get("sector"),
        trailing_pe=info.get("trailingPE"),
        forward_pe=info.get("forwardPE"),
        peg_ratio=info.get("pegRatio") or info.get("trailingPegRatio"),
        revenue_growth=_pct(info, "revenueGrowth"),
        earnings_growth=_pct(info, "earningsGrowth"),
        gross_margins=_pct(info, "grossMargins"),
        operating_margins=_pct(info, "operatingMargins"),
        profit_margins=_pct(info, "profitMargins"),
        return_on_equity=_pct(info, "returnOnEquity"),
        debt_to_equity=info.get("debtToEquity"),
        free_cashflow=info.get("freeCashflow"),
        total_debt=info.get("totalDebt"),
        total_cash=info.get("totalCash"),
        dividend_yield=dividend_yield,
        recommendation_mean=info.get("recommendationMean"),
        target_mean_price=info.get("targetMeanPrice"),
        beta=info.get("beta"),
    )
