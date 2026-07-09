#!/usr/bin/env python3
"""Long-term (3-5 year) stock picks: a fundamentals-driven screener.

This is a different tool from main.py's short-term scanner, not a mode of
it -- a 2-7 day momentum/sentiment screen and a 3-5 year holding decision
should not be driven by the same signals. This one ignores news/social
buzz entirely and instead scores each company on growth, profitability,
balance-sheet health, valuation, analyst coverage, and long-run price
trend (see src/analysis/fundamentals_scoring.py for the exact formula).

Usage:
    python long_term.py                              # scan the curated
                                                       # default pool (~40
                                                       # large/mid-caps),
                                                       # show top 10
    python long_term.py --watchlist AAPL,COST,LLY     # always include these
    python long_term.py --watchlist NVDA --no-default-pool
                                                       # only score named
                                                       # tickers
    python long_term.py --max-candidates 20 --top 5
    python long_term.py --output output/long_term.json
    python long_term.py --offline --once -v           # demo, no network
                                                       # ("--once" accepted
                                                       # for symmetry with
                                                       # main.py; this tool
                                                       # always runs once)

Unlike main.py, there's no live-tracking loop -- fundamentals move on a
quarterly cadence, not minute to minute, so a single scan is the right
default. Rerun it whenever you want a fresh read (e.g. after an earnings
season).

This is a research/screening tool, not investment advice. It surfaces
statistically decent-looking businesses by the numbers yfinance reports;
it knows nothing about competitive moats, management quality, or events
that haven't happened yet. Always do your own due diligence.
"""
import argparse
import csv
import json
import logging
import sys
from dataclasses import asdict
from datetime import datetime, timezone

import config
from src.analysis.fundamentals_scoring import rank_long_term, score_long_term_ticker
from src.data_sources import fundamentals as fundamentals_source
from src.data_sources import market_data
from src.long_term_sample_data import generate_offline_long_term_dataset
from src.long_term_universe import CANDIDATE_POOL

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("long_term")

# yfinance logs its own "possibly delisted"/"no data found" messages
# directly for every ticker miss -- already handled cleanly by our code, so
# silenced to avoid alarming, duplicate-looking output.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)


def gather_and_score(tickers, verbose=False):
    scores = []
    for ticker in tickers:
        if verbose:
            print(f"  scoring {ticker}...", file=sys.stderr)
        fundamentals = fundamentals_source.fetch_fundamentals(ticker)
        price_series = market_data.fetch_price_series(ticker, period="3y")
        result = score_long_term_ticker(ticker, fundamentals, price_series)
        if result is not None:
            scores.append(result)
        elif verbose:
            print(f"    skipped {ticker}: no data or below price/market-cap thresholds", file=sys.stderr)
    return scores


def gather_and_score_offline(tickers, verbose=False):
    dataset = generate_offline_long_term_dataset()
    scores = []
    for ticker in tickers:
        if ticker not in dataset:
            continue
        fundamentals, price_series = dataset[ticker]
        result = score_long_term_ticker(ticker, fundamentals, price_series)
        if result is not None:
            scores.append(result)
        elif verbose:
            print(f"    skipped {ticker}: no data or below price/market-cap thresholds", file=sys.stderr)
    return scores


def print_quick_summary(scores):
    if not scores:
        return
    print("QUICK PICKS (ticker, score out of 100):")
    picks = "   ".join(f"{i}. {s.ticker} ({s.final_score:.1f})" for i, s in enumerate(scores, 1))
    print(picks + "\n")


def _fmt_market_cap(cap):
    if cap is None:
        return "n/a"
    if cap >= 1e12:
        return f"{cap / 1e12:.2f}T"
    return f"{cap / 1e9:.0f}B"


