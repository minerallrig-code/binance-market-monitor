#!/usr/bin/env python3
"""Read-only perpetual market monitor. Uses Bybit first, OKX public candles as fallback. Never places orders."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
INTERVALS = {"1h": "60", "15m": "15"}
BYBIT_HOSTS = ["https://api.bybit.com", "https://api.bytick.com"]
OKX_INST = {"BTCUSDT": "BTC-USDT-SWAP", "ETHUSDT": "ETH-USDT-SWAP", "SOLUSDT": "SOL-USDT-SWAP"}
OKX_BAR = {"1h": "1H", "15m": "15m"}
LIMIT = 250
ERRORS = []


def get_json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; market-monitor/2.0)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_bybit(symbol, interval):
    query = urllib.parse.urlencode({
        "category": "linear", "symbol": symbol,
        "interval": interval, "limit": LIMIT,
    })
    failures = []
    for host in BYBIT_HOSTS:
        try:
            payload = get_json(f"{host}/v5/market/kline?{query}")
            if payload.get("retCode") != 0:
                raise RuntimeError(f"retCode={payload.get('retCode')}: {payload.get('retMsg')}")
            rows = payload.get("result", {}).get("list", [])
            now_ms = int(time.time() * 1000)
            candles = []
            for k in reversed(rows):
                start = int(k[0])
                close_time = start + int(interval) * 60_000 - 1
                if close_time < now_ms:
                    candles.append({
                        "time": start, "close_time": close_time,
                        "open": float(k[1]), "high": float(k[2]),
                        "low": float(k[3]), "close": float(k[4]),
                        "volume": float(k[5]),
                    })
            if len(candles) < 60:
                raise RuntimeError(f"Only {len(candles)} closed candles returned")
            return candles, "Bybit"
        except Exception as exc:
            failures.append(f"{host}: {type(exc).__name__}: {exc}")
    raise RuntimeError(" | ".join(failures))


def fetch_okx(symbol, label):
    inst = OKX_INST[symbol]
    query = urllib.parse.urlencode({"instId": inst, "bar": OKX_BAR[label], "limit": str(LIMIT)})
    payload = get_json(f"https://www.okx.com/api/v5/market/candles?{query}")
    if payload.get("code") != "0":
        raise RuntimeError(f"OKX code={payload.get('code')}: {payload.get('msg')}")
    now_ms = int(time.time() * 1000)
    candles = []
    # OKX row: ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm
    for k in reversed(payload.get("data", [])):
        if len(k) < 9 or k[8] != "1":
            continue
        start = int(k[0])
        candles.append({
            "time": start, "close_time": start,
            "open": float(k[1]), "high": float(k[2]),
            "low": float(k[3]), "close": float(k[4]),
            "volume": float(k[6]),  # base-asset volume; venue-specific
        })
    if len(candles) < 60:
        raise RuntimeError(f"OKX returned only {len(candles)} confirmed candles")
    return candles, "OKX fallback"


def fetch_klines(symbol, label, interval):
    try:
        return fetch_bybit(symbol, interval)
    except Exception as bybit_exc:
        ERRORS.append(f"{symbol} {label} Bybit: {bybit_exc}")
        try:
            return fetch_okx(symbol, label)
        except Exception as okx_exc:
            raise RuntimeError(f"Bybit failed ({bybit_exc}); OKX fallback failed ({type(okx_exc).__name__}: {okx_exc})")


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


def macd_series(values):
    series = []
    for end in range(26, len(values) + 1):
        series.append(ema(values[:end], 12) - ema(values[:end], 26))
    signal = ema(series, 9)
    current = series[-1] if series else None
    previous_signal = ema(series[:-1], 9) if len(series) > 1 else None
    previous = series[-2] if len(series) > 1 else None
    hist = current - signal if signal is not None else None
    prev_hist = previous - previous_signal if previous is not None and previous_signal is not None else None
    return {"line": current, "signal": signal, "histogram": hist,
            "previous_histogram": prev_hist,
            "histogram_rising": hist is not None and prev_hist is not None and hist > prev_hist}


def analyze(candles):
    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]
    e20, e50, r, m = ema(closes, 20), ema(closes, 50), rsi(closes), macd_series(closes)
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
        "primary_exchange": "Bybit", "fallback_exchange": "OKX",
        "market": "USDT perpetual swaps",
        "strategy": "LONG only; 1h trend + 15m confirmation; confirmed/closed candles only",
        "disclaimer": "Analytics only. No orders are placed, cancelled, or modified. OKX fallback volume is not directly comparable to Bybit volume.",
        "symbols": {}, "errors": ERRORS,
    }
    failures = 0
    for symbol in SYMBOLS:
        item = {}
        for label, interval in INTERVALS.items():
            try:
                candles, source = fetch_klines(symbol, label, interval)
                item[label] = analyze(candles)
                item[label]["data_source"] = source
                item[label]["candles"] = len(candles)
            except Exception as exc:
                failures += 1
                item[label] = {"signal": "UNAVAILABLE", "error": str(exc)}
                output["errors"].append(f"{symbol} {label}: {type(exc).__name__}: {exc}")
            time.sleep(0.15)
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
        item["volume_caution"] = "Compare volume with your Bybit chart only when data_source is Bybit."
        output["symbols"][symbol] = item

    with open("data/bybit_latest.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
    print(json.dumps({
        "generated_at": output["generated_at"],
        "signals": {s: v["signal"] for s, v in output["symbols"].items()},
        "sources": {s: {tf: v.get("data_source", "UNAVAILABLE") for tf, v in v.items() if tf in INTERVALS}
                    for s, v in output["symbols"].items()},
        "errors": failures,
        "bybit_fallbacks": len(output["errors"]),
    }, ensure_ascii=False, indent=2))
    if failures == len(SYMBOLS) * len(INTERVALS):
        raise SystemExit("All primary and fallback candle requests failed")


if __name__ == "__main__":
    main()
