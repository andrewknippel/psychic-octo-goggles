"""Central configuration: tunable weights, thresholds, and API credentials.

All values can be overridden with environment variables (see .env.example)
so the scoring behavior can be tuned without touching code.
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


# ---------------------------------------------------------------------------
# API credentials (all optional -- the pipeline degrades gracefully without
# them, see data_sources/*.py)
# ---------------------------------------------------------------------------
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")
REDDIT_USER_AGENT = os.environ.get(
    "REDDIT_USER_AGENT", "stock-scanner/1.0 (research use)"
)

# ---------------------------------------------------------------------------
# Universe / discovery
# ---------------------------------------------------------------------------
# Subreddits scanned for cashtag mentions and post sentiment. All configured
# subreddits are combined into a single request (see reddit.py), so adding
# more here widens ticker discovery without costing extra API calls.
REDDIT_SUBREDDITS = os.environ.get(
    "REDDIT_SUBREDDITS",
    "wallstreetbets,stocks,StockMarket,investing,options,Daytrading",
).split(",")

# Minimum share price to consider. $5 is the commonly-cited SEC/industry
# line for "penny stock" -- below it, tickers are excluded entirely (not
# just scored low) since that segment is mostly noise/manipulation risk
# rather than genuine short-term growth.
MIN_PRICE = _float_env("MIN_PRICE", 5.0)

# Minimum 20-day average daily volume to consider a ticker liquid enough to
# trade in/out of within a 2-7 day window.
MIN_AVG_VOLUME = _int_env("MIN_AVG_VOLUME", 300_000)

# A ticker needs at least this many combined news+social mentions before it's
# scored at all -- avoids ranking obscure names off a single noisy post.
MIN_MENTIONS = _int_env("MIN_MENTIONS", 3)

# Cap on the auto-discovered candidate universe size (watchlist tickers are
# always included on top of this). Each candidate costs ~5 sequential
# network calls (news, Reddit, StockTwits, price history, earnings date),
# so this is the main lever on how long a run takes and how much load it
# puts on the free data sources -- override with --max-candidates or this
# env var. A bigger pool means a longer scan (and more exposure to the
# free-tier rate limits described in the README) but more names considered.
MAX_DISCOVERY_CANDIDATES = _int_env("MAX_DISCOVERY_CANDIDATES", 15)

# Mention count at which the confidence multiplier saturates to 1.0.
MENTION_CONFIDENCE_SATURATION = _int_env("MENTION_CONFIDENCE_SATURATION", 40)

# ---------------------------------------------------------------------------
# Composite scoring weights (must sum to 1.0)
# ---------------------------------------------------------------------------
WEIGHT_SENTIMENT = _float_env("WEIGHT_SENTIMENT", 0.35)
WEIGHT_MOMENTUM = _float_env("WEIGHT_MOMENTUM", 0.30)
WEIGHT_BUZZ = _float_env("WEIGHT_BUZZ", 0.20)
WEIGHT_TECHNICAL = _float_env("WEIGHT_TECHNICAL", 0.15)

# Sub-weights: how news vs. social contribute to the sentiment sub-score.
SENTIMENT_NEWS_WEIGHT = _float_env("SENTIMENT_NEWS_WEIGHT", 0.4)
SENTIMENT_SOCIAL_WEIGHT = _float_env("SENTIMENT_SOCIAL_WEIGHT", 0.6)

# Recency half-life (hours) used to decay the influence of older mentions --
# tuned for a 2-7 day holding window, so anything older than ~4 days matters
# very little.
RECENCY_HALF_LIFE_HOURS = _float_env("RECENCY_HALF_LIFE_HOURS", 30.0)

# How many days of mentions to pull from news/social sources.
LOOKBACK_DAYS = _int_env("LOOKBACK_DAYS", 4)

# ---------------------------------------------------------------------------
# Risk flags -- these don't change the score, they annotate it so a high
# ranking doesn't get mistaken for a low-risk one.
# ---------------------------------------------------------------------------
RISK_RSI_OVERBOUGHT = _float_env("RISK_RSI_OVERBOUGHT", 75.0)
RISK_RSI_OVERSOLD = _float_env("RISK_RSI_OVERSOLD", 25.0)
RISK_VOLATILITY_PCT = _float_env("RISK_VOLATILITY_PCT", 6.0)
RISK_EXTENDED_MOVE_PCT = _float_env("RISK_EXTENDED_MOVE_PCT", 15.0)
RISK_EARNINGS_WINDOW_DAYS = _int_env("RISK_EARNINGS_WINDOW_DAYS", 7)

# ---------------------------------------------------------------------------
# Market-moving figures ("powerful businessmen") news feed
# ---------------------------------------------------------------------------
# People whose public statements/posts routinely move markets. Recent news
# about them (their remarks, filings, policy calls) is pulled from Google
# News' keyless RSS search and surfaced as a separate feed on the web
# dashboard. Override the roster with a "Name|Role" comma-separated env var,
# e.g. INFLUENCER_FIGURES="Elon Musk|Tesla & xAI CEO,Jerome Powell|Fed Chair".
INFLUENCER_FIGURES = os.environ.get(
    "INFLUENCER_FIGURES",
    "Elon Musk|Tesla & xAI CEO,"
    "Jerome Powell|Federal Reserve Chair,"
    "Warren Buffett|Berkshire Hathaway CEO,"
    "Jensen Huang|Nvidia CEO,"
    "Jamie Dimon|JPMorgan Chase CEO,"
    "Donald Trump|US President,"
    "Cathie Wood|ARK Invest CEO,"
    "Bill Ackman|Pershing Square CEO",
)
# Max headlines to keep per figure per refresh, and how many days back to look.
INFLUENCER_MAX_PER_FIGURE = _int_env("INFLUENCER_MAX_PER_FIGURE", 4)
INFLUENCER_LOOKBACK_DAYS = _int_env("INFLUENCER_LOOKBACK_DAYS", 3)

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
DEFAULT_TOP_N = _int_env("DEFAULT_TOP_N", 5)
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")

# ---------------------------------------------------------------------------
# Live tracking (on by default -- see main.py's --once to disable)
# ---------------------------------------------------------------------------
DEFAULT_WATCH_INTERVAL_MINUTES = _int_env("DEFAULT_WATCH_INTERVAL_MINUTES", 10)
# Floor on refresh frequency -- Reddit/StockTwits/Yahoo's free, keyless
# endpoints rate-limit or block clients that poll too aggressively.
MIN_WATCH_INTERVAL_MINUTES = _int_env("MIN_WATCH_INTERVAL_MINUTES", 5)

# ---------------------------------------------------------------------------
# Dip-reversal ("buy the dip") candidate detection
# ---------------------------------------------------------------------------
# Minimum 5-day decline (as a positive number, e.g. 8 means -8% or worse)
# before a ticker is even considered a dip candidate.
DIP_DROP_PCT = _float_env("DIP_DROP_PCT", 8.0)
# RSI at/below this counts as "oversold" -- one of two possible reversal
# signals (the other is the decline visibly decelerating).
DIP_RSI_OVERSOLD = _float_env("DIP_RSI_OVERSOLD", 32.0)
# Sentiment (0-100) must be at/above this to qualify. A sharp drop paired
# with genuinely bearish sentiment reads as a falling knife (bad
# company-specific news), not a bounce setup -- this filters those out.
DIP_MIN_SENTIMENT = _float_env("DIP_MIN_SENTIMENT", 40.0)

# Dip candidates are framed around a "days to ~4 weeks" rebound horizon --
# an earnings report anywhere in that window is real event risk (it can
# move the stock on its own terms regardless of the technical setup), so
# it's flagged when the next earnings date falls within this many days.
DIP_EARNINGS_WINDOW_DAYS = _int_env("DIP_EARNINGS_WINDOW_DAYS", 28)

# ---------------------------------------------------------------------------
# Same-day momentum movers -- NOT a same-day round-trip guarantee. This is
# the closest honest signal daily-bar data can give for "unusually active
# today": today's price move plus today's volume vs. its own average. It
# says nothing about which direction the rest of the day goes.
# ---------------------------------------------------------------------------
# Minimum single-day gain (%) to count as a "mover" today.
DAY_MOVER_MIN_CHANGE_PCT = _float_env("DAY_MOVER_MIN_CHANGE_PCT", 3.0)
# Minimum volume surge (today's volume / 20-day average) to count as
# unusually active rather than just drifting up on light volume.
DAY_MOVER_MIN_VOLUME_SURGE = _float_env("DAY_MOVER_MIN_VOLUME_SURGE", 1.5)
