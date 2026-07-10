"""Synthetic offline dataset for demoing/testing the pipeline without network
access. Timestamps are generated relative to "now" so the data always falls
inside the configured lookback window, regardless of when it's run.

Five archetypes are included to exercise the scorer meaningfully:
  * MOMO  - strong bullish news+social sentiment, rising price, volume surge
  * SLOW  - mildly bullish, unremarkable technicals (mid-table)
  * BAGGY - bearish sentiment, falling price
  * QUIET - good technicals but too few mentions (should be filtered out)
  * TOPPY - hot buzz but RSI extremely overbought after a vertical run,
            plus earnings in 2 days (exercises the risk-aware technical
            sub-score and both the overbought/earnings risk flags)
  * DIPPY - dropped sharply but sentiment is holding up ("buying the dip"
            framing, not bad company-specific news) and the decline is
            decelerating/oversold, plus earnings in 15 days (inside the
            ~4wk rebound window) -- should surface in dip_scanner's
            REBOUND CANDIDATES with an earnings flag, unlike BAGGY, whose
            drop is paired with bearish sentiment and reads as a falling
            knife instead
"""
import random
import zlib
from datetime import datetime, timedelta, timezone

from src.models import Mention, PriceSeries

_NOW = datetime.now(timezone.utc)
_TODAY = _NOW.date()


def _mentions(ticker, source, texts_and_sentiments, hours_ago_start=2, engagement=25):
    mentions = []
    for i, (text, tag) in enumerate(texts_and_sentiments):
        ts = _NOW - timedelta(hours=hours_ago_start + i * 3)
        mentions.append(
            Mention(
                ticker=ticker,
                source=source,
                text=text,
                timestamp=ts,
                url=f"https://example.com/{source}/{ticker}/{i}",
                engagement=engagement + i * 5,
                explicit_sentiment=tag,
            )
        )
    return mentions


def _price_series(ticker, start_price, daily_pct_changes, volumes):
    # zlib.crc32 (not the builtin hash()) so the seed -- and therefore this
    # synthetic dataset -- is identical across runs/processes. str hashing
    # in Python 3 is randomized per-process by default, which was making
    # RSI/risk-flag output drift from one run to the next.
    rng = random.Random(zlib.crc32(ticker.encode()) % 1000)
    closes = [start_price]
    for pct in daily_pct_changes:
        closes.append(round(closes[-1] * (1 + pct / 100 + rng.uniform(-0.3, 0.3) / 100), 2))
    dates = [
        str((_NOW - timedelta(days=len(closes) - i)).date()) for i in range(len(closes))
    ]
    return PriceSeries(ticker=ticker, dates=dates, close=closes, volume=volumes)


_BASELINE_FLAT = [0.1, -0.2, 0.3, -0.1, 0.2, 0.0, -0.1]  # 7 quiet lead-in days
_BASELINE_VOL = [900_000, 870_000, 910_000, 890_000, 900_000, 880_000, 895_000]


