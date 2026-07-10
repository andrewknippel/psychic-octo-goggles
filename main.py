#!/usr/bin/env python3
"""Two-horizon stock scanner: oversold rebound candidates (~4 weeks) +
same-day momentum movers, both shown by default. --show-momentum adds a
third, original 2-7 day momentum-ranked table.

Default output has two sections:

1. REBOUND CANDIDATES (~4 week horizon): tickers with a low RSI that just
   dropped sharply, show early signs of stabilizing, and whose sentiment
   hasn't turned bearish (which would suggest a falling knife instead of a
   bounce setup). "~4 weeks" describes the timeframe this kind of setup is
   typically evaluated over -- NOT a guarantee it bounces, or that it does
   by any deadline. Nothing can promise that.

2. SAME-DAY MOMENTUM MOVERS: tickers up sharply today on unusually high
   volume. This is NOT a same-day round-trip prediction -- genuine
   intraday trading signals need real-time, minute-by-minute data this
   tool doesn't have. It only flags unusual price+volume activity as of
   the latest daily bar, not which direction the rest of the day goes.
   Buying and selling the same day is high-risk speculation regardless.

See the "Known limitations" section of README.md for more on both.

Live tracking is ON by default: a plain run rescans every 10 minutes
until you press Ctrl+C. It's polling, not a real-time feed -- News/Reddit/
StockTwits data doesn't change meaningfully faster than every several
minutes anyway, and their free/keyless endpoints will start rate-limiting
or blocking you if you hit them too often, hence the 5-minute floor on
--interval.

Usage:
    python main.py --watchlist AAPL,TSLA,NVDA
                                                     # live, refreshes every 10 min
    python main.py --watchlist AAPL,TSLA --interval 20
                                                     # same, but every 20 min
    python main.py --watchlist AAPL,TSLA --once     # single scan, then exit
    python main.py --show-momentum --top 10         # also show the original
                                                     # 2-7 day momentum table
    python main.py --max-candidates 60 --interval 20
                                                     # scan a bigger pool
    python main.py --offline                        # demo with synthetic data
    python main.py --watchlist GME --no-trending     # only score named tickers

With no --watchlist, the candidate pool is auto-discovered from StockTwits
trending + Reddit cashtag mentions, capped at --max-candidates (default
15). Raising it considers more tickers per scan but takes longer -- if a
scan starts taking longer than --interval, raise --interval to match.

An upcoming earnings date within the ~4-week rebound window is flagged
separately (real event risk a technical setup can't account for). In live
mode, a newly-appearing rebound candidate triggers a terminal bell +
banner (same-day movers don't alert, since "still up today" isn't new
information the way "just became a candidate" is).

Penny stocks (price below MIN_PRICE, $5 by default) are excluded entirely,
not just scored low -- see config.py.

This is a research/screening tool, not investment advice. It surfaces
oversold/attention/momentum signals, all of which can keep moving against
you -- always do your own due diligence before trading anything it lists.
"""
import argparse
import csv
import json
import logging
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone

import config
from src.analysis.day_movers import rank_day_movers, scan_for_day_movers
from src.analysis.dip_scanner import rank_dip_candidates, scan_for_dips
from src.analysis.scoring import rank_tickers, score_ticker
from src.data_sources import market_data, news, reddit, stocktwits
from src.sample_data import generate_offline_dataset
from src.ticker_discovery import discover_universe

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("main")

# yfinance logs its own "possibly delisted"/"no data found" messages
# directly (outside our warning system) for every ticker miss -- our code
# already catches these and skips the ticker cleanly, so this is silenced
# to avoid alarming, duplicate-looking output for an already-handled case.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)


def gather_and_score(tickers, verbose=False):
    """Returns (scores, raw_data). raw_data holds each ticker's fetched
    (news_mentions, social_mentions, price_series, earnings_date) so
    callers -- e.g. the dip scanner -- can reuse it without refetching and
    burning extra requests against the free/keyless APIs."""
    scores = []
    raw_data = []
    for ticker in tickers:
        if verbose:
            print(f"  scoring {ticker}...", file=sys.stderr)
        news_mentions = news.fetch_news_mentions(ticker)
        social_mentions = reddit.fetch_reddit_mentions(
            ticker
        ) + stocktwits.fetch_stocktwits_mentions(ticker)
        price_series = market_data.fetch_price_series(ticker)
        earnings_date = market_data.fetch_next_earnings_date(ticker)
        raw_data.append((ticker, news_mentions, social_mentions, price_series, earnings_date))

        result = score_ticker(
            ticker, news_mentions, social_mentions, price_series, earnings_date=earnings_date
        )
        if result is not None:
            scores.append(result)
        elif verbose:
            print(f"    skipped {ticker}: insufficient data/liquidity", file=sys.stderr)
    return scores, raw_data


