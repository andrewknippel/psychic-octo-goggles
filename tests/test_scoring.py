from datetime import datetime, timedelta, timezone

import config
from src.analysis.scoring import rank_tickers, score_ticker
from src.models import Mention, PriceSeries

NOW = datetime.now(timezone.utc)


def _mention(ticker, tag=None, text="", source="stocktwits", hours_ago=1):
    return Mention(
        ticker=ticker, source=source, text=text,
        timestamp=NOW - timedelta(hours=hours_ago), engagement=10,
        explicit_sentiment=tag,
    )


def _series(ticker, closes, volumes=None):
    volumes = volumes or [500_000] * len(closes)
    return PriceSeries(ticker=ticker, dates=[str(i) for i in range(len(closes))],
                        close=closes, volume=volumes)


def test_below_min_mentions_returns_none():
    mentions = [_mention("XYZ", tag="Bullish")]  # only 1, below default MIN_MENTIONS
    series = _series("XYZ", [10, 10.5, 11, 11.5, 12])
    result = score_ticker("XYZ", [], mentions, series, now=NOW)
    assert result is None


def test_below_min_price_returns_none():
    mentions = [_mention("PENNY", tag="Bullish", hours_ago=i) for i in range(5)]
    series = _series("PENNY", [0.5, 0.55, 0.6, 0.65, 0.7])  # below MIN_PRICE
    result = score_ticker("PENNY", [], mentions, series, now=NOW)
    assert result is None


def test_penny_stock_threshold_is_five_dollars():
    # $4 stock: not a fraction-of-a-dollar penny stock, but still below the
    # $5 SEC/industry line this tool uses to exclude penny stocks entirely.
    mentions = [_mention("CHEAP", tag="Bullish", hours_ago=i) for i in range(5)]
    series = _series("CHEAP", [4.0, 4.05, 4.1, 4.15, 4.2], volumes=[500_000] * 5)
    assert config.MIN_PRICE == 5.0
    assert score_ticker("CHEAP", [], mentions, series, now=NOW) is None

    # $5.50 stock, otherwise identical -- should NOT be excluded on price.
    series_ok = _series("OK", [5.5, 5.55, 5.6, 5.65, 5.7], volumes=[500_000] * 5)
    mentions_ok = [_mention("OK", tag="Bullish", hours_ago=i) for i in range(5)]
    assert score_ticker("OK", [], mentions_ok, series_ok, now=NOW) is not None


def test_below_min_volume_returns_none():
    mentions = [_mention("ILLIQ", tag="Bullish", hours_ago=i) for i in range(5)]
    series = _series("ILLIQ", list(range(20, 40)), volumes=[1000] * 20)  # far below MIN_AVG_VOLUME
    result = score_ticker("ILLIQ", [], mentions, series, now=NOW)
    assert result is None


def test_no_price_series_returns_none():
    mentions = [_mention("XYZ", tag="Bullish", hours_ago=i) for i in range(5)]
    result = score_ticker("XYZ", [], mentions, None, now=NOW)
    assert result is None


def test_bullish_ticker_scores_higher_than_bearish():
    bull_mentions = [_mention("BULL", tag="Bullish", hours_ago=i) for i in range(5)]
    bull_series = _series("BULL", [10, 10.5, 11, 11.8, 12.5, 13.2])

    bear_mentions = [_mention("BEAR", tag="Bearish", hours_ago=i) for i in range(5)]
    bear_series = _series("BEAR", [10, 9.5, 9, 8.5, 8, 7.5])

    bull = score_ticker("BULL", [], bull_mentions, bull_series, now=NOW)
    bear = score_ticker("BEAR", [], bear_mentions, bear_series, now=NOW)

    assert bull is not None and bear is not None
    assert bull.final_score > bear.final_score


