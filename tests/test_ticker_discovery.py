import config
from src.data_sources.reddit import _multi_subreddit_path, extract_cashtags
from src.ticker_discovery import discover_universe


def test_extract_cashtags_finds_valid_tickers():
    text = "Loading up on $GME and $AMC calls before earnings"
    assert extract_cashtags(text) == {"GME", "AMC"}


def test_extract_cashtags_filters_jargon_blocklist():
    text = "These $OTM calls are pure $YOLO, might as well be $ATM"
    assert extract_cashtags(text) == set()


def test_extract_cashtags_no_matches_returns_empty_set():
    assert extract_cashtags("no tickers mentioned here") == set()


def test_discover_universe_always_includes_watchlist(monkeypatch):
    # Force discovery sources to no-op so this test has no network dependency.
    monkeypatch.setattr(
        "src.ticker_discovery.stocktwits.fetch_trending_symbols", lambda: set()
    )
    monkeypatch.setattr(
        "src.ticker_discovery.reddit.scan_trending_cashtags", lambda: set()
    )
    universe = discover_universe(["aapl", "TSLA"], include_trending=True)
    assert universe == ["AAPL", "TSLA"]


def test_discover_universe_merges_trending_sources(monkeypatch):
    monkeypatch.setattr(
        "src.ticker_discovery.stocktwits.fetch_trending_symbols", lambda: {"NVDA"}
    )
    monkeypatch.setattr(
        "src.ticker_discovery.reddit.scan_trending_cashtags", lambda: {"GME"}
    )
    universe = discover_universe(["AAPL"], include_trending=True)
    assert set(universe) == {"AAPL", "NVDA", "GME"}


def test_discover_universe_skips_trending_when_disabled(monkeypatch):
    monkeypatch.setattr(
        "src.ticker_discovery.stocktwits.fetch_trending_symbols",
        lambda: (_ for _ in ()).throw(AssertionError("should not be called")),
    )
    universe = discover_universe(["AAPL"], include_trending=False)
    assert universe == ["AAPL"]


def test_discover_universe_respects_configured_max_candidates(monkeypatch):
    monkeypatch.setattr(
        "src.ticker_discovery.stocktwits.fetch_trending_symbols",
        lambda: {f"T{i}" for i in range(50)},
    )
    monkeypatch.setattr(
        "src.ticker_discovery.reddit.scan_trending_cashtags", lambda: set()
    )
    universe = discover_universe([], include_trending=True)
    assert len(universe) == config.MAX_DISCOVERY_CANDIDATES


def test_multi_subreddit_path_joins_configured_subreddits():
    path = _multi_subreddit_path()
    subs = [s.strip() for s in config.REDDIT_SUBREDDITS if s.strip()]
    assert path == "+".join(subs)
    # One combined path -> one HTTP request instead of one per subreddit,
    # which is what was triggering Reddit's bot-detection 403s.
    assert path.count("+") == len(subs) - 1
