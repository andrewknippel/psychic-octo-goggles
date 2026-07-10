from datetime import datetime, timedelta, timezone

import config
from src.analysis.dip_scanner import (
    find_dip_candidate,
    rank_dip_candidates,
    scan_for_dips,
)
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


def test_scan_for_dips_accepts_5_tuples_with_earnings_date():
    bounce_mentions = [_mention("BOUNCE", tag="Bullish", hours_ago=i) for i in range(4)]
    earnings_soon = (NOW + timedelta(days=10)).date()
    batch = [
        ("BOUNCE", [], bounce_mentions, _series("BOUNCE", [20, 19, 17.5, 16, 15.2, 15.0]), earnings_soon),
    ]
    results = {c.ticker: c for c in scan_for_dips(batch)}
    assert "BOUNCE" in results
    assert results["BOUNCE"].earnings_date == earnings_soon.isoformat()


def test_earnings_within_window_is_flagged_in_reasons():
    mentions = [_mention("EARN", tag="Bullish", hours_ago=i) for i in range(4)]
    series = _series("EARN", [20, 19, 17.5, 16, 15.2, 15.0])
    earnings_in_10_days = (NOW + timedelta(days=10)).date()
    candidate = find_dip_candidate(
        "EARN", [], mentions, series, now=NOW, earnings_date=earnings_in_10_days
    )
    assert candidate is not None
    assert candidate.earnings_date == earnings_in_10_days.isoformat()
    assert any("earnings" in r.lower() for r in candidate.reasons)


def test_earnings_outside_window_not_flagged():
    mentions = [_mention("EARN2", tag="Bullish", hours_ago=i) for i in range(4)]
    series = _series("EARN2", [20, 19, 17.5, 16, 15.2, 15.0])
    earnings_far_out = (NOW + timedelta(days=60)).date()
    candidate = find_dip_candidate(
        "EARN2", [], mentions, series, now=NOW, earnings_date=earnings_far_out
    )
    assert candidate is not None
    assert candidate.earnings_date is None
    assert not any("earnings" in r.lower() for r in candidate.reasons)


def test_rank_dip_candidates_sorts_most_oversold_first():
    mild_mentions = [_mention("MILD", tag="Bullish", hours_ago=i) for i in range(4)]
    deep_mentions = [_mention("DEEP", tag="Bullish", hours_ago=i) for i in range(4)]
    # Both clear the drop threshold; DEEP is far more oversold (lower RSI).
    mild = find_dip_candidate(
        "MILD", [], mild_mentions,
        _series("MILD", [30, 30.2, 29.9, 30.1, 28.5, 27.5, 27.0, 26.8, 26.6]),
        now=NOW,
    )
    deep = find_dip_candidate(
        "DEEP", [], deep_mentions,
        _series("DEEP", [30, 30.2, 29.9, 30.1, 24.0, 20.0, 17.0, 15.0, 14.0]),
        now=NOW,
    )
    assert mild is not None and deep is not None
    ranked = rank_dip_candidates([mild, deep])
    assert [c.ticker for c in ranked] == ["DEEP", "MILD"]
