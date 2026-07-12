"""News feed for market-moving public figures ("powerful businessmen").

Pulls recent coverage of a configured roster of people whose public
statements routinely move markets -- CEOs, the Fed chair, high-profile
investors -- from Google News' keyless RSS search endpoint. This is a
per-figure request against a free, unauthenticated feed, so, like the
Yahoo RSS path in news.py, it's kept small (a handful of figures, a few
headlines each) and every network call degrades to an empty result instead
of crashing the run.

Honesty note: these are *news articles about* what these figures said or
did -- reputable outlets' coverage of their remarks, filings, and posts --
not a scrape of their raw social-media accounts. The platforms those posts
originate on (X in particular) require authenticated API access this
zero-key tool doesn't assume, and quoting an unverified raw post as fact
would be worse than citing an outlet that checked it. Coverage of a notable
post generally shows up here within the same news cycle.
"""
import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import quote_plus

import requests

import config

logger = logging.getLogger(__name__)

_TIMEOUT = 8
_REQUEST_DELAY_SECONDS = 0.4
# Bias the query toward market-relevant coverage so the feed doesn't fill
# with unrelated personal news about a figure.
_QUERY_SUFFIX = "(stock OR market OR economy OR earnings OR Fed OR shares)"


@dataclass
class InfluencerPost:
    """One recent news item about a market-moving figure."""

    name: str
    role: str
    headline: str
    source: str  # publishing outlet, e.g. "Reuters"
    url: str
    timestamp: datetime
    snippet: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "headline": self.headline,
            "source": self.source,
            "url": self.url,
            "published_at": self.timestamp.astimezone(timezone.utc).isoformat(),
            "snippet": self.snippet,
        }


def parse_figures(spec: str) -> List[tuple]:
    """Parse the "Name|Role,Name|Role" config string into (name, role) pairs.
    A missing role (no "|") is tolerated and left blank."""
    figures = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "|" in chunk:
            name, role = chunk.split("|", 1)
            figures.append((name.strip(), role.strip()))
        else:
            figures.append((chunk, ""))
    return figures


def fetch_influencer_posts(
    name: str,
    role: str = "",
    max_items: Optional[int] = None,
    lookback_days: Optional[int] = None,
) -> List[InfluencerPost]:
    """Recent market-relevant news items mentioning `name`, newest first."""
    max_items = max_items or config.INFLUENCER_MAX_PER_FIGURE
    lookback_days = lookback_days or config.INFLUENCER_LOOKBACK_DAYS

    query = quote_plus(f'"{name}" {_QUERY_SUFFIX}')
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    time.sleep(_REQUEST_DELAY_SECONDS)
    try:
        resp = requests.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except (requests.RequestException, ET.ParseError) as exc:
        logger.warning("Influencer news fetch failed for %s: %s", name, exc)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    posts: List[InfluencerPost] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        ts = _parse_rfc822(item.findtext("pubDate")) or datetime.now(timezone.utc)
        if ts < cutoff:
            continue
        # Google News formats titles as "Headline - Outlet"; split the outlet
        # off so it can be shown as a distinct source label.
        headline, source = title, ""
        if " - " in title:
            headline, source = title.rsplit(" - ", 1)
        posts.append(
            InfluencerPost(
                name=name,
                role=role,
                headline=headline.strip(),
                source=source.strip(),
                url=(item.findtext("link") or "").strip(),
                timestamp=ts,
                snippet=_strip_html(item.findtext("description") or ""),
            )
        )
        if len(posts) >= max_items:
            break
    return posts


def fetch_influencer_feed(figures: Optional[List[tuple]] = None) -> List[InfluencerPost]:
    """Aggregate recent news across all configured figures, newest first."""
    if figures is None:
        figures = parse_figures(config.INFLUENCER_FIGURES)
    feed: List[InfluencerPost] = []
    for name, role in figures:
        feed.extend(fetch_influencer_posts(name, role))
    feed.sort(key=lambda p: p.timestamp, reverse=True)
    return feed


def _strip_html(value: str) -> str:
    """Google News descriptions are HTML fragments -- reduce to a short,
    plain-text snippet for display."""
    import re

    text = re.sub(r"<[^>]+>", " ", value)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:280]


def _parse_rfc822(value):
    if not value:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None
