"""StockTwits collection via its public, keyless REST API.

StockTwits messages are useful beyond generic sentiment analysis because
authors can self-tag a message "Bullish" or "Bearish" -- that explicit label
is a stronger signal than anything we could infer from the text alone, so
downstream scoring prefers it when present.
"""
import logging
from datetime import datetime, timezone
from typing import List, Set

import requests

from src.models import Mention

logger = logging.getLogger(__name__)

_TIMEOUT = 8
_HEADERS = {"User-Agent": "Mozilla/5.0 (research bot; stock-scanner/1.0)"}


def fetch_stocktwits_mentions(ticker: str) -> List[Mention]:
    url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("StockTwits fetch failed for %s: %s", ticker, exc)
        return []

    mentions = []
    for msg in data.get("messages", []):
        created = msg.get("created_at")
        try:
            ts = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
        except (TypeError, ValueError):
            ts = datetime.now(timezone.utc)

        sentiment_tag = None
        entities = msg.get("entities") or {}
        sentiment = entities.get("sentiment")
        if sentiment and sentiment.get("basic"):
            sentiment_tag = sentiment["basic"]  # "Bullish" | "Bearish"

        likes = (msg.get("likes") or {}).get("total", 0)
        mentions.append(
            Mention(
                ticker=ticker,
                source="stocktwits",
                text=msg.get("body", ""),
                timestamp=ts,
                url=f"https://stocktwits.com/symbol/{ticker}",
                engagement=int(likes or 0),
                explicit_sentiment=sentiment_tag,
            )
        )
    return mentions


def fetch_trending_symbols() -> Set[str]:
    url = "https://api.stocktwits.com/api/2/trending/symbols.json"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("StockTwits trending fetch failed: %s", exc)
        return set()

    return {s.get("symbol") for s in data.get("symbols", []) if s.get("symbol")}
