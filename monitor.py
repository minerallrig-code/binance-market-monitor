#!/usr/bin/env python3
"""Read-only Bybit USDT linear futures monitor. Never places or modifies orders."""
import json
import math
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE_URL = "https://api.bybit.com"
CATEGORY = "linear"
SYMBOL = "BTCUSDT"
INTERVALS = {"1h": "60", "15m": "15", "5m": "5"}
LIMIT = 300
USER_AGENT = "bybit-long-monitor/1.0"


def fetch_klines(symbol=SYMBOL, interval="60", limit=LIMIT):
    query = urllib.parse.urlencode({
        "category": CATEGORY, "symbol": symbol,
        "interval": interval, "limit": limit,
    })
    request = urllib.request.Request(
        f"{BASE_URL}/v5/market/kline?{query}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("retCode") != 0:
        raise RuntimeError(f"Bybit retCode={payload.get('retCode')}: {payload.get('retMsg')}")
    now_ms = int(time.time() * 1000)
    candles = []
    for k in payload.get("result", {}).get("list", []):
        start, open_, high, low, close, volume, turnover = k
        start_ms = int(start)
        duration_ms = int(interval) * 60_000
        if start_ms + duration_ms <= now_ms:
            candles.append({
                "time": start_ms, "close_time": start_ms + duration_ms - 1,
                "open": float(open_), "high": float(high), "low": float(low),
                "close": float(close), "volume": float(volume),
                "turnover": float(turnover),
            })
    return sorted(candles, key=lambda x: x["time"])


def ema(values, period):
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1)
    value = sum(values[:period]) / period
    for item in values[period:]:
        value = item * alpha + value * (1 - alpha)
    return value


def rsi(values, period):
    if len(values) <= period:
        return None
    changes = [b - a for a, b in zip(values[:-1], values[1:])]
    gains = [max(x, 0.0) for x in changes]
    losses = [max(-x, 0.0) for x in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def macd(values):
    if len(values) < 35:
        return None
    line = []
    for end in range(26, len(values) + 1):
        line.append(ema(values[:end], 12) - ema(values[:end], 26))
    signal = ema(line, 9)
    hist = line[-1] - signal if signal is not None else None
    previous_hist = line[-2] - ema(line[:-1], 9) if len(line) > 1 and len(line[:-1]) >= 9 else None
    return {"dif": line[-1], "dea": signal, "histogram": hist,
            "histogram_previous": previous_hist,
            "histogram_rising": hist is not None and previous_hist is not None and hist > previous_hist}


def mean(values):
    return sum(values) / len(values) if values else None


def analyze(candles):
    if len(candles) < 60:
        raise ValueError(f"Need at least 60 closed candles; got {len(candles)}")
    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]
    e20, e50 = ema(closes, 20), ema(closes, 50)
    macd_data = macd(closes)
    last = candles[-1]
    volume_ma5, volume_ma10 = mean(volumes[-5:]), mean(volumes[-10:])
    swing = candles[-50:]
    swing_high = max(c["high"] for c in swing)
    swing_low = min(c["low"] for c in swing)
    span = swing_high - swing_low
    fib = ({str(level): swing_high - span * level for level in (0.5, 0.618, 0.786)}
           if span > 0 else {})
    return {
        "candle_time": datetime.fromtimestamp(last["time"] / 1000, timezone.utc).isoformat(),
        "close": last["close"], "high": last["high"], "low": last["low"],
        "ema20": e20, "ema50": e50,
        "rsi6": rsi(closes, 6), "rsi12": rsi(closes, 12),
        "rsi14": rsi(closes, 14), "rsi24": rsi(closes, 24),
        "macd": macd_data, "volume": last["volume"],
        "volume_ma5": volume_ma5, "volume_ma10": volume_ma10,
        "volume_vs_ma5": last["volume"] / volume_ma5 if volume_ma5 else None,
        "volume_vs_ma10": last["volume"] / volume_ma10 if volume_ma10 else None,
        "swing_high_50": swing_high, "swing_low_50": swing_low,
        "fibonacci_retracement": fib,
    }


def classify_long(data):
    """Conservative setup classifier; a signal is not an order recommendation."""
    h1, m15, m5 = data["1h"], data["15m"], data["5m"]
    trend = h1["ema20"] > h1["ema50"]
    momentum = (m15["close"] > m15["ema20"]
                and m15["macd"]["histogram"] is not None
                and m15["macd"]["histogram"] > 0
                and m15["rsi14"] is not None
                and 50 <= m15["rsi14"] <= 70)
    volume_ok = m15["volume_vs_ma5"] is not None and m15["volume_vs_ma5"] >= 0.8
    early = (m5["macd"]["histogram_rising"]
             and m5["rsi6"] is not None and m5["rsi6"] > 50
             and m5["close"] > m5["ema20"])
    continuation = trend and momentum and volume_ok and early

    # Reversal candidate after a sharp 1h decline; requires lower-TF confirmation.
    h1_drop = ((h1["close"] / h1["swing_high_50"]) - 1) if h1["swing_high_50"] else 0
    seller_spike = h1["volume_vs_ma10"] if "volume_vs_ma10" in h1 else None
    reversal = (h1_drop <= -0.015
                and h1["macd"]["histogram_rising"]
                and m5["macd"]["histogram_rising"]
                and m5["rsi6"] is not None and m5["rsi6"] >= 35
                and m15["macd"]["histogram"] is not None
                and m15["macd"]["histogram"] > 0
                and m15["close"] > m15["ema20"]
                and volume_ok)
    if continuation:
        scenario = "A_TREND_CONTINUATION"
    elif reversal:
        scenario = "B_REVERSAL_AFTER_DROP"
    else:
        scenario = "WAIT"
    return {
        "signal": "LONG_CANDIDATE" if scenario != "WAIT" else "WAIT",
        "scenario": scenario,
        "checks": {
            "1h_ema20_above_ema50": trend,
            "15m_momentum_confirmed": momentum,
            "15m_volume_ok": volume_ok,
            "5m_early_confirmation": early,
            "1h_drop_from_50_candle_high": h1_drop,
            "1h_macd_histogram_rising": h1["macd"]["histogram_rising"],
        },
        "note": "Candidate only. Verify live Walt balance/positions and calculate SL/TP; no orders are sent.",
    }


def main():
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Bybit USDT Linear Futures public market data",
        "category": CATEGORY, "symbol": SYMBOL,
        "disclaimer": "Analytics only. No orders are placed, cancelled or modified.",
        "timeframes": {}, "errors": [],
    }
    for label, interval in INTERVALS.items():
        try:
            result["timeframes"][label] = analyze(fetch_klines(interval=interval))
        except Exception as exc:
            result["errors"].append(f"{label}: {type(exc).__name__}: {exc}")
    if len(result["timeframes"]) == 3:
        result["decision"] = classify_long(result["timeframes"])
    else:
        result["decision"] = {
            "signal": "WAIT", "scenario": "DATA_UNAVAILABLE",
            "note": "One or more required timeframes unavailable; fail closed.",
        }
    os.makedirs("data", exist_ok=True)
    with open("data/latest.json", "w", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({
        "generated_at": result["generated_at"],
        "signal": result["decision"]["signal"],
        "scenario": result["decision"]["scenario"],
        "errors": result["errors"],
    }, ensure_ascii=False, indent=2))
    if result["errors"]:
        raise SystemExit("Incomplete Bybit data; decision forced to WAIT. See data/latest.json")


if __name__ == "__main__":
    main()
