"""Longer-horizon (weeks-to-months) single-ticker analysis: trend snapshot
plus a rule-based buy/hold/sell verdict, stop-loss/target levels, and a
holding-horizon estimate.

This is deliberately separate from src/analysis/technical.py and scoring.py,
which are tuned for the 2-7 day scanner in main.py (RSI-7, 3/5-day returns,
no moving averages). analyze.py's single-ticker report needs slower,
longer-lookback signals -- SMA20/50/200, RSI-14, MACD, 52-week range -- to
say anything meaningful about a multi-week/month hold.

Every verdict is a transparent, inspectable rule over these signals -- see
`build_recommendation`'s `reasons` list -- not a black-box prediction. This
is a heuristic screening aid, not investment advice.
"""
import math
import statistics
from datetime import date, datetime, timezone
from typing import List, Optional

import config
from src.models import CompanyInfo, PriceSeries, Recommendation

TRADING_DAYS_1M = 21
TRADING_DAYS_3M = 63
TRADING_DAYS_6M = 126


def _pct_change(closes: list, days_ago: int) -> Optional[float]:
    if len(closes) <= days_ago:
        return None
    base = closes[-1 - days_ago]
    if not base:
        return None
    return (closes[-1] - base) / base * 100


def _sma(values: list, period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _rsi(closes: list, period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _ema_full(values: list, period: int) -> list:
    """EMA seeded from the first value (not the more common SMA-seeded
    variant) so fast/slow series stay index-aligned without truncation.
    Early values are less accurate, but by bar 30+ this converges close
    enough to a standard EMA for a heuristic MACD."""
    if not values:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def _macd(closes: list, fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns (macd_line, signal_line, histogram, prev_histogram), or all
    None if there's not enough history."""
    if len(closes) < slow + signal:
        return None, None, None, None
    ema_fast = _ema_full(closes, fast)
    ema_slow = _ema_full(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = _ema_full(macd_line, signal)
    histogram = [m - s for m, s in zip(macd_line, signal_line)]
    prev_hist = histogram[-2] if len(histogram) > 1 else None
    return macd_line[-1], signal_line[-1], histogram[-1], prev_hist


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _daily_volatility_pct(closes: list, window: int = 20) -> Optional[float]:
    recent = closes[-(window + 1):]
    if len(recent) < 3:
        return None
    returns = [
        (recent[i] - recent[i - 1]) / recent[i - 1] * 100
        for i in range(1, len(recent))
        if recent[i - 1]
    ]
    if len(returns) < 2:
        return None
    return statistics.pstdev(returns)


class LongTermTechnicalSnapshot:
    """Trend/momentum signals over a multi-week-to-year lookback."""

    def __init__(self, series: PriceSeries):
        closes = series.close
        volumes = series.volume

        self.last_price = closes[-1] if closes else 0.0
        self.sma20 = _sma(closes, 20)
        self.sma50 = _sma(closes, 50)
        self.sma200 = _sma(closes, 200)

        lookback = closes[-252:] if len(closes) >= 252 else closes
        self.fifty_two_week_high = max(lookback) if lookback else None
        self.fifty_two_week_low = min(lookback) if lookback else None
        self.pct_from_high = (
            (self.last_price - self.fifty_two_week_high) / self.fifty_two_week_high * 100
            if self.fifty_two_week_high else None
        )
        self.pct_from_low = (
            (self.last_price - self.fifty_two_week_low) / self.fifty_two_week_low * 100
            if self.fifty_two_week_low else None
        )

        self.rsi14 = _rsi(closes, period=14)
        self.macd_line, self.macd_signal, self.macd_hist, self._prev_macd_hist = _macd(closes)

        self.momentum_1m = _pct_change(closes, TRADING_DAYS_1M)
        self.momentum_3m = _pct_change(closes, TRADING_DAYS_3M)
        self.momentum_6m = _pct_change(closes, TRADING_DAYS_6M)

        self.volatility_pct = _daily_volatility_pct(closes, window=20)

        avg_volume_50 = _sma(volumes, 50) or _sma(volumes, len(volumes))
        self.avg_volume_50 = avg_volume_50 or 0.0
        last_volume = volumes[-1] if volumes else 0.0
        self.volume_surge = last_volume / self.avg_volume_50 if self.avg_volume_50 else 1.0

        self.recent_low_20d = min(closes[-20:]) if len(closes) >= 5 else None

    @property
    def macd_bullish(self) -> Optional[bool]:
        if self.macd_line is None or self.macd_signal is None:
            return None
        return self.macd_line > self.macd_signal

    @property
    def macd_rising(self) -> Optional[bool]:
        if self.macd_hist is None or self._prev_macd_hist is None:
            return None
        return self.macd_hist > self._prev_macd_hist

    @property
    def ma_score(self) -> float:
        """0-100: price position relative to whichever moving averages are
        available, weighted toward the shorter (more reactive) ones."""
        signals = []
        for ma, weight in ((self.sma20, 0.5), (self.sma50, 0.3), (self.sma200, 0.2)):
            if ma:
                pct_above = (self.last_price - ma) / ma * 100
                signals.append((_clamp(50 + pct_above * 8), weight))
        if not signals:
            return 50.0
        total_w = sum(w for _, w in signals)
        return sum(s * w for s, w in signals) / total_w

    @property
    def rsi_score(self) -> float:
        """0-100: peaks in the mid-50s (healthy uptrend, room to run),
        tapers toward the overbought/oversold extremes."""
        if self.rsi14 is None:
            return 50.0
        return _clamp(100 - abs(self.rsi14 - 55) * 1.8)

    @property
    def macd_score(self) -> float:
        if self.macd_line is None or self.macd_signal is None:
            return 50.0
        spread_pct = (self.macd_line - self.macd_signal) / self.last_price * 100 if self.last_price else 0
        score = 50 + _clamp(spread_pct * 40, -30, 30)
        if self.macd_rising is True:
            score += 5
        elif self.macd_rising is False:
            score -= 5
        return _clamp(score)

    @property
    def momentum_score(self) -> float:
        parts, weights = [], []
        if self.momentum_1m is not None:
            parts.append(_clamp(50 + self.momentum_1m * 2.5))
            weights.append(0.25)
        if self.momentum_3m is not None:
            parts.append(_clamp(50 + self.momentum_3m * 1.5))
            weights.append(0.4)
        if self.momentum_6m is not None:
            parts.append(_clamp(50 + self.momentum_6m * 1.0))
            weights.append(0.35)
        if not parts:
            return 50.0
        total_w = sum(weights)
        return sum(p * w for p, w in zip(parts, weights)) / total_w

    @property
    def trend_score(self) -> float:
        """0-100 composite: moving-average positioning, RSI health, MACD,
        and multi-timeframe momentum, equally weighted."""
        return (self.ma_score + self.rsi_score + self.macd_score + self.momentum_score) / 4


def _risk_flags(tech: LongTermTechnicalSnapshot, earnings_date: Optional[date], now: datetime) -> List[str]:
    flags = []
    if tech.rsi14 is not None and tech.rsi14 >= config.DEEPDIVE_RSI_EXTREME_OVERBOUGHT:
        flags.append(f"Extremely overbought (RSI {tech.rsi14:.0f}) -- elevated pullback risk")
    elif tech.rsi14 is not None and tech.rsi14 >= config.DEEPDIVE_RSI_OVERBOUGHT:
        flags.append(f"Overbought (RSI {tech.rsi14:.0f})")
    elif tech.rsi14 is not None and tech.rsi14 <= config.DEEPDIVE_RSI_OVERSOLD:
        flags.append(f"Oversold (RSI {tech.rsi14:.0f})")

    if tech.pct_from_high is not None and tech.pct_from_high >= -2:
        flags.append("Trading within 2% of its 52-week high")
    if tech.pct_from_low is not None and tech.pct_from_low <= 5:
        flags.append("Trading near its 52-week low")

    if tech.sma50 and tech.sma200 and tech.sma50 < tech.sma200:
        flags.append("Death cross: 50-day average below the 200-day average")

    if tech.volatility_pct is not None and tech.volatility_pct >= 4.0:
        flags.append(f"High volatility (~{tech.volatility_pct:.1f}%/day swings)")

    if earnings_date is not None:
        days_out = (earnings_date - now.date()).days
        if 0 <= days_out <= 14:
            flags.append(f"Earnings in {days_out}d ({earnings_date.isoformat()})")

    return flags


def _action_for_score(score: float, tech: LongTermTechnicalSnapshot) -> str:
    if tech.rsi14 is not None and tech.rsi14 >= config.DEEPDIVE_RSI_EXTREME_OVERBOUGHT and score >= config.DEEPDIVE_SCORE_BUY:
        return "HOLD"  # trend is strong but too extended to chase right now

    if tech.sma50 and tech.sma200 and tech.sma50 < tech.sma200 and (tech.momentum_3m or 0) < -10:
        return "SELL"  # death cross + sustained decline overrides a middling score

    if score >= config.DEEPDIVE_SCORE_BUY:
        return "BUY MORE"
    if score >= config.DEEPDIVE_SCORE_HOLD_LOW:
        return "HOLD"
    if score >= config.DEEPDIVE_SCORE_TRIM_LOW:
        return "TRIM"
    return "SELL"


def _build_reasons(tech: LongTermTechnicalSnapshot, sentiment_score: Optional[float]) -> List[str]:
    reasons = []

    if tech.sma20 and tech.sma50 and tech.sma200:
        if tech.last_price > tech.sma20 > tech.sma50 > tech.sma200:
            reasons.append("Price above rising 20/50/200-day averages (healthy uptrend alignment)")
        elif tech.last_price < tech.sma20 < tech.sma50 < tech.sma200:
            reasons.append("Price below all major moving averages (downtrend alignment)")
        elif tech.last_price > tech.sma200:
            reasons.append("Price above its 200-day average (long-term trend still up)")
        else:
            reasons.append("Price below its 200-day average (long-term trend down/uncertain)")
    elif tech.sma50:
        reasons.append(
            "Price above its 50-day average" if tech.last_price > tech.sma50
            else "Price below its 50-day average"
        )

    if tech.rsi14 is not None:
        reasons.append(f"RSI-14 at {tech.rsi14:.0f}")

    if tech.macd_bullish is not None:
        direction = "bullish (line above signal)" if tech.macd_bullish else "bearish (line below signal)"
        building = ", momentum building" if tech.macd_rising else ", momentum fading" if tech.macd_rising is False else ""
        reasons.append(f"MACD {direction}{building}")

    if tech.momentum_3m is not None:
        reasons.append(f"{tech.momentum_3m:+.1f}% over 3 months")
    if tech.momentum_6m is not None:
        reasons.append(f"{tech.momentum_6m:+.1f}% over 6 months")

    if sentiment_score is not None:
        lean = "bullish" if sentiment_score >= 55 else "bearish" if sentiment_score <= 45 else "neutral"
        reasons.append(f"News/social sentiment leans {lean} ({sentiment_score:.0f}/100)")
    else:
        reasons.append("No recent news/social mentions found -- sentiment unknown")

    return reasons


def _stop_loss(tech: LongTermTechnicalSnapshot) -> tuple:
    candidates = []
    if tech.recent_low_20d is not None and tech.recent_low_20d < tech.last_price:
        candidates.append(tech.recent_low_20d)
    if tech.sma50 is not None and tech.sma50 < tech.last_price:
        candidates.append(tech.sma50)
    if tech.sma200 is not None and tech.sma200 < tech.last_price:
        candidates.append(tech.sma200)

    if candidates:
        stop = max(candidates)  # tightest support level below current price
    else:
        stop = tech.last_price * (1 - config.DEEPDIVE_DEFAULT_STOP_PCT / 100)

    stop_pct = (tech.last_price - stop) / tech.last_price * 100 if tech.last_price else None
    return round(stop, 2), round(stop_pct, 1) if stop_pct is not None else None


def _take_profit(tech: LongTermTechnicalSnapshot, info: Optional[CompanyInfo]) -> tuple:
    if info and info.target_mean_price and info.target_mean_price > tech.last_price:
        target, basis = info.target_mean_price, "average analyst price target"
    elif tech.fifty_two_week_high and tech.fifty_two_week_high > tech.last_price:
        target, basis = tech.fifty_two_week_high, "52-week high (prior resistance)"
    else:
        target = tech.last_price * (1 + config.DEEPDIVE_DEFAULT_TARGET_PCT / 100)
        basis = f"default +{config.DEEPDIVE_DEFAULT_TARGET_PCT:.0f}% (no analyst target or nearby resistance found)"

    target_pct = (target - tech.last_price) / tech.last_price * 100 if tech.last_price else None
    return round(target, 2), round(target_pct, 1) if target_pct is not None else None, basis


def _hold_horizon(tech: LongTermTechnicalSnapshot, sentiment_score: Optional[float]) -> tuple:
    long_term_intact = (
        tech.sma200 is not None and tech.last_price > tech.sma200
        and (tech.momentum_6m or 0) > 0
    )
    momentum_only = (
        (tech.sma200 is None or tech.last_price <= tech.sma200)
        and ((tech.momentum_1m or 0) > 8 or (sentiment_score or 50) >= 65)
    )

    if long_term_intact:
        return (
            "Long-term hold (months+)",
            "Price is above a rising 200-day average with positive 6-month momentum -- "
            "the long-term trend supports staying in as long as that holds, not just this week's news.",
        )
    if momentum_only:
        return (
            "Short-term trade (days to a few weeks)",
            "The move looks driven by short-term momentum/news rather than an established "
            "long-term uptrend -- treat this as a trade with a tight stop, not a buy-and-forget position.",
        )
    return (
        "Medium-term hold (a few weeks to ~2 months)",
        "Trend signals are mixed -- reassess at the next earnings report or if price "
        "breaks the stop-loss level below.",
    )


def build_recommendation(
    ticker: str,
    price_series: PriceSeries,
    sentiment_score: Optional[float],
    company_info: Optional[CompanyInfo] = None,
    earnings_date: Optional[date] = None,
    now: Optional[datetime] = None,
) -> Recommendation:
    now = now or datetime.now(timezone.utc)
    tech = LongTermTechnicalSnapshot(price_series)

    trend_score = tech.trend_score
    if sentiment_score is not None:
        overall_score = (
            config.DEEPDIVE_WEIGHT_TREND * trend_score
            + config.DEEPDIVE_WEIGHT_SENTIMENT * sentiment_score
        )
    else:
        overall_score = trend_score

    action = _action_for_score(overall_score, tech)
    reasons = _build_reasons(tech, sentiment_score)
    risk_flags = _risk_flags(tech, earnings_date, now)
    stop_loss, stop_loss_pct = _stop_loss(tech)
    take_profit, take_profit_pct, take_profit_basis = _take_profit(tech, company_info)
    hold_horizon, hold_horizon_reason = _hold_horizon(tech, sentiment_score)

    return Recommendation(
        ticker=ticker,
        action=action,
        overall_score=round(overall_score, 1),
        trend_score=round(trend_score, 1),
        sentiment_score=round(sentiment_score, 1) if sentiment_score is not None else None,
        reasons=reasons,
        risk_flags=risk_flags,
        stop_loss=stop_loss,
        stop_loss_pct=stop_loss_pct,
        take_profit=take_profit,
        take_profit_pct=take_profit_pct,
        take_profit_basis=take_profit_basis,
        hold_horizon=hold_horizon,
        hold_horizon_reason=hold_horizon_reason,
    )
