from datetime import datetime, timedelta, timezone

from src.analysis.sentiment import (
    bullish_ratio,
    compute_sentiment_score,
    weighted_average_sentiment,
)
from src.models import Mention

NOW = datetime.now(timezone.utc)


def _mention(text="", tag=None, hours_ago=1, engagement=10, source="news"):
    return Mention(
        ticker="TEST",
        source=source,
        text=text,
        timestamp=NOW - timedelta(hours=hours_ago),
        engagement=engagement,
        explicit_sentiment=tag,
    )


def test_weighted_average_sentiment_empty_returns_none():
    assert weighted_average_sentiment([]) is None


def test_explicit_bullish_tag_dominates_over_neutral_text():
    mentions = [_mention(text="just an update", tag="Bullish")]
    score = weighted_average_sentiment(mentions, now=NOW)
    assert score == 1.0


def test_explicit_bearish_tag_dominates():
    mentions = [_mention(text="just an update", tag="Bearish")]
    score = weighted_average_sentiment(mentions, now=NOW)
    assert score == -1.0


def test_older_mentions_are_downweighted():
    recent_bullish = _mention(tag="Bullish", hours_ago=1)
    old_bearish = _mention(tag="Bearish", hours_ago=500)
    score = weighted_average_sentiment([recent_bullish, old_bearish], now=NOW)
    assert score > 0.9  # old bearish mention should barely move the average


def test_bullish_ratio_only_counts_tagged_messages():
    mentions = [
        _mention(tag="Bullish"),
        _mention(tag="Bullish"),
        _mention(tag="Bearish"),
        _mention(tag=None),  # untagged, excluded from ratio
    ]
    assert bullish_ratio(mentions) == 2 / 3


def test_bullish_ratio_none_when_nothing_tagged():
    assert bullish_ratio([_mention(tag=None)]) is None


def test_compute_sentiment_score_neutral_when_no_data():
    assert compute_sentiment_score([], [], now=NOW) == 50.0


def test_compute_sentiment_score_falls_back_to_available_source():
    social = [_mention(tag="Bullish")]
    score = compute_sentiment_score([], social, now=NOW)
    assert score == 100.0  # (+1 -> 100 on the 0-100 scale)


def test_compute_sentiment_score_blends_news_and_social():
    news = [_mention(text="Company beats on strong earnings and raises guidance")]
    social = [_mention(tag="Bearish")]
    score = compute_sentiment_score(news, social, now=NOW)
    assert 0 <= score <= 100
