"""End-to-end pipeline test using the bundled synthetic dataset -- exercises
discovery-free scoring against realistic-shaped data without any network
calls, so it runs anywhere (including network-restricted CI/sandboxes)."""
from src.analysis.scoring import rank_tickers, score_ticker
from src.sample_data import generate_offline_dataset


def _score_all():
    dataset = generate_offline_dataset()
    scores = []
    for ticker, (news_mentions, social_mentions, price_series) in dataset.items():
        result = score_ticker(ticker, news_mentions, social_mentions, price_series)
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
