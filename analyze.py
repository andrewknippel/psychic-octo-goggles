#!/usr/bin/env python3
"""Single-ticker deep-dive report: buy/hold/sell verdict, stop-loss and
take-profit levels, a holding-horizon estimate, and a rundown of the
company, technicals, and recent news/social sentiment.

This is a longer-horizon (weeks-to-months) companion to main.py's 2-7 day
momentum scanner -- see README.md for how the two differ.

Usage:
    python analyze.py AAPL
    python analyze.py TSLA --output tsla_report.json
    python analyze.py NVDA --offline      # demo with synthetic data, no network

Every verdict below is a transparent rule over price/technical and
sentiment signals -- see the "Why" section in the printed report for the
exact reasons. This is a heuristic research aid, not investment advice;
always do your own due diligence before trading anything it suggests.
"""
import argparse
import json
import logging
import sys
from dataclasses import asdict
from datetime import datetime, timezone

import config
from src.analysis.deep_dive import LongTermTechnicalSnapshot, build_recommendation
from src.analysis.sentiment import compute_sentiment_score
from src.data_sources import market_data, news, reddit, stocktwits
from src.sample_data import generate_offline_ticker_report

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logger = logging.getLogger("analyze")


def gather(ticker: str, offline: bool, verbose: bool = False):
    """Returns (price_series, company_info, earnings_date, news_mentions,
    social_mentions), any of which may be None/empty on a data-source miss."""
    if offline:
        news_mentions, social_mentions, price_series, company_info, earnings_date = (
            generate_offline_ticker_report(ticker)
        )
        return price_series, company_info, earnings_date, news_mentions, social_mentions

    if verbose:
        print(f"Fetching price history for {ticker}...", file=sys.stderr)
    price_series = market_data.fetch_price_series(ticker, period=config.DEEPDIVE_PRICE_PERIOD)

    if verbose:
        print("Fetching company fundamentals...", file=sys.stderr)
    company_info = market_data.fetch_company_info(ticker)

    if verbose:
        print("Fetching next earnings date...", file=sys.stderr)
    earnings_date = market_data.fetch_next_earnings_date(ticker)

    if verbose:
        print("Fetching news/Reddit/StockTwits mentions...", file=sys.stderr)
    news_mentions = news.fetch_news_mentions(ticker, company_name=company_info.name if company_info else "")
    social_mentions = reddit.fetch_reddit_mentions(ticker) + stocktwits.fetch_stocktwits_mentions(ticker)

    return price_series, company_info, earnings_date, news_mentions, social_mentions


def _fmt_money(value):
    return f"${value:,.2f}" if value is not None else "n/a"


def _fmt_pct(value, signed=True):
    if value is None:
        return "n/a"
    return f"{value:+.1f}%" if signed else f"{value:.1f}%"


def _fmt_large(value):
    if value is None:
        return "n/a"
    for unit, threshold in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if abs(value) >= threshold:
            return f"${value / threshold:.2f}{unit}"
    return f"${value:,.0f}"


