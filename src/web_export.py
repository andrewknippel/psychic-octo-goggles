"""Serialize a scan's results into the JSON payload the static web
dashboard (see the web/ directory) reads.

The dashboard is a plain static page: this module writes a single
`data.json` file that the page fetches and re-fetches on a timer. Refreshing
the dashboard therefore just means rewriting this file -- which is exactly
what main.py's live loop does every --interval when given --web-out.
"""
import json
import os
from datetime import datetime, timezone
from typing import List, Optional

from src.analysis.day_movers import DayMover, rank_day_movers
from src.analysis.dip_scanner import DipCandidate, rank_dip_candidates
from src.data_sources.influencers import InfluencerPost

DISCLAIMER = (
    "Research/screening tool, not investment advice. Rebound candidates are "
    "oversold-bounce setups, not predictions -- a sharp drop can keep falling "
    "(a \"falling knife\") instead of bouncing, and nothing here guarantees a "
    "rebound within any timeframe. Same-day movers flag unusual price+volume "
    "activity, not which way the rest of the session goes. The figures feed is "
    "news coverage of what market-moving people said or did, not a guarantee of "
    "market impact. Always do your own due diligence before trading."
)


def _dip_to_dict(c: DipCandidate) -> dict:
    return {
        "ticker": c.ticker,
        "last_price": c.last_price,
        "change_3d_pct": c.change_3d_pct,
        "change_5d_pct": c.change_5d_pct,
        "rsi": c.rsi,
        "sentiment_score": c.sentiment_score,
        "earnings_date": c.earnings_date,
        "reasons": list(c.reasons),
        "summary": c.summary,
    }


def _mover_to_dict(m: DayMover) -> dict:
    return {
        "ticker": m.ticker,
        "last_price": m.last_price,
        "change_1d_pct": m.change_1d_pct,
        "volume_surge": m.volume_surge,
        "rsi": m.rsi,
        "reasons": list(m.reasons),
        "summary": m.summary,
    }


def build_dashboard_payload(
    dip_candidates: List[DipCandidate],
    day_movers: List[DayMover],
    influencer_feed: List[InfluencerPost],
    mode: str = "live",
    generated_at: Optional[datetime] = None,
) -> dict:
    """Assemble the full JSON payload (ranked, serialized) for the dashboard."""
    generated_at = generated_at or datetime.now(timezone.utc)
    return {
        "generated_at": generated_at.astimezone(timezone.utc).isoformat(),
        "mode": mode,
        "rebound_candidates": [_dip_to_dict(c) for c in rank_dip_candidates(dip_candidates)],
        "day_movers": [_mover_to_dict(m) for m in rank_day_movers(day_movers)],
        "influencer_feed": [p.to_dict() for p in influencer_feed],
        "disclaimer": DISCLAIMER,
    }


def write_dashboard_json(payload: dict, path: str) -> None:
    """Write `payload` to `path` atomically (temp file + rename) so the page
    never fetches a half-written file mid-refresh."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_path, path)
