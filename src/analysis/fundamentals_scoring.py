"""Composite scoring for the long-term (3-5 year) screen: combines growth,
profitability, financial health, valuation, analyst coverage, and long-run
price trend sub-scores into a single ranked signal.

    final_score = confidence * (
        LT_WEIGHT_GROWTH            * growth_score
      + LT_WEIGHT_PROFITABILITY     * profitability_score
      + LT_WEIGHT_FINANCIAL_HEALTH  * financial_health_score
      + LT_WEIGHT_VALUATION         * valuation_score
      + LT_WEIGHT_ANALYST           * analyst_score
      + LT_WEIGHT_TREND             * trend_score
    )

Unlike the short-term scorer's `confidence` (which down-weights low
mention-count tickers), here `confidence` reflects data completeness --
yfinance doesn't report every field for every company, and a score built
on 2 of 6 sub-scores shouldn't be trusted as much as one built on all 6.
Missing sub-scores fall back to a neutral 50 rather than being excluded,
so one missing field doesn't zero out an otherwise strong candidate.
"""
import statistics
from typing import List, Optional, Tuple

import config
from src.models import Fundamentals, LongTermScoreBreakdown, PriceSeries


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _growth_score(f: Fundamentals) -> Tuple[float, float]:
    """0-100: blends revenue and earnings growth. 0% growth -> 50;
    +20% -> ~90; -20% -> ~10."""
    parts = []
    if f.revenue_growth is not None:
        parts.append(_clamp(50 + f.revenue_growth * 2.5))
    if f.earnings_growth is not None:
        parts.append(_clamp(50 + f.earnings_growth * 2.0))
    if not parts:
        return 50.0, 0.0
    return sum(parts) / len(parts), 1.0


def _profitability_score(f: Fundamentals) -> Tuple[float, float]:
    """0-100: blends profit/operating margin and return on equity."""
    parts = []
    if f.profit_margins is not None:
        parts.append(_clamp(50 + f.profit_margins * 3.0))
    if f.operating_margins is not None:
        parts.append(_clamp(50 + f.operating_margins * 2.5))
    if f.return_on_equity is not None:
        parts.append(_clamp(50 + f.return_on_equity * 1.5))
    if not parts:
        return 50.0, 0.0
    return sum(parts) / len(parts), 1.0


def _financial_health_score(f: Fundamentals) -> Tuple[float, float]:
    """0-100: lower debt/equity is healthier for riding out a multi-year
    hold through rate/credit cycles; positive free cash flow nudges it up."""
    if f.debt_to_equity is None:
        return 50.0, 0.0
    score = _clamp(100 - f.debt_to_equity * 0.3)
    if f.free_cashflow is not None:
        score = _clamp(score + (5 if f.free_cashflow > 0 else -10))
    return score, 1.0


def _valuation_score(f: Fundamentals) -> Tuple[float, float]:
    """0-100: PEG ratio (P/E adjusted for growth) is the primary signal --
    ~1.0 is "fairly priced for its growth rate". Falls back to a cruder
    forward-P/E-only heuristic (lower confidence) when PEG is unavailable."""
    if f.peg_ratio is not None and f.peg_ratio > 0:
        return _clamp(100 - abs(f.peg_ratio - 1.0) * 30), 1.0
    if f.forward_pe is not None and f.forward_pe > 0:
        return _clamp(130 - f.forward_pe * 2.0), 0.6
    return 50.0, 0.0


def _analyst_score(f: Fundamentals) -> Tuple[float, float]:
    """0-100: blends the average analyst recommendation (1=Strong Buy,
    5=Sell) with implied upside to the mean 12-month price target."""
    parts = []
    if f.recommendation_mean is not None:
        parts.append(_clamp(100 - (f.recommendation_mean - 1) * 25))
    if f.target_mean_price is not None and f.current_price:
        upside = (f.target_mean_price - f.current_price) / f.current_price * 100
        parts.append(_clamp(50 + upside * 1.5))
    if not parts:
        return 50.0, 0.0
    return sum(parts) / len(parts), 1.0


def _trend_score(series: Optional[PriceSeries]) -> Tuple[float, float]:
    """0-100: blends multi-year CAGR with the trailing 1-year return, as a
    (backward-looking) proxy for sustained business quality -- weighted
    lightly since past returns don't guarantee future ones."""
    if series is None or len(series.close) < 60:
        return 50.0, 0.0

    closes = series.close
    years = len(closes) / 252.0
    cagr_pct = (
        ((closes[-1] / closes[0]) ** (1 / years) - 1) * 100
        if years > 0 and closes[0] > 0 else 0.0
    )
    one_year_idx = max(0, len(closes) - 252)
    one_year_return_pct = (
        (closes[-1] - closes[one_year_idx]) / closes[one_year_idx] * 100
        if closes[one_year_idx] else 0.0
    )

    cagr_score = _clamp(50 + cagr_pct * 2.2)
    one_year_score = _clamp(50 + one_year_return_pct * 1.0)
    return cagr_score * 0.6 + one_year_score * 0.4, 1.0


