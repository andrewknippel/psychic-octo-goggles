"""Synthetic offline dataset for the long-term screener (see sample_data.py
for the short-term equivalent). No network required.

Archetypes:
  * COMPOUND - quality compounder: strong growth+margins+ROE, low debt,
               reasonable valuation, bullish analyst coverage -- should
               rank #1.
  * VALUE    - modest growth, cheap-ish valuation, low debt, steady
               long-run uptrend -- solid but unexciting, mid-table.
  * HYPE     - fast revenue growth but unprofitable, richly valued, and
               already extended -- carries valuation/profitability risk
               flags despite having the single highest growth number.
  * TRAP     - shrinking revenue and earnings plus high debt, "cheap" only
               because the business is deteriorating (classic value trap)
               -- should rank near the bottom despite a low P/E.
  * STEADY   - unremarkable across every sub-score, lands near the middle.
  * THIN     - passes the price/market-cap thresholds but most fundamentals
               fields are missing -- exercises the data-completeness
               confidence penalty and "Thin fundamentals data coverage"
               risk flag.
"""
import random
import zlib
from datetime import datetime, timedelta, timezone

from src.models import Fundamentals, PriceSeries

_NOW = datetime.now(timezone.utc)


def _price_series(ticker, start_price, annual_cagr_pct, days=756, daily_noise_pct=1.2):
    # zlib.crc32 (not builtin hash()) for a seed that's stable across
    # runs/processes -- see sample_data.py for why.
    rng = random.Random(zlib.crc32(ticker.encode()) % 1000)
    daily_rate = (1 + annual_cagr_pct / 100) ** (1 / 252) - 1
    closes = [start_price]
    for _ in range(days - 1):
        noise = rng.uniform(-daily_noise_pct, daily_noise_pct) / 100
        closes.append(round(closes[-1] * (1 + daily_rate + noise), 2))
    dates = [str((_NOW - timedelta(days=days - i)).date()) for i in range(days)]
    volumes = [2_000_000] * days
    return PriceSeries(ticker=ticker, dates=dates, close=closes, volume=volumes)


def generate_offline_long_term_dataset():
    """Returns dict: ticker -> (Fundamentals, PriceSeries)."""
    dataset = {}

    dataset["COMPOUND"] = (
        Fundamentals(
            ticker="COMPOUND", current_price=210.0, market_cap=650_000_000_000,
            sector="Technology", forward_pe=28.0, peg_ratio=1.4,
            revenue_growth=18.0, earnings_growth=22.0,
            gross_margins=60.0, operating_margins=32.0, profit_margins=25.0,
            return_on_equity=38.0, debt_to_equity=40.0,
            free_cashflow=25_000_000_000, dividend_yield=0.5,
            recommendation_mean=1.8, target_mean_price=245.0, beta=1.1,
        ),
        _price_series("COMPOUND", 90.0, annual_cagr_pct=22.0),
    )

    dataset["VALUE"] = (
        Fundamentals(
            ticker="VALUE", current_price=145.0, market_cap=180_000_000_000,
            sector="Consumer Defensive", forward_pe=17.0, peg_ratio=1.9,
            revenue_growth=5.0, earnings_growth=6.0,
            gross_margins=35.0, operating_margins=18.0, profit_margins=14.0,
            return_on_equity=22.0, debt_to_equity=65.0,
            free_cashflow=8_000_000_000, dividend_yield=2.4,
            recommendation_mean=2.4, target_mean_price=155.0, beta=0.7,
        ),
        _price_series("VALUE", 95.0, annual_cagr_pct=8.0),
    )

    dataset["HYPE"] = (
        Fundamentals(
            ticker="HYPE", current_price=85.0, market_cap=40_000_000_000,
            sector="Technology", forward_pe=95.0, peg_ratio=6.5,
            revenue_growth=42.0, earnings_growth=-12.0,
            gross_margins=45.0, operating_margins=-8.0, profit_margins=-6.0,
            return_on_equity=-10.0, debt_to_equity=95.0,
            free_cashflow=-500_000_000, dividend_yield=None,
            recommendation_mean=3.1, target_mean_price=88.0, beta=2.3,
        ),
        _price_series("HYPE", 12.0, annual_cagr_pct=65.0),
    )

    dataset["TRAP"] = (
        Fundamentals(
            ticker="TRAP", current_price=22.0, market_cap=6_000_000_000,
            sector="Industrials", forward_pe=9.0, peg_ratio=None,
            revenue_growth=-8.0, earnings_growth=-18.0,
            gross_margins=18.0, operating_margins=4.0, profit_margins=2.0,
            return_on_equity=3.0, debt_to_equity=220.0,
            free_cashflow=-100_000_000, dividend_yield=1.0,
            recommendation_mean=3.8, target_mean_price=20.0, beta=1.3,
        ),
        _price_series("TRAP", 55.0, annual_cagr_pct=-14.0),
    )

    dataset["STEADY"] = (
        Fundamentals(
            ticker="STEADY", current_price=60.0, market_cap=25_000_000_000,
            sector="Industrials", forward_pe=19.0, peg_ratio=2.0,
            revenue_growth=4.0, earnings_growth=3.0,
            gross_margins=28.0, operating_margins=12.0, profit_margins=8.0,
            return_on_equity=14.0, debt_to_equity=90.0,
            free_cashflow=1_200_000_000, dividend_yield=1.8,
            recommendation_mean=2.8, target_mean_price=63.0, beta=1.0,
        ),
        _price_series("STEADY", 48.0, annual_cagr_pct=7.0),
    )

    dataset["THIN"] = (
        Fundamentals(
            ticker="THIN", current_price=40.0, market_cap=3_500_000_000,
            sector="Healthcare",
        ),
        _price_series("THIN", 35.0, annual_cagr_pct=5.0),
    )

    return dataset
