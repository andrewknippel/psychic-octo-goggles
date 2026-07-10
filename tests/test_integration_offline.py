"""End-to-end pipeline test using the bundled synthetic dataset -- exercises
discovery-free scoring against realistic-shaped data without any network
calls, so it runs anywhere (including network-restricted CI/sandboxes)."""
from src.analysis.dip_scanner import scan_for_dips
from src.analysis.scoring import rank_tickers, score_ticker
from src.sample_data import generate_offline_dataset


def _score_all():
    dataset = generate_offline_dataset()
    scores = []
    for ticker, (news_mentions, social_mentions, price_series, earnings_date) in dataset.items():
        result = score_ticker(
            ticker, news_mentions, social_mentions, price_series, earnings_date=earnings_date
        )
        if result is not None:
            scores.append(result)
    return scores


def test_quiet_ticker_filtered_out_for_low_mentions():
    scores = _score_all()
    tickers = {s.ticker for s in scores}
    assert "QUIET" not in tickers


def test_bearish_ticker_ranks_last():
    ranked = rank_tickers(_score_all(), top_n=10)
    assert ranked[-1].ticker == "BAGGY"


def test_bullish_tickers_outrank_bearish_and_slow():
    ranked = rank_tickers(_score_all(), top_n=10)
    order = [s.ticker for s in ranked]
    assert order.index("MOMO") < order.index("BAGGY")
    assert order.index("TOPPY") < order.index("BAGGY")
    assert order.index("MOMO") < order.index("SLOW")


def test_every_score_has_a_rationale_string():
    for s in _score_all():
        assert isinstance(s.rationale, str) and len(s.rationale) > 0


def test_toppy_carries_overbought_and_earnings_risk_flags():
    scores = {s.ticker: s for s in _score_all()}
    toppy = scores["TOPPY"]
    assert any("Overbought" in f for f in toppy.risk_flags)
    assert any("Earnings" in f for f in toppy.risk_flags)
    assert toppy.volatility_pct is not None and toppy.volatility_pct > 0


def test_slow_ticker_has_no_earnings_flag_and_fewer_risk_flags_than_toppy():
    scores = {s.ticker: s for s in _score_all()}
    assert scores["SLOW"].earnings_date is None
    assert len(scores["SLOW"].risk_flags) < len(scores["TOPPY"].risk_flags)


def _raw_data():
    dataset = generate_offline_dataset()
    return [
        (ticker, news_mentions, social_mentions, price_series, earnings_date)
        for ticker, (news_mentions, social_mentions, price_series, earnings_date)
        in dataset.items()
    ]


def test_dip_watch_flags_dippy_but_not_the_bearish_falling_knife():
    dip_tickers = {c.ticker for c in scan_for_dips(_raw_data())}
    assert "DIPPY" in dip_tickers
    assert "BAGGY" not in dip_tickers


def test_dippy_rebound_candidate_carries_earnings_flag():
    candidates = {c.ticker: c for c in scan_for_dips(_raw_data())}
    dippy = candidates["DIPPY"]
    assert dippy.earnings_date is not None
    assert any("earnings" in r.lower() for r in dippy.reasons)
