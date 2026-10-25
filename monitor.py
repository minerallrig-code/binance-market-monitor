#!/usr/bin/env python3
"""Read-only Binance market monitor. No trading or API keys required."""
import json
import math
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SYMBOLS = ["BTCUSDT", "SOLUSDT", "ZECUSDT", "HYPEUSDT", "WLDUSDT"]
INTERVALS = ["15m", "4h"]
LIMIT = 250
SPOT_BASE = "https://data-api.binance.vision"


def fetch_klines(base, market, symbol, interval):
    path = "/api/v3/klines" if market == "spot" else "/fapi/v1/klines"
    query = urllib.parse.urlencode({"symbol": symbol, "interval": interval, "limit": LIMIT})
    request = urllib.request.Request(
        f"{base}{path}?{query}",
        headers={"User-Agent": "binance-market-monitor/1.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = json.loads(response.read().decode("utf-8"))
    now_ms = int(time.time() * 1000)
    # Ignore the still-forming candle.
    return [
        {"time": int(k[0]), "close_time": int(k[6]), "open": float(k[1]),
         "high": float(k[2]), "low": float(k[3]), "close": float(k[4]),
         "volume": float(k[5])}
        for k in raw if int(k[6]) < now_ms
    ]


def ema(values, period):
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1)
    value = sum(values[:period]) / period
    for item in values[period:]:
        value = item * alpha + value * (1 - alpha)
    return value


def rsi(values, period=14):
    if len(values) <= period:
        return None
    gains, losses = [], []
    for a, b in zip(values[:-1], values[1:]):
        change = b - a
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))


def macd(values):
    fast, slow = ema(values, 12), ema(values, 26)
    if fast is None or slow is None:
        return None
    # Build the MACD line series to calculate its 9-period signal line.
    line = []
    for end in range(26, len(values) + 1):
        f, s = ema(values[:end], 12), ema(values[:end], 26)
        if f is not None and s is not None:
            line.append(f - s)
    signal = ema(line, 9)
    current = fast - slow
    return {"line": current, "signal": signal,
            "histogram": current - signal if signal is not None else None}


def analyze(candles):
    if len(candles) < 60:
        raise ValueError(f"Not enough closed candles: {len(candles)}")
    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]
    e20, e50 = ema(closes, 20), ema(closes, 50)
    r = rsi(closes)
    m = macd(closes)
    avg_volume = sum(volumes[-21:-1]) / min(20, len(volumes[-21:-1]))
    last_volume = volumes[-1]
    volume_ratio = last_volume / avg_volume if avg_volume else None

    long_ok = e20 > e50 and closes[-1] > e20 and r is not None and 50 <= r <= 70 and m and m["histogram"] is not None and m["histogram"] > 0
    short_ok = e20 < e50 and closes[-1] < e20 and r is not None and 30 <= r <= 50 and m and m["histogram"] is not None and m["histogram"] < 0
    signal = "LONG" if long_ok else "SHORT" if short_ok else "WAIT"
    return {
        "candle_time": datetime.fromtimestamp(candles[-1]["time"] / 1000, timezone.utc).isoformat(),
        "close": closes[-1], "ema20": e20, "ema50": e50, "rsi14": r,
        "macd": m, "volume": last_volume, "volume_avg20": avg_volume,
        "volume_ratio_20": volume_ratio, "signal": signal,
    }


def main():
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "Analytics only. No orders are placed or modified.",
        "markets": {},
        "errors": [],
    }
    for market, base in (("spot", SPOT_BASE),):
        result["markets"][market] = {}
        for symbol in SYMBOLS:
            result["markets"][market][symbol] = {}
            for interval in INTERVALS:
                try:
                    candles = fetch_klines(base, market, symbol, interval)
                    result["markets"][market][symbol][interval] = analyze(candles)
                except Exception as exc:
                    message = f"{market} {symbol} {interval}: {type(exc).__name__}: {exc}"
                    result["errors"].append(message)
                    result["markets"][market][symbol][interval] = {"signal": "UNAVAILABLE", "error": str(exc)}
                time.sleep(0.08)
    os.makedirs("data", exist_ok=True)
    with open("data/latest.json", "w", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({"generated_at": result["generated_at"], "errors": len(result["errors"])}, indent=2))
    # A partial API outage should still preserve diagnostics and the latest successful data.
    if len(result["errors"]) == len(SYMBOLS) * len(INTERVALS) * 2:
        raise SystemExit("All Binance market requests failed; inspect data/latest.json")


if __name__ == "__main__":
    main()
