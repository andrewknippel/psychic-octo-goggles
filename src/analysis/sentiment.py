"""Text sentiment scoring for news/social mentions.

Two signals are blended:
  * VADER compound sentiment on the raw text (works for any source).
  * StockTwits' explicit author-supplied Bullish/Bearish tag, which is
    trusted over VADER when present since it's a direct statement of
    intent rather than an inference from wording.

Each mention is weighted by recency (exponential decay tuned for a 2-7 day
holding window) and engagement (log-scaled likes/upvotes/comments) so one
old, unpopular post doesn't move the score as much as a fresh, widely-seen
one.
"""
import math
from datetime import datetime, timezone
from typing import List, Optional

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

import config
from src.models import Mention

_analyzer = SentimentIntensityAnalyzer()


def _recency_weight(ts: datetime, now: datetime) -> float:
    age_hours = max((now - ts).total_seconds() / 3600, 0)
    return 0.5 ** (age_hours / config.RECENCY_HALF_LIFE_HOURS)


def _engagement_weight(engagement: int) -> float:
    return 1.0 + math.log1p(max(engagement, 0))


def _mention_sentiment(mention: Mention) -> float:
    """Sentiment for a single mention in [-1, 1]."""
    if mention.explicit_sentiment == "Bullish":
        return 1.0
    if mention.explicit_sentiment == "Bearish":
        return -1.0
    if not mention.text.strip():
        return 0.0
    return _analyzer.polarity_scores(mention.text)["compound"]


def weighted_average_sentiment(
    mentions: List[Mention], now: Optional[datetime] = None
) -> Optional[float]:
    """Recency+engagement-weighted mean sentiment in [-1, 1], or None if empty."""
    if not mentions:
        return None
    now = now or datetime.now(timezone.utc)

    total_weight = 0.0
    weighted_sum = 0.0
    for mention in mentions:
        w = _recency_weight(mention.timestamp, now) * _engagement_weight(
            mention.engagement
        )
        weighted_sum += _mention_sentiment(mention) * w
        total_weight += w

    if total_weight == 0:
        return 0.0
    return weighted_sum / total_weight


def bullish_ratio(mentions: List[Mention]) -> Optional[float]:
    """Fraction of explicitly-tagged StockTwits messages that are Bullish."""
    tagged = [m for m in mentions if m.explicit_sentiment in ("Bullish", "Bearish")]
    if not tagged:
        return None
    bullish = sum(1 for m in tagged if m.explicit_sentiment == "Bullish")
    return bullish / len(tagged)


def compute_sentiment_score(
    news_mentions: List[Mention],
    social_mentions: List[Mention],
    now: Optional[datetime] = None,
) -> float:
    """Combined 0-100 sentiment score blending news and social sub-scores.

    Falls back to whichever source has data if the other is empty, instead
    of dragging the score toward a neutral midpoint for missing data.
    """
    news_sent = weighted_average_sentiment(news_mentions, now)
    social_sent = weighted_average_sentiment(social_mentions, now)

    if news_sent is None and social_sent is None:
        return 50.0  # neutral: no data either way

    if news_sent is None:
        combined = social_sent
    elif social_sent is None:
        combined = news_sent
    else:
        combined = (
            news_sent * config.SENTIMENT_NEWS_WEIGHT
            + social_sent * config.SENTIMENT_SOCIAL_WEIGHT
        )

    # Map [-1, 1] -> [0, 100]
    return (combined + 1) * 50
