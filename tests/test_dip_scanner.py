from datetime import datetime, timedelta, timezone

import config
from src.analysis.dip_scanner import find_dip_candidate, scan_for_dips
from src.models import Mention, PriceSeries

NOW = datetime.now(timezone.utc)


def _mention(ticker, tag=None, text="", hours_ago=1, source="stocktwits"):
    return Mention(
        ticker=ticker, source=source, text=text,
        timestamp=NOW - timedelta(hours=hours_ago), engagement=10,
        explicit_sentiment=tag,
    )


def _series(ticker, closes, volumes=None):
    volumes = volumes or [500_000] * len(closes)
    return PriceSeries(ticker=ticker, dates=[str(i) for i in range(len(closes))],
                        close=closes, volume=volumes)


def test_no_drop_is_not_a_dip_candidate():
    mentions = [_mention("FLAT", tag="Bullish", hours_ago=i) for i in range(4)]
    series = _series("FLAT", [10, 10.1, 10.0, 10.2, 10.1, 10.3])
    assert find_dip_candidate("FLAT", [], mentions, series, now=NOW) is None


def test_uptrend_is_not_a_dip_candidate():
    mentions = [_mention("UP", tag="Bullish", hours_ago=i) for i in range(4)]
    series = _series("UP", [10, 10.5, 11, 11.8, 12.5, 13.2])
    assert find_dip_candidate("UP", [], mentions, series, now=NOW) is None


def test_sharp_drop_with_bearish_sentiment_excluded_as_falling_knife():
    # Big drop, but sentiment is clearly bearish -- should NOT be flagged.
    mentions = [_mention("KNIFE", tag="Bearish", hours_ago=i) for i in range(6)]
    series = _series("KNIFE", [20, 18, 16, 14, 12, 10])  # -50% over 5 days
    assert find_dip_candidate("KNIFE", [], mentions, series, now=NOW) is None


def test_sharp_drop_with_holding_sentiment_and_oversold_rsi_is_flagged():
    mentions = [
        _mention("BOUNCE", tag="Bullish", hours_ago=i) for i in range(4)
    ]
    # 9 closes (8 changes) so RSI(7) actually computes: mild chop, then a
    # sustained decline with only one small up-day -> deeply oversold, and
    # -17.6% over 5 days clears the drop threshold.
    series = _series(
        "BOUNCE", [30, 30.2, 29.9, 30.1, 28.5, 27.0, 25.8, 25.0, 24.8]
    )
    candidate = find_dip_candidate("BOUNCE", [], mentions, series, now=NOW)
    assert candidate is not None
    assert candidate.change_5d_pct <= -config.DIP_DROP_PCT
    assert candidate.rsi is not None and candidate.rsi <= config.DIP_RSI_OVERSOLD
    assert any("oversold" in r for r in candidate.reasons)
    assert "BOUNCE" in candidate.summary


def test_drop_below_threshold_not_flagged():
    mentions = [_mention("MINI", tag="Bullish", hours_ago=i) for i in range(4)]
    # Only ~2% drop -- shouldn't clear the default 8% DIP_DROP_PCT threshold.
    series = _series("MINI", [20, 19.8, 19.7, 19.6, 19.6, 19.6])
    assert find_dip_candidate("MINI", [], mentions, series, now=NOW) is None


def test_no_price_series_returns_none():
    mentions = [_mention("X", tag="Bullish", hours_ago=i) for i in range(4)]
    assert find_dip_candidate("X", [], mentions, None, now=NOW) is None


def test_illiquid_or_penny_dip_excluded(monkeypatch):
    mentions = [_mention("PENNY", tag="Bullish", hours_ago=i) for i in range(4)]
    series = _series("PENNY", [2.0, 1.9, 1.7, 1.5, 1.4, 1.3], volumes=[400_000] * 6)
    assert find_dip_candidate("PENNY", [], mentions, series, now=NOW) is None


def test_scan_for_dips_filters_a_mixed_batch():
    up_mentions = [_mention("UP", tag="Bullish", hours_ago=i) for i in range(4)]
    bounce_mentions = [_mention("BOUNCE", tag="Bullish", hours_ago=i) for i in range(4)]
    knife_mentions = [_mention("KNIFE", tag="Bearish", hours_ago=i) for i in range(6)]

    batch = [
        ("UP", [], up_mentions, _series("UP", [10, 10.5, 11, 11.8, 12.5, 13.2])),
        ("BOUNCE", [], bounce_mentions, _series("BOUNCE", [20, 19, 17.5, 16, 15.2, 15.0])),
        ("KNIFE", [], knife_mentions, _series("KNIFE", [20, 18, 16, 14, 12, 10])),
    ]
    results = {c.ticker for c in scan_for_dips(batch)}
    assert results == {"BOUNCE"}