def test_final_score_bounded_0_to_100():
    mentions = [_mention("BULL", tag="Bullish", hours_ago=i) for i in range(20)]
    series = _series("BULL", [10 * (1.05 ** i) for i in range(15)],
                      volumes=[1_000_000] * 14 + [10_000_000])
    result = score_ticker("BULL", [], mentions, series, now=NOW)
    assert result is not None
    assert 0 <= result.final_score <= 100


def test_rank_tickers_sorts_descending_and_truncates():
    a = score_ticker(
        "A", [], [_mention("A", tag="Bullish", hours_ago=i) for i in range(5)],
        _series("A", [10, 10.5, 11, 11.5, 12]), now=NOW,
    )
    b = score_ticker(
        "B", [], [_mention("B", tag="Bearish", hours_ago=i) for i in range(5)],
        _series("B", [10, 9.5, 9, 8.5, 8]), now=NOW,
    )
    ranked = rank_tickers([b, a], top_n=1)
    assert len(ranked) == 1
    assert ranked[0].ticker == "A"


def test_low_mention_count_is_penalized_via_confidence(monkeypatch):
    monkeypatch.setattr(config, "MIN_MENTIONS", 1)
    series = _series("X", [10, 10.5, 11, 11.5, 12, 12.5])

    few = score_ticker(
        "X", [], [_mention("X", tag="Bullish", hours_ago=0)], series, now=NOW
    )
    many = score_ticker(
        "X", [], [_mention("X", tag="Bullish", hours_ago=i) for i in range(30)],
        series, now=NOW,
    )
    assert few.confidence < many.confidence
    assert few.final_score < many.final_score


def test_overbought_series_produces_risk_flag():
    mentions = [_mention("HOT", tag="Bullish", hours_ago=i) for i in range(5)]
    # 8 straight up days, no down days -> RSI saturates at 100.
    closes = [10, 11, 12.2, 13.5, 15, 16.7, 18.5, 20.6]
    series = _series("HOT", closes)
    result = score_ticker("HOT", [], mentions, series, now=NOW)
    assert result is not None
    assert any("Overbought" in f for f in result.risk_flags)


def test_downtrend_series_produces_oversold_flag():
    mentions = [_mention("COLD", tag="Bearish", hours_ago=i) for i in range(5)]
    closes = [20.6, 18.5, 16.7, 15, 13.5, 12.2, 11, 10]
    series = _series("COLD", closes)
    result = score_ticker("COLD", [], mentions, series, now=NOW)
    assert result is not None
    assert any("Oversold" in f for f in result.risk_flags)


def test_earnings_within_window_produces_risk_flag():
    mentions = [_mention("EARN", tag="Bullish", hours_ago=i) for i in range(5)]
    series = _series("EARN", [10, 10.2, 10.1, 10.3, 10.2, 10.4])
    earnings_in_3_days = (NOW + timedelta(days=3)).date()
    result = score_ticker(
        "EARN", [], mentions, series, now=NOW, earnings_date=earnings_in_3_days
    )
    assert result is not None
    assert any("Earnings" in f for f in result.risk_flags)
    assert result.earnings_date == earnings_in_3_days.isoformat()


def test_earnings_outside_window_produces_no_earnings_flag():
    mentions = [_mention("FAR", tag="Bullish", hours_ago=i) for i in range(5)]
    series = _series("FAR", [10, 10.2, 10.1, 10.3, 10.2, 10.4])
    earnings_far_out = (NOW + timedelta(days=30)).date()
    result = score_ticker(
        "FAR", [], mentions, series, now=NOW, earnings_date=earnings_far_out
    )
    assert result is not None
    assert not any("Earnings" in f for f in result.risk_flags)


def test_no_earnings_date_means_no_earnings_flag():
    mentions = [_mention("NOEARN", tag="Bullish", hours_ago=i) for i in range(5)]
    series = _series("NOEARN", [10, 10.2, 10.1, 10.3, 10.2, 10.4])
    result = score_ticker("NOEARN", [], mentions, series, now=NOW, earnings_date=None)
    assert result is not None
    assert result.earnings_date is None
    assert not any("Earnings" in f for f in result.risk_flags)
