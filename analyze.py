#!/usr/bin/env python3
"""Single-ticker short-term analysis: probability of a gain within a week,
and an estimated best day to sell.

Pulls several years of daily price history for one ticker via yfinance,
finds historical days whose technical state (RSI, momentum, distance from
its 20-day average, volatility, volume) looked like today's, and reports
what happened over the following 1-5 trading days on those look-alike days.
See README.md's "Single-ticker analysis" section for methodology and
caveats -- this is a statistical/historical-analog estimate, not investment
advice.

Usage:
    python analyze.py AAPL
    python analyze.py TSLA --period 10y --k 60
    python analyze.py NVDA --output output/nvda_forecast.json
    python analyze.py DEMO --offline           # synthetic demo, no network
"""
import argparse
import json
import sys
from dataclasses import asdict

from src.analysis.forecast import (
    DEFAULT_K,
    HORIZON_DAYS,
    MIN_TRAINING_ROWS,
    WARMUP_DAYS,
    ForecastResult,
    analyze_price_series,
    analyze_ticker,
    synthetic_price_series,
)


def format_report(r: ForecastResult) -> str:
    lines = []
    lines.append(f"=== {r.ticker} short-term analysis (as of {r.as_of_date}) ===")
    lines.append(f"Last close: ${r.last_price:.2f}")
    lines.append("")
    lines.append("Current technical snapshot:")
    lines.append(f"  RSI(14): {r.rsi14:.1f}")
    lines.append(f"  5-day momentum: {r.momentum_5d_pct:+.1f}%")
    lines.append(f"  Distance from 20-day SMA: {r.dist_from_sma20_pct:+.1f}%")
    lines.append(f"  20-day volatility: {r.volatility_20d_pct:.1f}%/day")
    lines.append(f"  Volume vs 20-day avg: {r.volume_ratio:.2f}x")
    lines.append("")
    lines.append(
        f"Historical analog analysis ({r.neighbors_used} of {r.analog_pool_size} "
        "similar historical setups used):"
    )
    lines.append(f"  Probability of a short-term gain within the week: {r.prob_gain_within_week_pct:.0f}%")
    lines.append(
        "  (share of look-alike historical days where price traded above today's "
        "close at *some* point over the next 5 trading days)"
    )
    lines.append("")
    lines.append("  Expected return by day-ahead:")
    for d in r.day_forecasts:
        marker = "   <-- estimated best day to sell" if d.day == r.best_sell_day else ""
        lines.append(
            f"    +{d.day}d: {d.avg_return_pct:+.1f}%  "
            f"({d.prob_positive_pct:.0f}% of analogs positive){marker}"
        )
    plural = "s" if r.best_sell_day != 1 else ""
    lines.append("")
    lines.append(
        f"  Best estimated sell point: ~{r.best_sell_day} trading day{plural} from now "
        f"(around {r.best_sell_date}), expected {r.best_sell_expected_return_pct:+.1f}% "
        f"({r.best_sell_prob_positive_pct:.0f}% of analogs were positive at that point)."
    )

    if r.notes:
        lines.append("")
        for note in r.notes:
            lines.append(f"  Note: {note}")

    lines.append("")
    lines.append(
        "This is a statistical/historical-analog estimate, not a prediction or "
        f"financial advice -- past look-alike setups are not a guarantee of what "
        f"{r.ticker} does next. Always do your own due diligence."
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("ticker", help="Ticker symbol to analyze, e.g. AAPL")
    parser.add_argument(
        "--period", default="5y", choices=["1y", "2y", "5y", "10y", "max"],
        help="How much price history to pull (default 5y). Falls back to 'max' "
             "automatically if the ticker doesn't have that much history.",
    )
    parser.add_argument(
        "--k", type=int, default=DEFAULT_K,
        help=f"Number of historical analog days to average over (default {DEFAULT_K})",
    )
    parser.add_argument("--output", default="", help="Save the full result to a .json file")
    parser.add_argument(
        "--offline", action="store_true",
        help="Use a synthetic demo series instead of live data (no network required)",
    )
    args = parser.parse_args()

    ticker = args.ticker.strip().upper()

    if args.offline:
        series = synthetic_price_series(ticker)
        result = analyze_price_series(series, k=args.k)
    else:
        result = analyze_ticker(ticker, period=args.period, k=args.k)

    if result is None:
        min_needed = WARMUP_DAYS + HORIZON_DAYS + MIN_TRAINING_ROWS
        print(
            f"Not enough historical data for {ticker} to run this analysis "
            f"(need at least ~{min_needed} trading days of history, and the ticker "
            "must be recognized by Yahoo Finance)."
        )
        sys.exit(1)

    print(format_report(result))

    if args.output:
        with open(args.output, "w") as f:
            json.dump(asdict(result), f, indent=2)
        print(f"\nSaved full result to {args.output}")


if __name__ == "__main__":
    main()
