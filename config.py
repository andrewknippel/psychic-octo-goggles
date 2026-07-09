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
# Long-term (3-5 year) fundamentals screener (see long_term.py)
# ---------------------------------------------------------------------------
# Composite weights (should sum to 1.0). Growth/profitability/valuation
# dominate since those drive multi-year compounding; analyst targets and
# trailing price trend get smaller weights since they say less about a
# 3-5 year outcome than the underlying business does.
LT_WEIGHT_GROWTH = _float_env("LT_WEIGHT_GROWTH", 0.25)
LT_WEIGHT_PROFITABILITY = _float_env("LT_WEIGHT_PROFITABILITY", 0.20)
LT_WEIGHT_FINANCIAL_HEALTH = _float_env("LT_WEIGHT_FINANCIAL_HEALTH", 0.15)
LT_WEIGHT_VALUATION = _float_env("LT_WEIGHT_VALUATION", 0.20)
LT_WEIGHT_ANALYST = _float_env("LT_WEIGHT_ANALYST", 0.10)
LT_WEIGHT_TREND = _float_env("LT_WEIGHT_TREND", 0.10)

# Minimum market cap ($2B, the common small/mid-cap line) to be considered --
# below this, single-company risk is high for a "best long-term picks" list.
LT_MIN_MARKET_CAP = _float_env("LT_MIN_MARKET_CAP", 2_000_000_000)

# Risk-flag thresholds -- annotations only, never affect score/ranking.
LT_RISK_DEBT_TO_EQUITY = _float_env("LT_RISK_DEBT_TO_EQUITY", 150.0)
LT_RISK_PEG = _float_env("LT_RISK_PEG", 3.0)
LT_RISK_FORWARD_PE = _float_env("LT_RISK_FORWARD_PE", 45.0)
LT_RISK_ANALYST_RATING = _float_env("LT_RISK_ANALYST_RATING", 3.5)
LT_RISK_BETA = _float_env("LT_RISK_BETA", 1.8)

LT_DEFAULT_TOP_N = _int_env("LT_DEFAULT_TOP_N", 10)
# Cap on how many tickers from the curated default pool (long_term_universe.py)
# get scanned on top of --watchlist. Each candidate costs a fundamentals
# lookup + a multi-year price history pull.
LT_DEFAULT_MAX_CANDIDATES = _int_env("LT_DEFAULT_MAX_CANDIDATES", 40)

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
