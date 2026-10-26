#!/usr/bin/env python3
"""Read-only Bybit USDT linear perpetual market monitor. Never places orders."""
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
INTERVALS = {"1h": "60", "15m": "15"}
BASE = "https://api.bybit.com"
LIMIT = 250


def fetch_klines(symbol, interval):
    query = urllib.parse.urlencode({
        "category": "linear", "symbol": symbol,
        "interval": interval, "limit": LIMIT,
    })
    request = urllib.request.Request(
        f"{BASE}/v5/market/kline?{query}",
        headers={"User-Agent": "bybit-market-monitor/1.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("retCode") != 0:
        raise RuntimeError(payload.get("retMsg", "Bybit API error"))
    now_ms = int(time.time() * 1000)
    candles = []
    for k in reversed(payload.get("result", {}).get("list", [])):
        start, close_time = int(k[0]), int(k[0]) + int(interval) * 60_000 - 1
        if close_time < now_ms:
            candles.append({
                "time": start, "close_time": close_time,
                "open": float(k[1]), "high": float(k[2]),
                "low": float(k[3]), "close": float(k[4]),
                "volume": float(k[5]),
            })
    return candles


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
    changes = [b - a for a, b in zip(values[:-1], values[1:])]
    gain = sum(max(x, 0.0) for x in changes[:period]) / period
    loss = sum(max(-x, 0.0) for x in changes[:period]) / period
    for change in changes[period:]:
        gain = (gain * (period - 1) + max(change, 0.0)) / period
        loss = (loss * (period - 1) + max(-change, 0.0)) / period
    if loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + gain / loss)


def macd(values):
    line = []
    for end in range(26, len(values) + 1):
        fast, slow = ema(values[:end], 12), ema(values[:end], 26)
        line.append(fast - slow)
    signal = ema(line, 9)
    current = ema(values, 12) - ema(values, 26)
    return {
        "line": current, "signal": signal,
        "histogram": current - signal if signal is not None else None,
    }


def analyze(candles):
    if len(candles) < 60:
        raise ValueError(f"Not enough closed candles: {len(candles)}")
    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]
    e20, e50, r, m = ema(closes, 20), ema(closes, 50), rsi(closes), macd(closes)
    avg_volume = sum(volumes[-21:-1]) / 20
    return {
        "candle_time": datetime.fromtimestamp(candles[-1]["time"] / 1000, timezone.utc).isoformat(),
        "close": closes[-1], "ema20": e20, "ema50": e50, "rsi14": r,
        "macd": m, "volume": volumes[-1], "volume_avg20": avg_volume,
        "volume_ratio_20": volumes[-1] / avg_volume if avg_volume else None,
    }


def main():
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "exchange": "Bybit", "market": "USDT linear perpetual",
        "strategy": "LONG only; 1h trend + 15m confirmation; closed candles only",
        "disclaimer": "Analytics only. No orders are placed, cancelled, or modified.",
        "symbols": {}, "errors": [],
    }
    for symbol in SYMBOLS:
        item = {}
        for label, interval in INTERVALS.items():
            try:
                item[label] = analyze(fetch_klines(symbol, interval))
            except Exception as exc:
                item[label] = {"signal": "UNAVAILABLE", "error": str(exc)}
                output["errors"].append(f"{symbol} {label}: {type(exc).__name__}: {exc}")
            time.sleep(0.1)
        h, m = item.get("1h", {}), item.get("15m", {})
        if "error" in h or "error" in m:
            signal = "UNAVAILABLE"
        else:
            trend_ok = h["ema20"] > h["ema50"] and h["close"] > h["ema20"]
            entry_ok = (m["close"] > m["ema20"] and 50 <= m["rsi14"] <= 70
                        and m["macd"]["histogram"] is not None
                        and m["macd"]["histogram"] > 0)
            signal = "LONG" if trend_ok and entry_ok else "WAIT"
        item["signal"] = signal
        item["reason"] = (
            "1h bullish trend and 15m momentum confirmed"
            if signal == "LONG" else
            "No complete long confirmation on closed 1h/15m candles"
            if signal == "WAIT" else "Market data unavailable; no signal"
        )
        output["symbols"][symbol] = item

    with open("data/bybit_latest.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
    print(json.dumps({
        "generated_at": output["generated_at"],
        "signals": {s: v["signal"] for s, v in output["symbols"].items()},
        "errors": len(output["errors"]),
    }, ensure_ascii=False, indent=2))
    if len(output["errors"]) == len(SYMBOLS) * len(INTERVALS):
        raise SystemExit("All Bybit candle requests failed")


if __name__ == "__main__":
    main()
