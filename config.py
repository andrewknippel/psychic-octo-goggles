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
# Subreddits scanned for cashtag mentions and post sentiment.
REDDIT_SUBREDDITS = os.environ.get(
    "REDDIT_SUBREDDITS", "wallstreetbets,stocks,StockMarket,investing"
).split(",")

# Minimum share price to consider (filters out illiquid/penny tickers whose
# short-term "growth" is mostly noise/manipulation risk).
MIN_PRICE = _float_env("MIN_PRICE", 3.0)

# Minimum 20-day average daily volume to consider a ticker liquid enough to
# trade in/out of within a 2-7 day window.
MIN_AVG_VOLUME = _int_env("MIN_AVG_VOLUME", 300_000)

# A ticker needs at least this many combined news+social mentions before it's
# scored at all -- avoids ranking obscure names off a single noisy post.
MIN_MENTIONS = _int_env("MIN_MENTIONS", 3)

# Cap on the auto-discovered candidate universe size (watchlist tickers are
# always included on top of this). Each candidate costs ~3-4 network calls
# (news, Reddit, StockTwits, price history), so this is the main lever on
# how long a no-watchlist run takes and how much load it puts on the free
# data sources.
MAX_DISCOVERY_CANDIDATES = _int_env("MAX_DISCOVERY_CANDIDATES", 20)

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
# Output
# ---------------------------------------------------------------------------
DEFAULT_TOP_N = _int_env("DEFAULT_TOP_N", 10)
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")

# ---------------------------------------------------------------------------
# --watch (live tracking) mode
# ---------------------------------------------------------------------------
DEFAULT_WATCH_INTERVAL_MINUTES = _int_env("DEFAULT_WATCH_INTERVAL_MINUTES", 15)
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
