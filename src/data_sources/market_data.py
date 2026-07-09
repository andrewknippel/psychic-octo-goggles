"""Price/volume history via yfinance (no API key required)."""
import logging
from typing import Optional

from src.models import PriceSeries

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