def gather_and_score_offline(tickers, verbose=False):
    dataset = generate_offline_dataset()
    scores = []
    raw_data = []
    for ticker in tickers:
        if ticker not in dataset:
            continue
        news_mentions, social_mentions, price_series, earnings_date = dataset[ticker]
        raw_data.append((ticker, news_mentions, social_mentions, price_series, earnings_date))
        result = score_ticker(
            ticker, news_mentions, social_mentions, price_series, earnings_date=earnings_date
        )
        if result is not None:
            scores.append(result)
        elif verbose:
            print(f"    skipped {ticker}: insufficient data/liquidity", file=sys.stderr)
    return scores, raw_data


def print_quick_summary(scores):
    if not scores:
        return
    print("QUICK PICKS (ticker, score out of 100):")
    picks = "   ".join(f"{i}. {s.ticker} ({s.final_score:.1f})" for i, s in enumerate(scores, 1))
    print(picks + "\n")


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


def print_rebound_section(candidates, heading="REBOUND CANDIDATES"):
    ranked = rank_dip_candidates(candidates)
    print("\n" + "=" * 88)
    print(f"{heading} -- low RSI, just dipped, sentiment not panicking (~4wk horizon, not a prediction)")
    print("=" * 88)
    if not ranked:
        print("None right now.")
        return
    for i, c in enumerate(ranked, 1):
        rsi_str = f"{c.rsi:.0f}" if c.rsi is not None else "n/a"
        earn_str = f"  earnings {c.earnings_date}" if c.earnings_date else ""
        print(
            f"{i}. {c.ticker:<8} ${c.last_price:<10.2f} 3d {c.change_3d_pct:+.1f}%  "
            f"5d {c.change_5d_pct:+.1f}%  RSI {rsi_str}{earn_str}"
        )
        print(f"   {c.summary}")
    print(
        "\nReminder: these are oversold-bounce candidates, not predictions -- a sharp drop "
        "can keep falling (a \"falling knife\") instead of rebounding. Verify independently."
    )


def print_day_mover_section(movers):
    ranked = rank_day_movers(movers)
    print("\n" + "=" * 88)
    print("SAME-DAY MOMENTUM MOVERS -- big move + unusual volume today (not a round-trip guarantee)")
    print("=" * 88)
    if not ranked:
        print("None right now.")
        return
    for i, m in enumerate(ranked, 1):
        print(f"{i}. {m.ticker:<8} ${m.last_price:<10.2f} today {m.change_1d_pct:+.1f}%")
        print(f"   {m.summary}")
    print(
        "\nReminder: same-day (intraday) trading is high-risk speculation. This only flags "
        "unusual price+volume activity happening today -- it does NOT predict which way the "
        "rest of the day goes, and it is not built from real-time/intraday data, only the "
        "latest daily bar. Verify independently before trading on it."
    )


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
    """Runs one full discover -> fetch -> score -> print cycle.

    By default only prints REBOUND CANDIDATES (oversold-dip setups). Pass
    --show-momentum to also print the original momentum-ranked table.

    Returns the set of tickers currently flagged as rebound candidates, so
    live mode can tell a newly-appearing one apart from one it already
    told you about last cycle.
    """
    if args.offline:
        universe = watchlist or list(generate_offline_dataset().keys())
        print(f"[offline demo mode] scoring {len(universe)} synthetic tickers: {', '.join(universe)}\n")
        scores, raw_data = gather_and_score_offline(universe, verbose=args.verbose)
    else:
        universe = discover_universe(
            watchlist, include_trending=not args.no_trending,
            max_candidates=args.max_candidates,
        )
        if not universe:
            print("No candidate tickers found (empty watchlist and trending discovery returned nothing).")
            return set()
        print(f"Scoring {len(universe)} candidate tickers: {', '.join(universe)}\n")
        scores, raw_data = gather_and_score(universe, verbose=args.verbose)

    all_ranked = rank_tickers(scores, top_n=len(scores))

    if args.show_momentum:
        top = all_ranked[: args.top]
        print(f"\nTop short-term (2-7 day) momentum candidates as of {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}\n")
        print_quick_summary(top)
        print_table(top)

    dip_candidates = scan_for_dips(raw_data)
    print_rebound_section(dip_candidates)

    day_movers = scan_for_day_movers(raw_data)
    print_day_mover_section(day_movers)

    if args.output:
        save_output(all_ranked, args.output)

    return {c.ticker for c in dip_candidates}


