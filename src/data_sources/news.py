"""News headline collection.

Primary source is NewsAPI (https://newsapi.org) when NEWSAPI_KEY is set.
Falls back to the free, keyless Yahoo Finance per-ticker RSS feed so the
pipeline still gets a news signal with zero configuration -- but that feed
is a per-ticker request with no batching option, so it starts returning
`429 Too Many Requests` once a scan covers dozens of tickers back-to-back.
A small delay before each request buys some headroom, though at a large
enough --max-candidates it's still going to get rate-limited sometimes; a
NEWSAPI_KEY avoids this path (and its rate limit) entirely.

Every network call is wrapped so a single failing source degrades to an
empty result instead of crashing the whole run.
"""
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import List

import requests

import config
from src.models import Mention

logger = logging.getLogger(__name__)

_TIMEOUT = 8
_YAHOO_RSS_DELAY_SECONDS = 0.5


def fetch_news_mentions(ticker: str, company_name: str = "") -> List[Mention]:
    """Return recent news headlines mentioning `ticker` (or `company_name`)."""
    if config.NEWSAPI_KEY:
        mentions = _fetch_newsapi(ticker, company_name)
        if mentions:
            return mentions
    return _fetch_yahoo_rss(ticker)


def _fetch_newsapi(ticker: str, company_name: str) -> List[Mention]:
    query = f'"{company_name}" OR "{ticker}"' if company_name else ticker
    since = (datetime.now(timezone.utc) - timedelta(days=config.LOOKBACK_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    params = {
        "q": query,
        "from": since,
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": 25,
        "apiKey": config.NEWSAPI_KEY,
    }
    try:
        resp = requests.get(
            "https://newsapi.org/v2/everything", params=params, timeout=_TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("NewsAPI fetch failed for %s: %s", ticker, exc)
        return []

    mentions = []
    for article in data.get("articles", []):
        title = article.get("title") or ""
        description = article.get("description") or ""
        published = article.get("publishedAt")
        try:
            ts = datetime.strptime(published, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
        except (TypeError, ValueError):
            ts = datetime.now(timezone.utc)
        mentions.append(
            Mention(
                ticker=ticker,
                source="news",
                text=f"{title}. {description}".strip(),
                timestamp=ts,
                url=article.get("url", ""),
                engagement=0,
            )
        )
    return mentions


def _fetch_yahoo_rss(ticker: str) -> List[Mention]:
    url = (
        "https://feeds.finance.yahoo.com/rss/2.0/headline"
        f"?s={ticker}&region=US&lang=en-US"
    )
    time.sleep(_YAHOO_RSS_DELAY_SECONDS)
    try:
        resp = requests.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except (requests.RequestException, ET.ParseError) as exc:
        logger.warning("Yahoo RSS fetch failed for %s: %s", ticker, exc)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=config.LOOKBACK_DAYS)
    mentions = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        description = (item.findtext("description") or "").strip()
        pub_date = item.findtext("pubDate")
        ts = _parse_rfc822(pub_date) or datetime.now(timezone.utc)
        if ts < cutoff:
            continue
        mentions.append(
            Mention(
                ticker=ticker,
                source="news",
                text=f"{title}. {description}".strip(),
                timestamp=ts,
                url=item.findtext("link") or "",
                engagement=0,
            )
        )
    return mentions


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
