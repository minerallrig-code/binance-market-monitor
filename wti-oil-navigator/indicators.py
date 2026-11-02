"""Dependency-free indicators for closed Lighter OHLCV candles."""
from __future__ import annotations

from math import isfinite
from typing import Any


def _ema(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    alpha = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    result = [float("nan")] * (period - 1) + [seed]
    current = seed
    for value in values[period:]:
        current = value * alpha + current * (1.0 - alpha)
        result.append(current)
    return result


def _rsi(values: list[float], period: int) -> float | None:
    if len(values) <= period:
        return None
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(candles: list[dict[str, Any]], period: int = 14) -> float | None:
    if len(candles) <= period:
        return None
    true_ranges = []
    previous_close = float(candles[0]["c"])
    for candle in candles[1:]:
        high, low, close = float(candle["h"]), float(candle["l"]), float(candle["c"])
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
        previous_close = close
    if len(true_ranges) < period:
        return None
    value = sum(true_ranges[:period]) / period
    for tr in true_ranges[period:]:
        value = ((value * (period - 1)) + tr) / period
    return value


def analyze_timeframe(candles: list[dict[str, Any]]) -> dict[str, Any]:
    if len(candles) < 60:
        raise ValueError(f"Need at least 60 closed candles, got {len(candles)}")
    ordered = sorted(candles, key=lambda candle: int(candle["t"]))
    closes = [float(candle["c"]) for candle in ordered]
    volumes = [float(candle.get("v", 0.0)) for candle in ordered]
    if not all(isfinite(value) for value in closes + volumes):
        raise ValueError("Non-finite OHLCV value")
    ema20 = _ema(closes, 20)[-1]
    ema50 = _ema(closes, 50)[-1]
    ema12_series = _ema(closes, 12)
    ema26_series = _ema(closes, 26)
    macd_line = [fast - slow for fast, slow in zip(ema12_series, ema26_series) if isfinite(fast) and isfinite(slow)]
    signal_series = _ema(macd_line, 9)
    macd = macd_line[-1] if macd_line else None
    macd_signal = signal_series[-1] if signal_series else None
    histogram = (macd - macd_signal) if macd is not None and macd_signal is not None else None
    last_close = closes[-1]
    if last_close > ema20 > ema50:
        trend = "BULLISH"
    elif last_close < ema20 < ema50:
        trend = "BEARISH"
    else:
        trend = "RANGE_OR_MIXED"
    average_volume = sum(volumes[-21:-1]) / 20
    volume_ratio = volumes[-1] / average_volume if average_volume > 0 else None
    return {
        "last_close": round(last_close, 4),
        "ema20": round(ema20, 4),
        "ema50": round(ema50, 4),
        "rsi6": round(_rsi(closes, 6), 2) if _rsi(closes, 6) is not None else None,
        "rsi14": round(_rsi(closes, 14), 2) if _rsi(closes, 14) is not None else None,
        "rsi24": round(_rsi(closes, 24), 2) if _rsi(closes, 24) is not None else None,
        "macd": round(macd, 6) if macd is not None else None,
        "macd_signal": round(macd_signal, 6) if macd_signal is not None else None,
        "macd_histogram": round(histogram, 6) if histogram is not None else None,
        "atr14": round(_atr(ordered), 5) if _atr(ordered) is not None else None,
        "volume_ratio_vs_20": round(volume_ratio, 2) if volume_ratio is not None else None,
        "trend": trend,
    }


def analyze_all_timeframes(timeframes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for name, data in timeframes.items():
        result[name] = analyze_timeframe(data["candles"])
    long_votes = sum(result.get(tf, {}).get("trend") == "BULLISH" for tf in ("1d", "4h", "1h"))
    short_votes = sum(result.get(tf, {}).get("trend") == "BEARISH" for tf in ("1d", "4h", "1h"))
    if long_votes >= 2 and short_votes == 0:
        bias = "BULLISH"
    elif short_votes >= 2 and long_votes == 0:
        bias = "BEARISH"
    else:
        bias = "MIXED"
    return {
        "timeframes": result,
        "higher_timeframe_bias": bias,
        "signal": "WAIT",
        "signal_status": "TECHNICAL_CONTEXT_ONLY",
        "reason": "Entry rules and news confirmation are not yet calibrated/backtested; no trade signal is emitted.",
    }