def run_watch_loop(args, watchlist):
    interval_minutes = max(args.interval, config.MIN_WATCH_INTERVAL_MINUTES)
    if args.interval < config.MIN_WATCH_INTERVAL_MINUTES:
        print(
            f"Note: --interval raised to {interval_minutes} min (minimum) -- "
            "the free news/Reddit/StockTwits endpoints this tool uses will start "
            "rate-limiting or blocking you if hit too frequently.\n"
        )

    print(
        f"Live tracking (default mode): rescanning every {interval_minutes} min. "
        "Press Ctrl+C to stop, or rerun with --once for a single scan.\n"
        "Rebound alerts (terminal bell + banner) fire only when a ticker newly "
        "becomes a candidate, not on every refresh it's still sitting there.\n"
    )
    cycle = 1
    previously_seen_dips = set()
    try:
        while True:
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            banner = f" Refresh #{cycle} -- {stamp} "
            print(f"\n{banner.center(88, '=')}\n")
            dip_tickers = run_scan(args, watchlist) or set()

            new_dips = dip_tickers - previously_seen_dips
            if new_dips:
                alert = f" NEW REBOUND CANDIDATE: {', '.join(sorted(new_dips))} "
                print("\a" + alert.center(88, "!"))
            previously_seen_dips = dip_tickers

            cycle += 1
            print(f"\nNext refresh in {interval_minutes} min... (Ctrl+C to stop)")
            time.sleep(interval_minutes * 60)
    except KeyboardInterrupt:
        print("\nStopped live tracking.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--watchlist", default="", help="Comma-separated tickers to always include, e.g. AAPL,TSLA"
    )
    parser.add_argument(
        "--no-trending", action="store_true",
        help="Only score --watchlist tickers; skip StockTwits/Reddit trending discovery",
    )
    parser.add_argument(
        "--max-candidates", type=int, default=config.MAX_DISCOVERY_CANDIDATES,
        help=f"Max auto-discovered tickers to scan on top of --watchlist (default "
             f"{config.MAX_DISCOVERY_CANDIDATES}). Higher = more tickers considered but "
             f"a slower scan -- raise --interval to match if a cycle runs long.",
    )
    parser.add_argument(
        "--show-momentum", action="store_true",
        help="Also show the original momentum-ranked table (default: only REBOUND "
             "CANDIDATES are shown)",
    )
    parser.add_argument("--top", type=int, default=config.DEFAULT_TOP_N, help="Number of results to show in --show-momentum")
    parser.add_argument("--output", default="", help="Save full results to a .json or .csv file (overwritten on each refresh)")
    parser.add_argument(
        "--offline", action="store_true",
        help="Use bundled synthetic sample data instead of live APIs (demo/test mode)",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single scan and exit, instead of the default live-tracking loop",
    )
    parser.add_argument(
        "--interval", type=int, default=config.DEFAULT_WATCH_INTERVAL_MINUTES,
        help=f"Minutes between refreshes in live mode (default {config.DEFAULT_WATCH_INTERVAL_MINUTES}, "
             f"minimum {config.MIN_WATCH_INTERVAL_MINUTES}; ignored with --once)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    watchlist = [t for t in args.watchlist.split(",") if t.strip()]

    if not args.offline and not watchlist and args.no_trending:
        parser.error("--no-trending requires --watchlist to have at least one ticker")

    if args.once:
        run_scan(args, watchlist)
    else:
        run_watch_loop(args, watchlist)

    print(
        "\nDisclaimer: this is an automated screen of news/social attention and "
        "short-term price momentum, not investment advice. High-buzz, high-momentum "
        "names carry elevated reversal risk -- verify independently before trading."
    )


if __name__ == "__main__":
    main()
