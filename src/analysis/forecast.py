"""Single-ticker short-term forecast via historical-analog (k-nearest-neighbor)
statistics.

Given one ticker, this pulls several years of daily price/volume history,
computes a handful of technical-state features for every historical day
(RSI, momentum, distance from the 20-day moving average, volatility, volume
ratio relative to its 20-day average), and finds the historical days whose
feature vector was closest to today's. Whatever actually happened to price
over the 1-5 trading days *following* those look-alike days becomes the
forecast: the fraction that were profitable at some point in the following
week estimates a probability of short-term gain, and the day-ahead with the
best average forward return becomes the estimated best day to sell.

This is a base-rate/analog statistical estimate, not a predictive model --
see README.md's "Single-ticker analysis" section for methodology and
caveats. Past look-alike setups are not a guarantee of what a given ticker
does next.
"""
import math
import random
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import List, Optional

from src.data_sources import market_data
from src.models import PriceSeries

WARMUP_DAYS = 20          # trailing days needed before the first feature row
HORIZON_DAYS = 5          # ~1 trading week
DEFAULT_K = 40            # neighbors to average over
MIN_TRAINING_ROWS = 30    # below this, the analog pool is too thin to trust

_FEATURE_KEYS = ["rsi14", "mom5", "mom10", "dist_sma20", "vol20", "volratio"]


@dataclass
class DayForecast:
    day: int  # trading days ahead (1-5)
    avg_return_pct: float
    prob_positive_pct: float


@dataclass
class ForecastResult:
    ticker: str
    as_of_date: str
    last_price: float
    rsi14: Optional[float]
    momentum_5d_pct: Optional[float]
    dist_from_sma20_pct: Optional[float]
    volatility_20d_pct: Optional[float]
    volume_ratio: Optional[float]
    analog_pool_size: int
    neighbors_used: int
    prob_gain_within_week_pct: float
    day_forecasts: List[DayForecast]
    best_sell_day: int
    best_sell_date: str
    best_sell_expected_return_pct: float
    best_sell_prob_positive_pct: float
    notes: List[str] = field(default_factory=list)


