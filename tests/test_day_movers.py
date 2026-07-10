from src.analysis.day_movers import find_day_mover, rank_day_movers, scan_for_day_movers
from src.models import PriceSeries


def _series(ticker, closes, volumes=None):
    volumes = volumes or [500_000] * len(closes)
    return PriceSeries(ticker=ticker, dates=[str(i) for i in range(len(closes))],
                        close=closes, volume=volumes)


def test_flat_day_is_not_a_mover():
    series = _series("FLAT", [10, 10.05, 10.1, 10.05, 10.1, 10.1])
    assert find_day_mover("FLAT", series) is None


def test_big_move_without_volume_surge_not_flagged():
    # +5% today, but volume is unchanged from the 20-day average.
    volumes = [1_000_000] * 20 + [1_000_000]
    closes = [10.0] * 20 + [10.5]
    assert find_day_mover("QUIETPOP", _series("QUIETPOP", closes, volumes)) is None


def test_big_move_with_volume_surge_is_flagged():
    volumes = [1_000_000] * 20 + [3_000_000]  # 3x surge
    closes = [10.0] * 20 + [10.6]  # +6% today
    mover = find_day_mover("POPPER", _series("POPPER", closes, volumes))
    assert mover is not None
    assert mover.change_1d_pct >= 3.0
    assert mover.volume_surge >= 1.5
    assert "POPPER" in mover.summary


def test_negative_day_not_flagged():
    volumes = [1_000_000] * 20 + [3_000_000]
    closes = [10.0] * 20 + [9.4]  # -6% today, big volume, but down not up
    assert find_day_mover("DROPPER", _series("DROPPER", closes, volumes)) is None


def test_illiquid_or_penny_mover_excluded():
    volumes = [400_000] * 20 + [1_200_000]
    closes = [2.0] * 20 + [2.2]
    assert find_day_mover("PENNY", _series("PENNY", closes, volumes)) is None


def test_no_price_series_returns_none():
    assert find_day_mover("X", None) is None


def test_scan_for_day_movers_accepts_4_and_5_tuples():
    volumes = [1_000_000] * 20 + [3_000_000]
    closes = [10.0] * 20 + [10.6]
    series = _series("POPPER", closes, volumes)
    batch_4 = [("POPPER", [], [], series)]
    batch_5 = [("POPPER", [], [], series, None)]
    assert {m.ticker for m in scan_for_day_movers(batch_4)} == {"POPPER"}
    assert {m.ticker for m in scan_for_day_movers(batch_5)} == {"POPPER"}


def test_rank_day_movers_sorts_biggest_gain_first():
    volumes = [1_000_000] * 20 + [3_000_000]
    small = find_day_mover("SMALL", _series("SMALL", [10.0] * 20 + [10.4], volumes))
    big = find_day_mover("BIG", _series("BIG", [10.0] * 20 + [11.5], volumes))
    assert small is not None and big is not None
    ranked = rank_day_movers([small, big])
    assert [m.ticker for m in ranked] == ["BIG", "SMALL"]
