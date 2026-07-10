from datetime import date, timedelta

from src.analysis.forecast import (
    HORIZON_DAYS,
    MIN_TRAINING_ROWS,
    WARMUP_DAYS,
    _add_trading_days,
    _rsi_at,
    _sma_at,
    _volatility_at,
    analyze_price_series,
    synthetic_price_series,
)
from src.models import PriceSeries


def _series(closes, volumes=None, ticker="TEST"):
    volumes = volumes or [1_000_000] * len(closes)
    dates = [str(date(2020, 1, 1) + timedelta(days=i)) for i in range(len(closes))]
    return PriceSeries(ticker=ticker, dates=dates, close=closes, volume=volumes)


def test_rsi_at_matches_manual_uptrend():
    closes = [10, 10.5, 11, 11.6, 12.3, 13.1, 14.0, 14.5, 15.1, 15.6, 16.2, 16.9, 17.5, 18.2, 19.0]
    rsi = _rsi_at(closes, len(closes) - 1, period=14)
    assert rsi is not None
    assert rsi > 60  # sustained uptrend -> high RSI


def test_rsi_at_none_when_too_short():
    assert _rsi_at([10, 10.5, 11], 2, period=14) is None


def test_sma_at_basic():
    closes = [1, 2, 3, 4, 5]
    assert _sma_at(closes, 4, period=5) == 3.0
    assert _sma_at(closes, 3, period=5) is None


def test_volatility_at_choppy_higher_than_smooth():
    smooth = [10 + i * 0.05 for i in range(25)]
    choppy = [10 + (1 if i % 2 == 0 else -1) for i in range(25)]
    v_smooth = _volatility_at(smooth, 24, period=20)
    v_choppy = _volatility_at(choppy, 24, period=20)
    assert v_smooth is not None and v_choppy is not None
    assert v_choppy > v_smooth


def test_add_trading_days_skips_weekends():
    # Friday 2024-01-05 + 1 trading day -> Monday 2024-01-08
    friday = date(2024, 1, 5)
    assert _add_trading_days(friday, 1) == date(2024, 1, 8)
    assert _add_trading_days(friday, 5) == date(2024, 1, 12)


def test_too_short_series_returns_none():
    series = _series([10.0] * (WARMUP_DAYS + HORIZON_DAYS + MIN_TRAINING_ROWS - 5))
    assert analyze_price_series(series) is None


def test_synthetic_series_produces_full_result():
    series = synthetic_price_series("DEMO", days=1260, seed=42)
    result = analyze_price_series(series, k=40)
    assert result is not None
    assert result.ticker == "DEMO"
    assert len(result.day_forecasts) == HORIZON_DAYS
    assert 0.0 <= result.prob_gain_within_week_pct <= 100.0
    assert 1 <= result.best_sell_day <= HORIZON_DAYS
    assert result.neighbors_used <= 40
    assert result.analog_pool_size >= MIN_TRAINING_ROWS
    for d in result.day_forecasts:
        assert 0.0 <= d.prob_positive_pct <= 100.0


def test_limited_history_adds_note_and_smaller_k():
    # Enough for the minimum training pool, but well under the default k=40.
    days = WARMUP_DAYS + HORIZON_DAYS + MIN_TRAINING_ROWS + 5
    series = synthetic_price_series("THIN", days=days, seed=3)
    result = analyze_price_series(series, k=40)
    assert result is not None
    assert result.neighbors_used < 40
    assert any("Limited history" in note for note in result.notes)


def test_strong_sustained_uptrend_scores_higher_than_downtrend():
    # Both series share the same up-then-down history, so the analog pool is
    # identical; only the *tail* (today's setup) differs -- uptrending vs
    # downtrending -- which should meaningfully shift the forecast in that
    # historical dataset's own terms, not against an absolute threshold.
    base = []
    price = 100.0
    for i in range(400):
        # Oscillating regime so both up and down setups exist in history.
        pct = 0.6 if (i // 20) % 2 == 0 else -0.6
        price *= 1 + pct / 100
        base.append(round(price, 2))

    up_tail = list(base)
    p = up_tail[-1]
    for _ in range(10):
        p *= 1.01
        up_tail.append(round(p, 2))

    down_tail = list(base)
    p = down_tail[-1]
    for _ in range(10):
        p *= 0.99
        down_tail.append(round(p, 2))

    up_series = _series(up_tail, ticker="UP")
    down_series = _series(down_tail, ticker="DOWN")

    up_result = analyze_price_series(up_series, k=40)
    down_result = analyze_price_series(down_series, k=40)

    assert up_result is not None and down_result is not None
    # An uptrending tail should look for analogs among historical up-legs
    # (which kept rising), a downtrending tail among down-legs (which kept
    # falling) -- so the up case should come out more bullish.
    assert up_result.prob_gain_within_week_pct >= down_result.prob_gain_within_week_pct
