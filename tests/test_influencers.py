"""Tests for the market-mover ("powerful businessmen") news feed helpers.

The network fetch itself isn't exercised here (it hits a live keyless RSS
endpoint); these cover the pure parsing/formatting logic and the offline
sample feed used by the dashboard's demo mode."""
from datetime import datetime, timezone

from src.data_sources.influencers import (
    InfluencerPost,
    _parse_rfc822,
    _strip_html,
    parse_figures,
)
from src.sample_data import generate_offline_influencer_feed


def test_parse_figures_splits_name_and_role():
    figures = parse_figures("Elon Musk|Tesla CEO,Jerome Powell|Fed Chair")
    assert figures == [("Elon Musk", "Tesla CEO"), ("Jerome Powell", "Fed Chair")]


def test_parse_figures_tolerates_missing_role_and_blanks():
    figures = parse_figures("Warren Buffett, ,Cathie Wood|ARK CEO")
    assert ("Warren Buffett", "") in figures
    assert ("Cathie Wood", "ARK CEO") in figures
    assert len(figures) == 2  # the empty chunk is dropped


def test_strip_html_reduces_to_plain_snippet():
    raw = '<a href="x">Powell</a> says <b>rates</b> hold&nbsp;steady'
    cleaned = _strip_html(raw)
    assert "<" not in cleaned and ">" not in cleaned
    assert "Powell" in cleaned and "rates" in cleaned


def test_parse_rfc822_handles_google_news_format():
    dt = _parse_rfc822("Sat, 11 Jul 2026 14:30:00 GMT")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 7 and dt.day == 11
    assert dt.tzinfo is not None


def test_influencer_post_to_dict_is_json_shaped():
    post = InfluencerPost(
        name="Jensen Huang",
        role="Nvidia CEO",
        headline="AI demand strong",
        source="CNBC",
        url="https://example.com/a",
        timestamp=datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc),
        snippet="snippet",
    )
    d = post.to_dict()
    assert d["name"] == "Jensen Huang"
    assert d["published_at"].startswith("2026-07-11T12:00:00")
    assert set(d) == {"name", "role", "headline", "source", "url", "published_at", "snippet"}


def test_offline_feed_is_populated_and_sorted_newest_first():
    feed = generate_offline_influencer_feed()
    assert len(feed) >= 3
    timestamps = [p.timestamp for p in feed]
    assert timestamps == sorted(timestamps, reverse=True)
    assert all(p.headline and p.name for p in feed)
