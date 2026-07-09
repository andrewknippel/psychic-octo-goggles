import config
from src.analysis.fundamentals_scoring import rank_long_term, score_long_term_ticker
from src.models import Fundamentals, PriceSeries


def _series(ticker, closes):
    return PriceSeries(ticker=ticker, dates=[str(i) for i in range(len(closes))],
                        close=closes, volume=[1_000_000] * len(closes))


def _uptrend(start, annual_cagr_pct, days=756):
    daily_rate = (1 + annual_cagr_pct / 100) ** (1 / 252) - 1
    closes = [start]
    for _ in range(days - 1):
        closes.append(closes[-1] * (1 + daily_rate))
    return closes


def test_below_min_price_returns_none():
    f = Fundamentals(ticker="PENNY", current_price=1.0, market_cap=5_000_000_000)
    assert score_long_term_ticker("PENNY", f) is None


def test_below_min_market_cap_returns_none():
    f = Fundamentals(ticker="MICRO", current_price=20.0, market_cap=100_000_000)
    assert score_long_term_ticker("MICRO", f) is None


def test_no_fundamentals_returns_none():
    assert score_long_term_ticker("XYZ", None) is None


def test_quality_compounder_scores_higher_than_deteriorating_business():
    compound = Fundamentals(
        ticker="COMPOUND", current_price=200.0, market_cap=500_000_000_000,
        forward_pe=28.0, peg_ratio=1.3,
        revenue_growth=18.0, earnings_growth=20.0,
        profit_margins=25.0, operating_margins=30.0, return_on_equity=35.0,
        debt_to_equity=40.0, free_cashflow=10_000_000_000,
        recommendation_mean=1.8, target_mean_price=230.0, beta=1.1,
    )
    trap = Fundamentals(
        ticker="TRAP", current_price=22.0, market_cap=6_000_000_000,
        forward_pe=9.0, peg_ratio=None,
        revenue_growth=-8.0, earnings_growth=-18.0,
        profit_margins=2.0, operating_margins=4.0, return_on_equity=3.0,
        debt_to_equity=220.0, free_cashflow=-100_000_000,
        recommendation_mean=3.8, target_mean_price=20.0, beta=1.3,
    )
    compound_result = score_long_term_ticker("COMPOUND", compound, _series("COMPOUND", _uptrend(90, 22.0)))
    trap_result = score_long_term_ticker("TRAP", trap, _series("TRAP", _uptrend(55, -14.0)))

    assert compound_result is not None and trap_result is not None
    assert compound_result.final_score > trap_result.final_score


def test_high_debt_produces_risk_flag():
    f = Fundamentals(
        ticker="LEVERED", current_price=40.0, market_cap=10_000_000_000,
        debt_to_equity=220.0,
    )
    result = score_long_term_ticker("LEVERED", f)
    assert result is not None
    assert any("debt" in flag.lower() for flag in result.risk_flags)


def test_rich_valuation_via_peg_produces_risk_flag():
    f = Fundamentals(
        ticker="PRICEY", current_price=90.0, market_cap=20_000_000_000,
        peg_ratio=6.0,
    )
    result = score_long_term_ticker("PRICEY", f)
    assert result is not None
    assert any("valued" in flag.lower() for flag in result.risk_flags)


def test_rich_valuation_via_forward_pe_when_peg_missing():
    f = Fundamentals(
        ticker="PRICEY2", current_price=90.0, market_cap=20_000_000_000,
        peg_ratio=None, forward_pe=90.0,
    )
    result = score_long_term_ticker("PRICEY2", f)
    assert result is not None
    assert any("fwd p/e" in flag.lower() for flag in result.risk_flags)


def test_shrinking_business_produces_risk_flag():
    f = Fundamentals(
        ticker="SHRINK", current_price=30.0, market_cap=10_000_000_000,
        revenue_growth=-5.0, earnings_growth=-10.0,
    )
    result = score_long_term_ticker("SHRINK", f)
    assert result is not None
    assert any("shrinking" in flag.lower() for flag in result.risk_flags)


def test_thin_data_reduces_confidence_and_flags_coverage():
    thin = Fundamentals(ticker="THIN", current_price=40.0, market_cap=3_500_000_000)
    rich = Fundamentals(
        ticker="RICH", current_price=40.0, market_cap=3_500_000_000,
        forward_pe=20.0, peg_ratio=1.5,
        revenue_growth=10.0, earnings_growth=10.0,
        profit_margins=15.0, operating_margins=18.0, return_on_equity=20.0,
        debt_to_equity=60.0, free_cashflow=500_000_000,
        recommendation_mean=2.0, target_mean_price=45.0, beta=1.0,
    )
    thin_result = score_long_term_ticker("THIN", thin)
    rich_result = score_long_term_ticker("RICH", rich)

    assert thin_result is not None and rich_result is not None
    assert thin_result.confidence < rich_result.confidence
    assert any("data coverage" in flag.lower() for flag in thin_result.risk_flags)


def test_rank_long_term_sorts_descending_and_truncates():
    a = score_long_term_ticker(
        "A", Fundamentals(ticker="A", current_price=50.0, market_cap=10_000_000_000,
                           revenue_growth=15.0, earnings_growth=15.0, profit_margins=20.0)
    )
    b = score_long_term_ticker(
        "B", Fundamentals(ticker="B", current_price=50.0, market_cap=10_000_000_000,
                           revenue_growth=-15.0, earnings_growth=-15.0, profit_margins=-5.0)
    )
    ranked = rank_long_term([b, a], top_n=1)
    assert len(ranked) == 1
    assert ranked[0].ticker == "A"


def test_final_score_bounded_0_to_100():
    f = Fundamentals(
        ticker="BEST", current_price=50.0, market_cap=50_000_000_000,
        forward_pe=25.0, peg_ratio=1.0,
        revenue_growth=50.0, earnings_growth=50.0,
        profit_margins=40.0, operating_margins=40.0, return_on_equity=50.0,
        debt_to_equity=0.0, free_cashflow=1_000_000_000,
        recommendation_mean=1.0, target_mean_price=100.0, beta=1.0,
    )
    result = score_long_term_ticker("BEST", f, _series("BEST", _uptrend(10, 80.0)))
    assert result is not None
    assert 0 <= result.final_score <= 100


def test_market_cap_none_does_not_exclude():
    f = Fundamentals(ticker="NOCAP", current_price=50.0, market_cap=None)
    assert score_long_term_ticker("NOCAP", f) is not None
