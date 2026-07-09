"""Composite scoring: combines sentiment, momentum, buzz, and technical
sub-scores into a single ranked signal for short-term (2-7 day) growth.

    final_score = confidence * (
        WEIGHT_SENTIMENT * sentiment_score
      + WEIGHT_MOMENTUM  * momentum_score
      + WEIGHT_BUZZ      * buzz_score
      + WEIGHT_TECHNICAL * technical_score
    )

`confidence` down-weights tickers backed by very few mentions, so a single
hyperbolic Reddit post can't rocket an obscure ticker to the top of the
list purely on noise.
"""
import math
from datetime import datetime, timezone
from typing import List, Optional

import config
from src.analysis.sentiment import bullish_ratio, compute_sentiment_score
from src.analysis.technical import TechnicalSnapshot
from src.models import Mention, PriceSeries, ScoreBreakdown


def _mention_count_score(count: int) -> float:
    saturation = config.MENTION_CONFIDENCE_SATURATION
    return min(100.0, 100 * math.log1p(count) / math.log1p(saturation))


def _confidence(count: int) -> float:
    saturation = config.MENTION_CONFIDENCE_SATURATION
    return min(1.0, math.log1p(count) / math.log1p(saturation))


def _build_rationale(
    ticker: str,
    sentiment_score: float,
    tech: TechnicalSnapshot,
    ratio: Optional[float],
    mention_count: int,
) -> str:
    parts = []

    if ratio is not None:
        parts.append(f"{ratio * 100:.0f}% bullish across {mention_count} social mentions")
    else:
        lean = "bullish" if sentiment_score >= 55 else "bearish" if sentiment_score <= 45 else "neutral"
        parts.append(f"{lean} sentiment across {mention_count} mentions")

    if tech.change_3d_pct is not None:
        parts.append(f"{tech.change_3d_pct:+.1f}% over 3 days")
    if tech.volume_surge:
        parts.append(f"{tech.volume_surge:.1f}x normal trading volume")
    if tech.rsi is not None:
        parts.append(f"RSI {tech.rsi:.0f}")

    return "; ".join(parts) + "."


def score_ticker(
    ticker: str,
    news_mentions: List[Mention],
    social_mentions: List[Mention],
    price_series: Optional[PriceSeries],
    now: Optional[datetime] = None,
) -> Optional[ScoreBreakdown]:
    """Returns a ScoreBreakdown, or None if the ticker fails minimum data /
    liquidity requirements and shouldn't be ranked."""
    now = now or datetime.now(timezone.utc)
    all_mentions = news_mentions + social_mentions
    mention_count = len(all_mentions)

    if mention_count < config.MIN_MENTIONS:
        return None
    if price_series is None:
        return None

    tech = TechnicalSnapshot(price_series)

    if tech.last_price < config.MIN_PRICE:
        return None
    if tech.avg_volume_20 and tech.avg_volume_20 < config.MIN_AVG_VOLUME:
        return None

    sentiment_score = compute_sentiment_score(news_mentions, social_mentions, now)
    ratio = bullish_ratio(social_mentions)

    buzz_score = (
        tech.volume_score * 0.5 + _mention_count_score(mention_count) * 0.5
    )

    confidence = _confidence(mention_count)

    composite = (
        config.WEIGHT_SENTIMENT * sentiment_score
        + config.WEIGHT_MOMENTUM * tech.momentum_score
        + config.WEIGHT_BUZZ * buzz_score
        + config.WEIGHT_TECHNICAL * tech.technical_score
    )
    final_score = composite * confidence

    return ScoreBreakdown(
        ticker=ticker,
        final_score=round(final_score, 2),
        sentiment_score=round(sentiment_score, 2),
        momentum_score=round(tech.momentum_score, 2),
        buzz_score=round(buzz_score, 2),
        technical_score=round(tech.technical_score, 2),
        confidence=round(confidence, 2),
        mention_count=mention_count,
        last_price=round(tech.last_price, 2),
        change_3d_pct=round(tech.change_3d_pct, 2) if tech.change_3d_pct is not None else 0.0,
        change_5d_pct=round(tech.change_5d_pct, 2) if tech.change_5d_pct is not None else 0.0,
        bullish_ratio=round(ratio, 2) if ratio is not None else None,
        volume_surge=round(tech.volume_surge, 2),
        rsi=round(tech.rsi, 1) if tech.rsi is not None else None,
        rationale=_build_rationale(ticker, sentiment_score, tech, ratio, mention_count),
    )


def rank_tickers(scores: List[ScoreBreakdown], top_n: int = 10) -> List[ScoreBreakdown]:
    return sorted(scores, key=lambda s: s.final_score, reverse=True)[:top_n]
