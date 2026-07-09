"""Builds the candidate ticker universe to score.

Combines three sources:
  1. A user-supplied watchlist (always included).
  2. StockTwits' own trending-symbols list (algorithmic buzz ranking).
  3. $CASHTAGs scraped out of hot posts in configured subreddits.

This keeps the pipeline from being limited to a hardcoded list while still
letting a user pin specific tickers they care about.
"""
import logging
from typing import List, Optional, Set

import config
from src.data_sources import reddit, stocktwits

logger = logging.getLogger(__name__)


def discover_universe(
    watchlist: List[str],
    include_trending: bool = True,
    max_candidates: Optional[int] = None,
) -> List[str]:
    if max_candidates is None:
        max_candidates = config.MAX_DISCOVERY_CANDIDATES
    universe: Set[str] = {t.strip().upper() for t in watchlist if t.strip()}

    if include_trending:
        try:
            universe |= stocktwits.fetch_trending_symbols()
        except Exception as exc:  # defensive: discovery must never crash the run
            logger.warning("StockTwits trending discovery failed: %s", exc)

        try:
            universe |= reddit.scan_trending_cashtags()
        except Exception as exc:
            logger.warning("Reddit cashtag discovery failed: %s", exc)

    ordered = sorted(universe)
    return ordered[:max_candidates]