def _rsi_at(closes: List[float], i: int, period: int = 14) -> Optional[float]:
    if i < period:
        return None
    gains, losses = [], []
    for j in range(i - period + 1, i + 1):
        change = closes[j] - closes[j - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _pct_change_at(closes: List[float], i: int, lag: int) -> Optional[float]:
    if i < lag or not closes[i - lag]:
        return None
    return (closes[i] - closes[i - lag]) / closes[i - lag] * 100


def _sma_at(closes: List[float], i: int, period: int) -> Optional[float]:
    if i < period - 1:
        return None
    window = closes[i - period + 1 : i + 1]
    return sum(window) / period


def _volatility_at(closes: List[float], i: int, period: int = 20) -> Optional[float]:
    if i < period:
        return None
    window = closes[i - period : i + 1]
    returns = [
        (window[j] - window[j - 1]) / window[j - 1] * 100
        for j in range(1, len(window))
        if window[j - 1]
    ]
    if len(returns) < 2:
        return None
    return statistics.pstdev(returns)


def _volume_ratio_at(volumes: List[float], i: int, period: int = 20) -> Optional[float]:
    if i < period - 1:
        return None
    window = volumes[i - period + 1 : i + 1]
    avg = sum(window) / period
    if not avg:
        return None
    return volumes[i] / avg


def _feature_vector(closes, volumes, i):
    """Feature dict at index i, or None if any input indicator is unavailable
    (not enough trailing history at this index)."""
    rsi = _rsi_at(closes, i, 14)
    mom5 = _pct_change_at(closes, i, 5)
    mom10 = _pct_change_at(closes, i, 10)
    sma20 = _sma_at(closes, i, 20)
    vol20 = _volatility_at(closes, i, 20)
    volratio = _volume_ratio_at(volumes, i, 20)

    if None in (rsi, mom5, mom10, sma20, vol20, volratio) or not sma20:
        return None

    dist_sma20 = (closes[i] - sma20) / sma20 * 100
    return {
        "rsi14": rsi,
        "mom5": mom5,
        "mom10": mom10,
        "dist_sma20": dist_sma20,
        "vol20": vol20,
        "volratio": volratio,
    }


def _add_trading_days(start: date, n: int) -> date:
    """Calendar-naive: skips weekends only, market holidays aren't modeled,
    so this is an approximate estimate of the calendar date."""
    d = start
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


def _standardize(rows, today_vec):
    """Z-scores every feature across `rows` (list of feature dicts) and
    applies the same transform to today_vec. Returns (scaled_rows,
    scaled_today) as lists of floats in _FEATURE_KEYS order."""
    stats = {}
    for key in _FEATURE_KEYS:
        values = [r[key] for r in rows]
        mean = sum(values) / len(values)
        stdev = statistics.pstdev(values)
        stats[key] = (mean, stdev)

    def scale(vec):
        out = []
        for key in _FEATURE_KEYS:
            mean, stdev = stats[key]
            out.append((vec[key] - mean) / stdev if stdev else 0.0)
        return out

    return [scale(r) for r in rows], scale(today_vec)


def _distance(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def analyze_price_series(series: PriceSeries, k: int = DEFAULT_K) -> Optional[ForecastResult]:
    closes = series.close
    volumes = series.volume
    n = len(closes)

    last_index = n - 1
    if last_index < WARMUP_DAYS:
        return None

    today_features = _feature_vector(closes, volumes, last_index)
    if today_features is None:
        return None

    # Training pool: every earlier day with a full feature vector AND a full
    # forward-return label (needs HORIZON_DAYS of future closes after it).
    training_rows = []
    forward_returns = []
    for i in range(WARMUP_DAYS, last_index - HORIZON_DAYS + 1):
        feats = _feature_vector(closes, volumes, i)
        if feats is None or not closes[i]:
            continue
        base = closes[i]
        rets = {h: (closes[i + h] - base) / base * 100 for h in range(1, HORIZON_DAYS + 1)}
        training_rows.append(feats)
        forward_returns.append(rets)

    if len(training_rows) < MIN_TRAINING_ROWS:
        return None  # not enough history for a meaningful analog pool

    notes = []
    scaled_rows, scaled_today = _standardize(training_rows, today_features)
    k_used = min(k, len(scaled_rows))

    ranked = sorted(range(len(scaled_rows)), key=lambda idx: _distance(scaled_rows[idx], scaled_today))
    neighbor_idxs = ranked[:k_used]

    if k_used < k:
        notes.append(
            f"Limited history: only {k_used} analog days available (wanted {k}). "
            "Estimates below are less reliable than usual."
        )

    gains_within_week = sum(
        1 for idx in neighbor_idxs if max(forward_returns[idx].values()) > 0
    )
    prob_gain_pct = gains_within_week / len(neighbor_idxs) * 100

    day_forecasts = []
    for h in range(1, HORIZON_DAYS + 1):
        h_returns = [forward_returns[idx][h] for idx in neighbor_idxs]
        avg_ret = sum(h_returns) / len(h_returns)
        prob_pos = sum(1 for r in h_returns if r > 0) / len(h_returns) * 100
        day_forecasts.append(DayForecast(day=h, avg_return_pct=avg_ret, prob_positive_pct=prob_pos))

    best = max(day_forecasts, key=lambda d: d.avg_return_pct)
    if best.prob_positive_pct < 50:
        notes.append(
            f"The average return on day +{best.day} is pulled positive by a wide spread of "
            f"outcomes -- only {best.prob_positive_pct:.0f}% of analogs were actually positive "
            "at that point. Treat the 'best day' estimate as directional, not precise."
        )

    try:
        as_of = datetime.strptime(series.dates[-1], "%Y-%m-%d").date()
    except (ValueError, IndexError):
        as_of = datetime.now().date()
    best_sell_date = _add_trading_days(as_of, best.day)

    return ForecastResult(
        ticker=series.ticker,
        as_of_date=str(as_of),
        last_price=closes[-1],
        rsi14=today_features["rsi14"],
        momentum_5d_pct=today_features["mom5"],
        dist_from_sma20_pct=today_features["dist_sma20"],
        volatility_20d_pct=today_features["vol20"],
        volume_ratio=today_features["volratio"],
        analog_pool_size=len(training_rows),
        neighbors_used=k_used,
        prob_gain_within_week_pct=prob_gain_pct,
        day_forecasts=day_forecasts,
        best_sell_day=best.day,
        best_sell_date=str(best_sell_date),
        best_sell_expected_return_pct=best.avg_return_pct,
        best_sell_prob_positive_pct=best.prob_positive_pct,
        notes=notes,
    )


def analyze_ticker(ticker: str, period: str = "5y", k: int = DEFAULT_K) -> Optional[ForecastResult]:
    """Fetches `period` of daily history for `ticker` and runs the analog
    forecast. Falls back to the full available history ("max") if `period`
    didn't come back with enough data -- e.g. a recent IPO with under 5
    years on record."""
    series = market_data.fetch_price_series(ticker, period=period)
    min_needed = WARMUP_DAYS + HORIZON_DAYS + MIN_TRAINING_ROWS
    if (series is None or len(series.close) < min_needed) and period != "max":
        series = market_data.fetch_price_series(ticker, period="max")
    if series is None:
        return None
    return analyze_price_series(series, k=k)


def synthetic_price_series(ticker: str = "DEMO", days: int = 1260, seed: int = 7) -> PriceSeries:
    """Deterministic synthetic daily series for offline demo/testing -- a
    random walk with a slowly wandering drift term, so it cycles through a
    variety of technical states (trending, flat, choppy) rather than one
    straight line. No relation to any real ticker's actual behavior."""
    rng = random.Random(seed)
    price = 100.0
    closes = []
    volumes = []
    trend = 0.0
    for _ in range(days):
        trend = max(-0.25, min(0.25, trend + rng.uniform(-0.03, 0.03)))
        daily_ret = trend / 100 + rng.gauss(0, 0.015)
        price = max(0.5, price * (1 + daily_ret))
        closes.append(round(price, 2))
        volumes.append(max(1000, int(1_000_000 * (1 + rng.uniform(-0.4, 0.6)))))

    end = date.today()
    dates = []
    d = end
    while len(dates) < days:
        if d.weekday() < 5:
            dates.append(d)
        d -= timedelta(days=1)
    dates = [str(x) for x in reversed(dates)]

    return PriceSeries(ticker=ticker, dates=dates, close=closes, volume=volumes)
