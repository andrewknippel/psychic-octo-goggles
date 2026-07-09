from src.analysis.technical import TechnicalSnapshot
from src.models import PriceSeries


def _series(closes, volumes=None):
    volumes = volumes or [1_000_000] * len(closes)
    return PriceSeries(ticker="TEST", dates=[str(i) for i in range(len(closes))],
                        close=closes, volume=volumes)


def test_uptrend_yields_high_momentum_score():
    closes = [10, 10.1, 10.3, 10.6, 11.0, 11.5]
    snap = TechnicalSnapshot(_series(closes))
    assert snap.momentum_score > 60


def test_downtrend_yields_low_momentum_score():
    closes = [10, 9.9, 9.7, 9.4, 9.0, 8.5]
    snap = TechnicalSnapshot(_series(closes))
    assert snap.momentum_score < 40


def test_flat_series_momentum_near_neutral():
    closes = [10.0] * 10
    snap = TechnicalSnapshot(_series(closes))
    assert 45 <= snap.momentum_score <= 55


def test_volume_surge_above_baseline_scores_above_50():
    closes = [10.0] * 21
    volumes = [1_000_000] * 20 + [5_000_000]
    snap = TechnicalSnapshot(_series(closes, volumes))
    assert snap.volume_surge > 1
    assert snap.volume_score > 50


def test_volume_at_baseline_scores_near_50():
    closes = [10.0] * 21
    volumes = [1_000_000] * 21
    snap = TechnicalSnapshot(_series(closes, volumes))
    assert abs(snap.volume_score - 50) < 1


def test_extreme_overbought_rsi_penalizes_technical_score():
    # 8 straight up days, no losses at all -> RSI saturates at 100.
    closes = [10, 11, 12.2, 13.5, 15, 16.7, 18.5, 20.6]
    overbought = TechnicalSnapshot(_series(closes))
    assert overbought.rsi == 100.0

    # A healthier mixed uptrend (some down days) should score better on the
    # technical sub-score than a pinned-at-100 RSI, even though both are
    # trending up overall.
    mixed_closes = [10, 10.5, 10.3, 10.8, 10.6, 11.1, 11.4, 11.2]
    healthy = TechnicalSnapshot(_series(mixed_closes))
    assert healthy.technical_score > overbought.technical_score


def test_price_series_too_short_for_rsi_returns_none():
    snap = TechnicalSnapshot(_series([10, 10.5, 11]))
    assert snap.rsi is None
