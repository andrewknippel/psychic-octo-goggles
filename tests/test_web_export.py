"""Tests for the static-dashboard JSON export."""
import json
import os
from datetime import datetime, timezone

from src.analysis.day_movers import scan_for_day_movers
from src.analysis.dip_scanner import scan_for_dips
from src.sample_data import (
    generate_offline_dataset,
    generate_offline_influencer_feed,
)
from src.web_export import build_dashboard_payload, write_dashboard_json


def _raw_data():
    dataset = generate_offline_dataset()
    return [
        (ticker, news, social, prices, earnings)
        for ticker, (news, social, prices, earnings) in dataset.items()
    ]


def _payload():
    raw = _raw_data()
    return build_dashboard_payload(
        scan_for_dips(raw),
        scan_for_day_movers(raw),
        generate_offline_influencer_feed(),
        mode="offline",
        generated_at=datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc),
    )


def test_payload_has_all_top_level_sections():
    payload = _payload()
    assert set(payload) == {
        "generated_at", "mode", "rebound_candidates",
        "day_movers", "influencer_feed", "disclaimer",
    }
    assert payload["mode"] == "offline"
    assert payload["generated_at"].startswith("2026-07-11T12:00:00")


def test_rebound_candidates_include_dippy_and_are_serializable():
    payload = _payload()
    tickers = {c["ticker"] for c in payload["rebound_candidates"]}
    assert "DIPPY" in tickers
    # must be pure-JSON (no dataclasses / datetimes leaking through)
    json.dumps(payload)


def test_rebound_candidates_sorted_by_rsi_ascending():
    # multiple candidates would sort most-oversold (lowest RSI) first
    rsis = [c["rsi"] for c in _payload()["rebound_candidates"] if c["rsi"] is not None]
    assert rsis == sorted(rsis)


def test_day_movers_include_toppy():
    tickers = {m["ticker"] for m in _payload()["day_movers"]}
    assert "TOPPY" in tickers


def test_influencer_feed_entries_have_expected_fields():
    feed = _payload()["influencer_feed"]
    assert feed
    for item in feed:
        assert item["name"] and item["headline"]
        assert "published_at" in item


def test_write_dashboard_json_roundtrips(tmp_path):
    path = os.path.join(tmp_path, "sub", "data.json")
    payload = _payload()
    write_dashboard_json(payload, path)
    assert os.path.exists(path)
    with open(path) as f:
        loaded = json.load(f)
    assert loaded == payload
    # no leftover temp file
    assert not os.path.exists(f"{path}.tmp")