def print_table(scores):
    if not scores:
        print("No tickers met the minimum price/market-cap thresholds.")
        return

    header = (
        f"{'#':<3}{'Ticker':<8}{'Score':>7}{'Grow':>6}{'Prof':>6}{'Health':>7}"
        f"{'Val':>6}{'Analy':>6}{'Trend':>6}{'Conf':>6}{'Price':>10}{'MktCap':>9}{'Risk':>6}"
    )
    print(header)
    print("-" * len(header))
    for i, s in enumerate(scores, 1):
        risk_str = f"{len(s.risk_flags)}" if s.risk_flags else "-"
        print(
            f"{i:<3}{s.ticker:<8}{s.final_score:>7.1f}{s.growth_score:>6.0f}"
            f"{s.profitability_score:>6.0f}{s.financial_health_score:>7.0f}"
            f"{s.valuation_score:>6.0f}{s.analyst_score:>6.0f}{s.trend_score:>6.0f}"
            f"{s.confidence:>6.2f}{s.current_price:>10.2f}{_fmt_market_cap(s.market_cap):>9}{risk_str:>6}"
        )
    print(
        "\n(Grow/Prof/Health/Val/Analy/Trend = 0-100 sub-scores; Conf = data-completeness "
        "confidence multiplier; Risk = number of risk flags below, '-' = none)\n"
    )
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


def run_scan(args, watchlist):
    if args.offline:
        universe = watchlist or list(generate_offline_long_term_dataset().keys())
        print(f"[offline demo mode] scoring {len(universe)} synthetic tickers: {', '.join(universe)}\n")
        scores = gather_and_score_offline(universe, verbose=args.verbose)
    else:
        watchlist_set = set(watchlist)
        if args.no_default_pool:
            universe = sorted(watchlist_set)
        else:
            pool_extra = [t for t in CANDIDATE_POOL if t not in watchlist_set][: args.max_candidates]
            universe = sorted(watchlist_set | set(pool_extra))
        if not universe:
            print("No candidate tickers to scan (empty watchlist with --no-default-pool).")
            return
        print(f"Scoring {len(universe)} candidate tickers (this pulls 3y of price history per "
              f"ticker, so it can take a bit): {', '.join(universe)}\n")
        scores = gather_and_score(universe, verbose=args.verbose)

    all_ranked = rank_long_term(scores, top_n=len(scores))
    top = all_ranked[: args.top]

    print(f"\nTop long-term (3-5 year) picks as of {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}\n")
    print_quick_summary(top)
    print_table(top)

    if args.output:
        save_output(all_ranked, args.output)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--watchlist", default="", help="Comma-separated tickers to always include, e.g. AAPL,COST,LLY"
    )
    parser.add_argument(
        "--no-default-pool", action="store_true",
        help="Only score --watchlist tickers; skip the curated default candidate pool",
    )
    parser.add_argument(
        "--max-candidates", type=int, default=config.LT_DEFAULT_MAX_CANDIDATES,
        help=f"Max default-pool tickers to scan on top of --watchlist (default "
             f"{config.LT_DEFAULT_MAX_CANDIDATES}).",
    )
    parser.add_argument("--top", type=int, default=config.LT_DEFAULT_TOP_N, help="Number of results to show")
    parser.add_argument("--output", default="", help="Save full results to a .json or .csv file")
    parser.add_argument(
        "--offline", action="store_true",
        help="Use bundled synthetic sample data instead of live APIs (demo/test mode)",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="No-op: this tool always runs a single scan. Accepted for symmetry with main.py.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    watchlist = [t.strip().upper() for t in args.watchlist.split(",") if t.strip()]

    if not args.offline and not watchlist and args.no_default_pool:
        parser.error("--no-default-pool requires --watchlist to have at least one ticker")

    run_scan(args, watchlist)

    print(
        "\nDisclaimer: this is an automated fundamentals screen (growth, profitability, "
        "balance-sheet health, valuation, analyst coverage, long-run price trend), not "
        "investment advice. Past growth and price trend are not guarantees of future "
        "results -- verify independently before investing."
    )


if __name__ == "__main__":
    main()
