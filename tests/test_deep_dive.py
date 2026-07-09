import random

from src.analysis.deep_dive import LongTermTechnicalSnapshot, build_recommendation
from src.models import CompanyInfo, PriceSeries


def _series(closes, volumes=None):
    volumes = volumes or [1_000_000] * len(closes)
    return PriceSeries(ticker="TEST", dates=[str(i) for i in range(len(closes))],
                        close=closes, volume=volumes)


def _noisy_trend(days=260, start=50.0, daily_drift_pct=0.15, seed=1):
    """A realistic trend: net drift plus daily noise (occasional red days),
    unlike a purely monotonic series which pins RSI at 0/100 and reads as
    maximally extended regardless of the underlying trend strength."""
    rng = random.Random(seed)
    closes = [start]
    for _ in range(days):
        pct = daily_drift_pct + rng.uniform(-0.6, 0.6)
        closes.append(round(closes[-1] * (1 + pct / 100), 4))
    return closes


def _steady_uptrend(days=260, start=50.0, daily_pct=0.15):
    return _noisy_trend(days, start, daily_drift_pct=daily_pct, seed=1)


def _steady_downtrend(days=260, start=200.0, daily_pct=0.15):
    return _noisy_trend(days, start, daily_drift_pct=-daily_pct, seed=2)


def test_uptrend_yields_high_trend_score():
    snap = LongTermTechnicalSnapshot(_series(_steady_uptrend()))
    assert snap.trend_score > 60
    assert snap.sma200 is not None
    assert snap.last_price > snap.sma200


def test_downtrend_yields_low_trend_score():
    up = LongTermTechnicalSnapshot(_series(_steady_uptrend()))
    down = LongTermTechnicalSnapshot(_series(_steady_downtrend()))
    assert down.trend_score < up.trend_score
    assert down.momentum_3m < 0
    assert down.last_price < down.sma200


def test_short_series_degrades_gracefully_no_crash():
    snap = LongTermTechnicalSnapshot(_series([10, 10.5, 11, 11.2, 10.8]))
    assert snap.sma200 is None
    assert snap.sma50 is None
    assert 0 <= snap.trend_score <= 100


def test_fifty_two_week_range_matches_lookback():
    closes = list(range(10, 40))  # rising 10..39
    snap = LongTermTechnicalSnapshot(_series([float(c) for c in closes]))
    assert snap.fifty_two_week_high == 39.0
    assert snap.fifty_two_week_low == 10.0


def test_recommendation_buy_more_on_strong_uptrend_and_sentiment():
    series = _series(_steady_uptrend())
    rec = build_recommendation("BULL", series, sentiment_score=80.0)
    assert rec.action == "BUY MORE"
    assert rec.overall_score > 68
    assert rec.stop_loss < rec.take_profit
    assert rec.hold_horizon.startswith("Long-term")


def test_recommendation_sell_on_death_cross_and_decline():
    # Long decline so sma50 < sma200 and 3-month momentum is sharply negative.
    series = _series(_steady_downtrend(days=260, start=200.0, daily_pct=0.4))
    rec = build_recommendation("BEAR", series, sentiment_score=20.0)
    assert rec.action == "SELL"


def test_recommendation_stop_loss_below_current_price():
    series = _series(_steady_uptrend())
    rec = build_recommendation("BULL", series, sentiment_score=None)
    assert rec.stop_loss < series.close[-1]
    assert rec.stop_loss_pct > 0


def test_recommendation_take_profit_uses_analyst_target_when_available():
    series = _series(_steady_uptrend(days=60))
    last_price = series.close[-1]
    info = CompanyInfo(ticker="BULL", target_mean_price=last_price * 1.5)
    rec = build_recommendation("BULL", series, sentiment_score=60.0, company_info=info)
    assert rec.take_profit == round(last_price * 1.5, 2)
    assert "analyst" in rec.take_profit_basis


def test_recommendation_no_sentiment_falls_back_to_trend_only():
    series = _series(_steady_uptrend())
    rec = build_recommendation("BULL", series, sentiment_score=None)
    assert rec.sentiment_score is None
    assert rec.overall_score == rec.trend_score


def test_extreme_overbought_caps_action_below_buy_more():
    # Sharp vertical spike -> very high RSI -- should not say "buy more"
    # into an extended blow-off top even though the trend score is high.
    closes = _steady_uptrend(days=200, start=50.0, daily_pct=0.1)
    spike = closes[-1]
    for _ in range(10):
        spike *= 1.08
        closes.append(round(spike, 4))
    rec = build_recommendation("HOT", _series(closes), sentiment_score=80.0)
    assert rec.action != "BUY MORE"