def _risk_flags(f: Fundamentals, completeness: float) -> List[str]:
    """Annotations, not scoring inputs -- they never change a ticker's rank,
    they just stop a high score from being mistaken for a low-risk one."""
    flags = []

    if f.debt_to_equity is not None and f.debt_to_equity >= config.LT_RISK_DEBT_TO_EQUITY:
        flags.append(f"High debt load (D/E {f.debt_to_equity:.0f}%)")

    if f.peg_ratio is not None and f.peg_ratio >= config.LT_RISK_PEG:
        flags.append(f"Richly valued (PEG {f.peg_ratio:.1f})")
    elif f.peg_ratio is None and f.forward_pe is not None and f.forward_pe >= config.LT_RISK_FORWARD_PE:
        flags.append(f"Richly valued (fwd P/E {f.forward_pe:.0f})")

    if (
        f.revenue_growth is not None and f.revenue_growth < 0
        and f.earnings_growth is not None and f.earnings_growth < 0
    ):
        flags.append("Revenue and earnings both shrinking")

    if f.recommendation_mean is not None and f.recommendation_mean >= config.LT_RISK_ANALYST_RATING:
        flags.append(f"Weak analyst sentiment (avg rating {f.recommendation_mean:.1f}/5)")

    if f.beta is not None and f.beta >= config.LT_RISK_BETA:
        flags.append(f"High volatility stock (beta {f.beta:.1f})")

    if completeness < 0.5:
        flags.append("Thin fundamentals data coverage")

    return flags


def _build_rationale(f: Fundamentals, risk_flags: List[str]) -> str:
    parts = []

    if f.revenue_growth is not None and f.earnings_growth is not None:
        parts.append(f"{f.revenue_growth:+.0f}% revenue / {f.earnings_growth:+.0f}% earnings growth")
    elif f.revenue_growth is not None:
        parts.append(f"{f.revenue_growth:+.0f}% revenue growth")

    if f.profit_margins is not None:
        parts.append(f"{f.profit_margins:.0f}% profit margin")

    if f.peg_ratio is not None:
        parts.append(f"PEG {f.peg_ratio:.1f}")
    elif f.forward_pe is not None:
        parts.append(f"fwd P/E {f.forward_pe:.0f}")

    if f.recommendation_mean is not None:
        parts.append(f"analyst avg rating {f.recommendation_mean:.1f}/5")

    rationale = ("; ".join(parts) + ".") if parts else "Limited fundamentals data available."
    if risk_flags:
        rationale += " Risk: " + "; ".join(risk_flags) + "."
    return rationale


def score_long_term_ticker(
    ticker: str,
    fundamentals: Optional[Fundamentals],
    price_series: Optional[PriceSeries] = None,
) -> Optional[LongTermScoreBreakdown]:
    """Returns a LongTermScoreBreakdown, or None if the ticker fails minimum
    price/market-cap thresholds and shouldn't be ranked."""
    if fundamentals is None or fundamentals.current_price is None:
        return None
    if fundamentals.current_price < config.MIN_PRICE:
        return None
    if fundamentals.market_cap is not None and fundamentals.market_cap < config.LT_MIN_MARKET_CAP:
        return None

    growth_score, growth_conf = _growth_score(fundamentals)
    profitability_score, profitability_conf = _profitability_score(fundamentals)
    health_score, health_conf = _financial_health_score(fundamentals)
    valuation_score, valuation_conf = _valuation_score(fundamentals)
    analyst_score, analyst_conf = _analyst_score(fundamentals)
    trend_score, trend_conf = _trend_score(price_series)

    completeness = statistics.mean(
        [growth_conf, profitability_conf, health_conf, valuation_conf, analyst_conf, trend_conf]
    )
    confidence = _clamp(0.4 + 0.6 * completeness, 0.0, 1.0)

    composite = (
        config.LT_WEIGHT_GROWTH * growth_score
        + config.LT_WEIGHT_PROFITABILITY * profitability_score
        + config.LT_WEIGHT_FINANCIAL_HEALTH * health_score
        + config.LT_WEIGHT_VALUATION * valuation_score
        + config.LT_WEIGHT_ANALYST * analyst_score
        + config.LT_WEIGHT_TREND * trend_score
    )
    final_score = composite * confidence

    risk_flags = _risk_flags(fundamentals, completeness)
    analyst_upside_pct = None
    if fundamentals.target_mean_price is not None and fundamentals.current_price:
        analyst_upside_pct = (
            (fundamentals.target_mean_price - fundamentals.current_price)
            / fundamentals.current_price * 100
        )

    return LongTermScoreBreakdown(
        ticker=ticker,
        final_score=round(final_score, 2),
        growth_score=round(growth_score, 2),
        profitability_score=round(profitability_score, 2),
        financial_health_score=round(health_score, 2),
        valuation_score=round(valuation_score, 2),
        analyst_score=round(analyst_score, 2),
        trend_score=round(trend_score, 2),
        confidence=round(confidence, 2),
        data_completeness=round(completeness, 2),
        current_price=round(fundamentals.current_price, 2),
        market_cap=fundamentals.market_cap,
        sector=fundamentals.sector,
        revenue_growth_pct=fundamentals.revenue_growth,
        earnings_growth_pct=fundamentals.earnings_growth,
        peg_ratio=fundamentals.peg_ratio,
        forward_pe=fundamentals.forward_pe,
        debt_to_equity=fundamentals.debt_to_equity,
        analyst_upside_pct=round(analyst_upside_pct, 1) if analyst_upside_pct is not None else None,
        risk_flags=risk_flags,
        rationale=_build_rationale(fundamentals, risk_flags),
    )


def rank_long_term(scores: List[LongTermScoreBreakdown], top_n: int = 10) -> List[LongTermScoreBreakdown]:
    return sorted(scores, key=lambda s: s.final_score, reverse=True)[:top_n]
