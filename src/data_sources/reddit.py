"""Reddit collection via the public, keyless JSON endpoints.

Reddit's read-only JSON API (append `.json` to any listing URL) doesn't
require OAuth for this kind of low-volume, unauthenticated read access, but
it *is* sensitive to request volume/pattern -- firing one request per
subreddit per ticker in a tight loop reliably triggers 403 "Blocked for
url" responses. Reddit supports multi-subreddit listings
(`r/sub1+sub2+sub3/...`), so every function here issues one combined
request instead of one per subreddit, plus a small delay before each call
to avoid looking like a burst of bot traffic.
"""
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import List, Set

import requests

import config
from src.models import Mention

logger = logging.getLogger(__name__)

_TIMEOUT = 10
_REQUEST_DELAY_SECONDS = 0.6
_CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")
# Common false positives that look like cashtags but are trading jargon /
# not tickers, plus a couple of mega-cap tickers that are also common words
# and too noisy to auto-discover (still scorable if explicitly watchlisted).
_CASHTAG_BLOCKLIST = {
    "ITM", "OTM", "ATM", "IV", "YOLO", "DD", "CEO", "CFO", "SEC", "IPO",
    "ETF", "USD", "EPS", "PE", "PT", "ATH", "ATL", "FOMO", "TA", "IMO",
}


def _headers():
    return {"User-Agent": config.REDDIT_USER_AGENT}


def _multi_subreddit_path() -> str:
    subs = [s.strip() for s in config.REDDIT_SUBREDDITS if s.strip()]
    return "+".join(subs)


def fetch_reddit_mentions(ticker: str) -> List[Mention]:
    """Search configured subreddits (as one combined multi-subreddit query,
    not one request per subreddit) for posts mentioning `ticker`."""
    subs_path = _multi_subreddit_path()
    if not subs_path:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=config.LOOKBACK_DAYS)
    url = f"https://www.reddit.com/r/{subs_path}/search.json"
    params = {
        "q": f"{ticker} OR ${ticker}",
        "restrict_sr": "1",
        "sort": "new",
        "t": "week",
        "limit": 25,
    }
    time.sleep(_REQUEST_DELAY_SECONDS)
    try:
        resp = requests.get(url, params=params, headers=_headers(), timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Reddit search failed for %s: %s", ticker, exc)
        return []

    mentions: List[Mention] = []
    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        ts = datetime.fromtimestamp(post.get("created_utc", 0), tz=timezone.utc)
        if ts < cutoff:
            continue
        title = post.get("title", "")
        body = post.get("selftext", "") or ""
        text = f"{title}. {body}"[:1000]
        if ticker.upper() not in text.upper():
            continue
        mentions.append(
            Mention(
                ticker=ticker,
                source="reddit",
                text=text,
                timestamp=ts,
                url=f"https://reddit.com{post.get('permalink', '')}",
                engagement=int(post.get("score", 0)) + int(post.get("num_comments", 0)),
            )
        )
    return mentions


def extract_cashtags(text: str) -> Set[str]:
    """Pull $CASHTAG-style ticker mentions out of free text, filtering out
    common trading-jargon false positives (e.g. $OTM, $YOLO)."""
    return {m for m in _CASHTAG_RE.findall(text) if m not in _CASHTAG_BLOCKLIST}


def scan_trending_cashtags(limit_per_sub: int = 75) -> Set[str]:
    """Scan hot posts across configured subreddits (one combined
    multi-subreddit request) and extract $CASHTAGs.

    Used for ticker *discovery* -- finding names getting organic retail
    attention right now, independent of any hand-maintained watchlist.
    """
    subs_path = _multi_subreddit_path()
    if not subs_path:
        return set()

    url = f"https://www.reddit.com/r/{subs_path}/hot.json"
    time.sleep(_REQUEST_DELAY_SECONDS)
    try:
        resp = requests.get(
            url, params={"limit": limit_per_sub}, headers=_headers(), timeout=_TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Reddit trending scan failed: %s", exc)
        return set()

    found: Set[str] = set()
    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        text = f"{post.get('title', '')} {post.get('selftext', '')}"
        found |= extract_cashtags(text)
    return found
