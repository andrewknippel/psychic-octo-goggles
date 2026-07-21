import config
from src.analysis.buy_alerts import (
    fidelity_buy_url,
    is_buy_alert,
    select_buy_alerts,
)
from src.analysis.dip_scanner import DipCandidate


def _candidate(ticker, change_5d_pct, rsi):
    return DipCandidate(
        ticker=ticker,
        last_price=25.0,
        change_3d_pct=-3.0,
        change_5d_pct=change_5d_pct,
        rsi=rsi,
        sentiment_score=60.0,
        earnings_date=None,
        reasons=[f"down {change_5d_pct:.1f}% over 5 days"],
    )


def test_dip_with_low_rsi_and_big_drop_is_a_buy_alert():
    c = _candidate("BUY", change_5d_pct=-12.0, rsi=25.0)
    assert is_buy_alert(c) is True


def test_dip_without_low_rsi_is_not_a_buy_alert():
    # Cleared the weekly drop, but RSI is above the low-RSI bar -> not actionable.
    c = _candidate("MEH", change_5d_pct=-12.0, rsi=config.BUY_ALERT_RSI_MAX + 5)
    assert is_buy_alert(c) is False


def test_low_rsi_without_enough_drop_is_not_a_buy_alert():
    # Low RSI, but hasn't fallen the required amount over the week.
    c = _candidate("SHALLOW", change_5d_pct=-2.0, rsi=20.0)
    assert is_buy_alert(c) is False


def test_missing_rsi_is_not_a_buy_alert():
    c = _candidate("NORSI", change_5d_pct=-15.0, rsi=None)
    assert is_buy_alert(c) is False


def test_thresholds_are_inclusive_at_the_boundary():
    c = _candidate(
        "EDGE",
        change_5d_pct=-config.BUY_ALERT_DROP_PCT,   # exactly -8%
        rsi=config.BUY_ALERT_RSI_MAX,               # exactly at the low-RSI line
    )
    assert is_buy_alert(c) is True


def test_select_buy_alerts_filters_and_sorts_most_oversold_first():
    candidates = [
        _candidate("MILD", change_5d_pct=-9.0, rsi=30.0),
        _candidate("DEEP", change_5d_pct=-20.0, rsi=12.0),
        _candidate("SKIP_RSI", change_5d_pct=-11.0, rsi=55.0),   # RSI too high
        _candidate("SKIP_DROP", change_5d_pct=-1.0, rsi=15.0),   # drop too small
    ]
    alerts = select_buy_alerts(candidates)
    assert [a.ticker for a in alerts] == ["DEEP", "MILD"]


def test_buy_alert_carries_a_fidelity_buy_link_and_action_line():
    alerts = select_buy_alerts([_candidate("AAPL", change_5d_pct=-10.0, rsi=20.0)])
    assert len(alerts) == 1
    alert = alerts[0]
    assert "AAPL" in alert.fidelity_url
    assert "ORDER_ACTION=B" in alert.fidelity_url
    assert "AAPL" in alert.action


def test_fidelity_buy_url_uppercases_and_substitutes_symbol():
    url = fidelity_buy_url("tsla")
    assert "SYMBOL=TSLA" in url
    assert "ORDER_ACTION=B" in url
