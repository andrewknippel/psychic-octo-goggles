#!/usr/bin/env python3
"""Short-term (2-7 day) stock scanner.

Pulls news headlines, Reddit posts, and StockTwits messages for a universe
of tickers, blends them with price/volume technicals, and ranks the
tickers by a composite short-term-growth score.

Usage:
    python main.py --watchlist AAPL,TSLA,NVDA --top 10
    python main.py --offline                       # demo with synthetic data
    python main.py --watchlist GME --no-trending    # only score named tickers

This is a research/screening tool, not investment advice. It surfaces
attention + momentum, both of which can reverse violently within days --
always do your own due diligence before trading anything it lists.
"""
import argparse
import csv
import json
import logging
import sys
from dataclasses import asdict
from datetime import datetime, timezone

import config
from src.analysis.scoring import rank_tickers, score_ticker
from src.data_sources import market_data, news, reddit, stocktwits
from src.sample_data import generate_offline_dataset
from src.ticker_discovery import discover_universe

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("main")


def gather_and_score(tickers, verbose=False):
    scores = []
    for ticker in tickers:
        if verbose:
            print(f"  scoring {ticker}...", file=sys.stderr)
        news_mentions = news.fetch_news_mentions(ticker)
        social_mentions = reddit.fetch_reddit_mentions(
            ticker
        ) + stocktwits.fetch_stocktwits_mentions(ticker)
        price_series = market_data.fetch_price_series(ticker)
        earnings_date = market_data.fetch_next_earnings_date(ticker)

        result = score_ticker(
            ticker, news_mentions, social_mentions, price_series, earnings_date=earnings_date
        )
        if result is not None:
            scores.append(result)
        elif verbose:
            print(f"    skipped {ticker}: insufficient data/liquidity", file=sys.stderr)
    return scores


def gather_and_score_offline(tickers, verbose=False):
    dataset = generate_offline_dataset()
    scores = []
    for ticker in tickers:
        if ticker not in dataset:
            continue
        news_mentions, social_mentions, price_series, earnings_date = dataset[ticker]
        result = score_ticker(
            ticker, news_mentions, social_mentions, price_series, earnings_date=earnings_date
        )
        if result is not None:
            scores.append(result)
        elif verbose:
            print(f"    skipped {ticker}: insufficient data/liquidity", file=sys.stderr)
    return scores


def print_table(scores):
    if not scores:
        print("No tickers met the minimum data/liquidity thresholds.")
        return

    header = (
        f"{'#':<3}{'Ticker':<8}{'Score':>7}{'Sent':>7}{'Mom':>7}{'Buzz':>7}"
        f"{'Tech':>7}{'Conf':>6}{'Price':>9}{'3d%':>8}{'Vol%':>7}{'Risk':>6}"
    )
    print(header)
    print("-" * len(header))
    for i, s in enumerate(scores, 1):
        vol_str = f"{s.volatility_pct:.1f}" if s.volatility_pct is not None else "n/a"
        risk_str = f"{len(s.risk_flags)}" if s.risk_flags else "-"
        print(
            f"{i:<3}{s.ticker:<8}{s.final_score:>7.1f}{s.sentiment_score:>7.1f}"
            f"{s.momentum_score:>7.1f}{s.buzz_score:>7.1f}{s.technical_score:>7.1f}"
            f"{s.confidence:>6.2f}{s.last_price:>9.2f}{s.change_3d_pct:>+7.1f}%"
            f"{vol_str:>7}{risk_str:>6}"
        )
    print("\n(Vol% = avg daily price swing over the last ~10 days; Risk = number of risk flags below, '-' = none)\n")
    for i, s in enumerate(scores, 1):
        print(f"{i}. {s.ticker} -- {s.rationale}")


def save_output(scores, path):
    rows = [asdict(s) for s in scores]
    if path.endswith(".json"):
        with open(path, "w") as f:
            json.dump(rows, f, indent=2)
    else:
        if not rows:
            return
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    print(f"\nSaved full results to {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--watchlist", default="", help="Comma-separated tickers to always include, e.g. AAPL,TSLA"
    )
    parser.add_argument(
        "--no-trending", action="store_true",
        help="Only score --watchlist tickers; skip StockTwits/Reddit trending discovery",
    )
    parser.add_argument("--top", type=int, default=config.DEFAULT_TOP_N, help="Number of results to show")
    parser.add_argument("--output", default="", help="Save full results to a .json or .csv file")
    parser.add_argument(
        "--offline", action="store_true",
        help="Use bundled synthetic sample data instead of live APIs (demo/test mode)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    watchlist = [t for t in args.watchlist.split(",") if t.strip()]

    if args.offline:
        universe = watchlist or list(generate_offline_dataset().keys())
        print(f"[offline demo mode] scoring {len(universe)} synthetic tickers: {', '.join(universe)}\n")
        scores = gather_and_score_offline(universe, verbose=args.verbose)
    else:
        if not watchlist and args.no_trending:
            parser.error("--no-trending requires --watchlist to have at least one ticker")
        universe = discover_universe(watchlist, include_trending=not args.no_trending)
        if not universe:
            print("No candidate tickers found (empty watchlist and trending discovery returned nothing).")
            return
        print(f"Scoring {len(universe)} candidate tickers: {', '.join(universe)}\n")
        scores = gather_and_score(universe, verbose=args.verbose)

    all_ranked = rank_tickers(scores, top_n=len(scores))
    top = all_ranked[: args.top]

    print(f"\nTop short-term (2-7 day) growth candidates as of {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}\n")
    print_table(top)

    if args.output:
        save_output(all_ranked, args.output)

    print(
        "\nDisclaimer: this is an automated screen of news/social attention and "
        "short-term price momentum, not investment advice. High-buzz, high-momentum "
        "names carry elevated reversal risk -- verify independently before trading."
    )


if __name__ == "__main__":
    main()
