"""Default candidate universe for the long-term (3-5 year) screener.

Short-term discovery (StockTwits trending, Reddit cashtags -- see
ticker_discovery.py) surfaces whatever has attention *right now*, which is
close to the opposite of what matters for a multi-year hold. So instead of
algorithmic discovery, this is a curated, static pool of established,
liquid, large/mid-cap companies spread across sectors -- a reasonable
starting universe to run through the fundamentals screen, not a claim that
these are already "the best long-term picks" (that's what
fundamentals_scoring.py's ranking is for). Add your own names via
--watchlist; CANDIDATE_POOL is just what's scanned when none is given.
"""
CANDIDATE_POOL = sorted({
    # Technology / semiconductors
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "AVGO", "ASML", "TSM",
    "ADBE", "CRM", "ORCL", "NOW", "INTU", "TXN", "AMD", "QCOM", "PANW",
    # Healthcare
    "UNH", "JNJ", "LLY", "ABBV", "MRK", "TMO", "DHR", "ISRG", "SYK",
    # Consumer
    "COST", "WMT", "PG", "HD", "NKE", "SBUX", "MCD", "PEP", "KO", "DIS",
    # Financials
    "V", "MA", "JPM", "BRK-B", "GS", "SPGI",
    # Industrials / energy / materials
    "CAT", "HON", "LIN", "XOM", "CVX", "GE",
    # Communication / other
    "NFLX", "ACN",
})