def generate_offline_dataset():
    """Returns dict: ticker -> (news_mentions, social_mentions, price_series, earnings_date)."""
    dataset = {}

    # MOMO: quiet baseline, then a genuine accelerating breakout with volume
    # confirmation -- healthy setup, not yet extended. Earnings are far
    # enough out that they shouldn't trip the earnings risk flag.
    dataset["MOMO"] = (
        _mentions(
            "MOMO",
            "news",
            [
                ("MOMO shares surge after blowout earnings beat and raised guidance.", None),
                ("Analysts upgrade MOMO price target citing accelerating growth.", None),
                ("MOMO announces new product line, investors cheer.", None),
            ],
        ),
        _mentions(
            "MOMO",
            "stocktwits",
            [(f"MOMO breaking out, loading calls #{i}", "Bullish") for i in range(8)],
            engagement=40,
        ),
        _price_series(
            "MOMO", 22.0, _BASELINE_FLAT + [1.2, 2.1, 3.4, 2.8, 4.1],
            volumes=_BASELINE_VOL + [1_400_000, 1_900_000, 3_200_000, 4_600_000, 5_100_000, 5_300_000],
        ),
        _TODAY + timedelta(days=12),
    )

    # SLOW: mild positive, unremarkable -- 12 quiet grinding-up days.
    dataset["SLOW"] = (
        _mentions(
            "SLOW",
            "news",
            [("SLOW posts in-line quarterly results, guidance unchanged.", None)],
        ),
        _mentions(
            "SLOW",
            "stocktwits",
            [("SLOW slow and steady, holding my shares", "Bullish"),
             ("SLOW not doing much either way", None),
             ("SLOW might grind higher into next week", "Bullish")],
        ),
        _price_series(
            "SLOW", 48.0,
            [0.2, 0.1, -0.1, 0.3, 0.0, 0.2, -0.1, 0.2, 0.4, -0.1, 0.6, 0.3],
            volumes=[500_000, 480_000, 510_000, 495_000, 520_000, 505_000,
                     490_000, 500_000, 510_000, 495_000, 520_000, 505_000, 515_000],
        ),
        None,
    )

    # BAGGY: quiet baseline, then a sustained bearish leg lower.
    dataset["BAGGY"] = (
        _mentions(
            "BAGGY",
            "news",
            [
                ("BAGGY shares slide after disappointing guidance cut.", None),
                ("Analysts downgrade BAGGY on demand concerns.", None),
            ],
        ),
        _mentions(
            "BAGGY",
            "stocktwits",
            [(f"BAGGY dumping this, bad news everywhere #{i}", "Bearish") for i in range(6)],
        ),
        _price_series(
            "BAGGY", 15.0, _BASELINE_FLAT + [-2.1, -1.8, -3.0, -1.2, -2.5],
            volumes=_BASELINE_VOL + [800_000, 1_100_000, 1_300_000, 1_500_000, 1_600_000, 1_650_000],
        ),
        None,
    )

    # QUIET: good technicals, but almost no mentions -> filtered by MIN_MENTIONS.
    dataset["QUIET"] = (
        [],
        _mentions("QUIET", "stocktwits", [("QUIET quietly ripping", "Bullish")]),
        _price_series(
            "QUIET", 30.0,
            [0.2, 0.3, 0.1, 0.4, 0.2, 0.3, 0.1, 1.0, 1.5, 1.0, 0.8, 1.2],
            volumes=[300_000, 310_000, 305_000, 320_000, 315_000, 330_000,
                     310_000, 315_000, 320_000, 318_000, 322_000, 325_000, 330_000],
        ),
        None,
    )

    # TOPPY: quiet baseline, then a vertical, unsustainable spike -- heavy
    # buzz and maxed-out raw momentum, but RSI/technical health should flag
    # it as extended rather than blindly rewarding the hype. Also has
    # earnings in 2 days, exercising the earnings risk flag.
    dataset["TOPPY"] = (
        _mentions(
            "TOPPY",
            "news",
            [("TOPPY goes parabolic, up huge again on no news.", None)],
        ),
        _mentions(
            "TOPPY",
            "stocktwits",
            [(f"TOPPY to the moon!!! #{i}", "Bullish") for i in range(10)],
            engagement=60,
        ),
        _price_series(
            "TOPPY", 8.0, _BASELINE_FLAT + [9.0, 12.0, 15.0, 11.0, 14.0],
            volumes=_BASELINE_VOL + [2_500_000, 6_000_000, 9_000_000, 12_000_000, 15_000_000, 18_000_000],
        ),
        _TODAY + timedelta(days=2),
    )

    # DIPPY: quiet baseline, then a real drop -- but sentiment is framing it
    # as a buying opportunity (broad pullback), not a company-specific
    # problem, and the decline is decelerating with an oversold RSI. This is
    # the "big dip, likely to bounce" case the dip scanner is meant to catch.
    dataset["DIPPY"] = (
        _mentions(
            "DIPPY",
            "news",
            [("DIPPY shares fall with broader market pullback; no company-specific news.", None)],
        ),
        _mentions(
            "DIPPY",
            "stocktwits",
            [
                ("DIPPY oversold here, buying this dip", "Bullish"),
                ("still like DIPPY long term, this is just market noise", "Bullish"),
                ("DIPPY starting to find a floor", "Bullish"),
                ("added more DIPPY on the drop", "Bullish"),
            ],
            engagement=20,
        ),
        _price_series(
            "DIPPY", 40.0, _BASELINE_FLAT + [-3.5, -4.0, -2.5, -0.8],
            volumes=_BASELINE_VOL[:7] + [700_000, 1_100_000, 1_600_000, 1_900_000, 1_200_000],
        ),
        _TODAY + timedelta(days=15),  # inside the ~4wk rebound window -> earnings flag
    )

    return dataset