def print_report(ticker, price_series, company_info, earnings_date, news_mentions, social_mentions):
    if price_series is None:
        print(f"No price data found for '{ticker}' -- check the symbol and try again.")
        return

    tech = LongTermTechnicalSnapshot(price_series)
    sentiment_score = (
        compute_sentiment_score(news_mentions, social_mentions)
        if (news_mentions or social_mentions) else None
    )
    rec = build_recommendation(
        ticker, price_series, sentiment_score,
        company_info=company_info, earnings_date=earnings_date,
    )

    name = company_info.name if company_info and company_info.name else ticker
    print("=" * 78)
    print(f" {ticker} -- {name}")
    print("=" * 78)

    if company_info:
        print(f"\nSector: {company_info.sector or 'n/a'}   Industry: {company_info.industry or 'n/a'}")
        print(f"Market cap: {_fmt_large(company_info.market_cap)}   Beta: {company_info.beta or 'n/a'}")
        print(
            f"P/E (trailing/forward): {company_info.trailing_pe or 'n/a'} / {company_info.forward_pe or 'n/a'}"
            f"   Dividend yield: {_fmt_pct(company_info.dividend_yield * 100, signed=False) if company_info.dividend_yield else 'n/a'}"
        )
        if company_info.summary:
            summary = company_info.summary[:400] + ("..." if len(company_info.summary) > 400 else "")
            print(f"\n{summary}")

    print("\n--- Price & trend ---")
    print(f"Last price: {_fmt_money(tech.last_price)}")
    print(
        f"52-week range: {_fmt_money(tech.fifty_two_week_low)} - {_fmt_money(tech.fifty_two_week_high)}"
        f"  ({_fmt_pct(tech.pct_from_high)} from high, {_fmt_pct(tech.pct_from_low)} from low)"
    )
    print(
        f"Moving averages -- 20d: {_fmt_money(tech.sma20)}  50d: {_fmt_money(tech.sma50)}"
        f"  200d: {_fmt_money(tech.sma200)}"
    )
    print(f"RSI-14: {tech.rsi14:.0f}" if tech.rsi14 is not None else "RSI-14: n/a")
    if tech.macd_line is not None:
        trend = "bullish" if tech.macd_bullish else "bearish"
        print(f"MACD: {tech.macd_line:.3f} vs signal {tech.macd_signal:.3f} ({trend})")
    print(
        f"Momentum -- 1mo: {_fmt_pct(tech.momentum_1m)}  3mo: {_fmt_pct(tech.momentum_3m)}"
        f"  6mo: {_fmt_pct(tech.momentum_6m)}"
    )
    print(f"Volume vs 50-day avg: {tech.volume_surge:.2f}x")
    if earnings_date:
        print(f"Next earnings: {earnings_date.isoformat()}")

    print("\n--- Recent headlines ---")
    if news_mentions:
        for m in news_mentions[:5]:
            print(f"  - {m.text[:140]}")
    else:
        print("  (none found)")

    print("\n" + "=" * 78)
    print(f" VERDICT: {rec.action}   (score {rec.overall_score:.0f}/100)")
    print("=" * 78)
    print(f"\nSuggested stop-loss: {_fmt_money(rec.stop_loss)} ({_fmt_pct(-rec.stop_loss_pct if rec.stop_loss_pct else None)})")
    print(
        f"Suggested take-profit / when to sell for a win: {_fmt_money(rec.take_profit)}"
        f" ({_fmt_pct(rec.take_profit_pct)}) -- basis: {rec.take_profit_basis}"
    )
    print(f"\nHow long to hold: {rec.hold_horizon}")
    print(f"  {rec.hold_horizon_reason}")

    print("\nWhy:")
    for reason in rec.reasons:
        print(f"  - {reason}")

    if rec.risk_flags:
        print("\nRisk flags:")
        for flag in rec.risk_flags:
            print(f"  ! {flag}")

    print(
        "\nSell triggers to watch: a daily close below the stop-loss above, "
        "RSI-14 staying above 80 for several days without a new high (blow-off-top "
        "risk), a negative earnings surprise, or a sustained shift to bearish "
        "news/social sentiment."
    )

    print(
        "\nDisclaimer: this is a rule-based technical/sentiment screen, not "
        "investment advice. Data can be delayed, incomplete, or wrong -- verify "
        "independently and consider your own risk tolerance before trading."
    )

    return rec


def save_output(ticker, price_series, company_info, earnings_date, rec, path):
    payload = {
        "ticker": ticker,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "last_price": price_series.close[-1] if price_series and price_series.close else None,
        "company_info": asdict(company_info) if company_info else None,
        "earnings_date": earnings_date.isoformat() if earnings_date else None,
        "recommendation": asdict(rec) if rec else None,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nSaved full report to {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ticker", help="Ticker symbol to analyze, e.g. AAPL")
    parser.add_argument("--offline", action="store_true", help="Use synthetic demo data instead of live APIs")
    parser.add_argument("--output", default="", help="Save the full report to a .json file")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    ticker = args.ticker.strip().upper()
    price_series, company_info, earnings_date, news_mentions, social_mentions = gather(
        ticker, args.offline, verbose=args.verbose
    )
    rec = print_report(ticker, price_series, company_info, earnings_date, news_mentions, social_mentions)

    if args.output and rec is not None:
        save_output(ticker, price_series, company_info, earnings_date, rec, args.output)


if __name__ == "__main__":
    main()
