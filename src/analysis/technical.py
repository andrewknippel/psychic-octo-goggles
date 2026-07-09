"""Price/volume-derived technical signals, tuned for a 2-7 day horizon.

Deliberately short lookbacks (3-day/5-day returns, RSI-7) rather than the
more common RSI-14/50-day-MA setups used for swing/position trading -- those
are too slow-moving to say anything useful about a one-week window.
"""
import math
from typing import Optional

from src.models import PriceSeries


def _pct_change(closes: list, days_ago: int) -> Optional[float]:
    if len(closes) <= days_ago:
        return None
    return (closes[-1] - closes[-1 - days_ago]) / closes[-1 - days_ago] * 100


def _rsi(closes: list, period: int = 7) -> Optional[float]:
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


def _sma(values: list, period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


class TechnicalSnapshot:
    def __init__(self, series: PriceSeries):
        closes = series.close
        volumes = series.volume

        self.last_price = closes[-1] if closes else 0.0
        self.change_3d_pct = _pct_change(closes, 3)
        self.change_5d_pct = _pct_change(closes, 5)
        self.rsi = _rsi(closes, period=7)

        avg_volume_20 = _sma(volumes, 20) or _sma(volumes, len(volumes))
        self.avg_volume_20 = avg_volume_20 or 0.0
        last_volume = volumes[-1] if volumes else 0.0
        self.volume_surge = (
            last_volume / avg_volume_20 if avg_volume_20 else 1.0
        )

        self.sma5 = _sma(closes, 5)
        self.sma10 = _sma(closes, 10)

    @property
    def momentum_score(self) -> float:
        """0-100: blends 3-day, 5-day return and short MA trend."""
        parts, weights = [], []

        if self.change_3d_pct is not None:
            parts.append(_clamp(50 + self.change_3d_pct * 5))
            weights.append(0.4)
        if self.change_5d_pct is not None:
            parts.append(_clamp(50 + self.change_5d_pct * 4))
            weights.append(0.3)
        if self.sma5 is not None and self.sma10 is not None and self.sma10:
            trend_pct = (self.sma5 - self.sma10) / self.sma10 * 100
            parts.append(_clamp(50 + trend_pct * 8))
            weights.append(0.3)

        if not parts:
            return 50.0
        total_w = sum(weights)
        return sum(p * w for p, w in zip(parts, weights)) / total_w

    @property
    def volume_score(self) -> float:
        """0-100: log-scaled surge relative to the 20-day average volume."""
        surge = max(self.volume_surge, 1e-6)
        return _clamp(50 + 25 * math.log2(surge))

    @property
    def technical_score(self) -> float:
        """0-100: RSI positioned for continuation (not overbought/oversold)
        combined with short-term MA trend confirmation."""
        if self.rsi is None:
            rsi_health = 50.0
        else:
            # Peaks around RSI 60 (rising, room to run); tapers toward the
            # extremes where reversal risk is higher.
            rsi_health = _clamp(100 - abs(self.rsi - 60) * 2.2)

        if self.sma5 is not None and self.sma10 is not None and self.sma10:
            trend_pct = (self.sma5 - self.sma10) / self.sma10 * 100
            trend_score = _clamp(50 + trend_pct * 10)
        else:
            trend_score = 50.0

        return rsi_health * 0.6 + trend_score * 0.4
