#!/usr/bin/env python3
"""Multi-asset historical LONG backtest using the live bybit_monitor classifier.

Read-only public candles only. One global position at a time. No order execution.
"""
import argparse
import bisect
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import bybit_monitor as live

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
TIMEFRAMES = {"1h": ("60", 3_600_000), "15m": ("15", 900_000), "5m": ("5", 300_000)}
FEE = 0.0009
SLIPPAGE = 0.0001
FUNDING_HOURLY = 0.000096  # explicit stress assumption, not historical funding
MARGIN = 5.0
LEVERAGE = 2.0
NOTIONAL = MARGIN * LEVERAGE
STOP_ATR = 1.5
TARGET_R = 2.0
MAX_HOLD_HOURS = 12


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "multi-asset-long-backtest/1.0"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_history(symbol, tf, days, now_ms):
    interval, duration = TIMEFRAMES[tf]
    cutoff = now_ms - days * 86_400_000
    rows = {}
    errors = []
    cursor = now_ms
    while cursor > cutoff:
        q = urllib.parse.urlencode({"category": "linear", "symbol": symbol,
                                    "interval": interval, "limit": 1000, "end": cursor - 1})
        try:
            payload = get_json("https://api.bybit.com/v5/market/kline?" + q)
            if payload.get("retCode") != 0:
                raise RuntimeError(f"Bybit {payload.get('retCode')}: {payload.get('retMsg')}")
            batch = payload.get("result", {}).get("list", [])
            if not batch:
                break
            oldest = min(int(x[0]) for x in batch)
            for x in batch:
                ts = int(x[0])
                if cutoff <= ts and ts + duration <= now_ms:
                    rows[ts] = {"time": ts, "close_time": ts + duration - 1,
                                "open": float(x[1]), "high": float(x[2]), "low": float(x[3]),
                                "close": float(x[4]), "volume": float(x[5])}
            if oldest >= cursor or len(batch) < 2:
                break
            cursor = oldest
            time.sleep(0.05)
        except Exception as exc:
            errors.append(f"Bybit: {type(exc).__name__}: {exc}")
            rows.clear()
            break
    if len(rows) >= 60:
        return sorted(rows.values(), key=lambda x: x["time"]), "Bybit"
    # OKX fallback. Its volume unit differs; classifier's volume ratio is dimensionless.
    inst = symbol.replace("USDT", "-USDT-SWAP")
    bar = {"60": "1H", "15": "15m", "5": "5m"}[interval]
    cursor = now_ms
    rows = {}
    while cursor > cutoff:
        q = urllib.parse.urlencode({"instId": inst, "bar": bar, "limit": "300", "after": cursor})
        payload = get_json("https://www.okx.com/api/v5/market/history-candles?" + q)
        if payload.get("code") != "0":
            raise RuntimeError(f"{symbol} {tf}: {errors}; OKX {payload.get('code')}: {payload.get('msg')}")
        batch = payload.get("data", [])
        if not batch:
            break
        oldest = min(int(x[0]) for x in batch)
        for x in batch:
            ts = int(x[0])
            if len(x) >= 9 and x[8] == "1" and cutoff <= ts and ts + duration <= now_ms:
                rows[ts] = {"time": ts, "close_time": ts + duration - 1,
                            "open": float(x[1]), "high": float(x[2]), "low": float(x[3]),
                            "close": float(x[4]), "volume": float(x[6])}
        if oldest >= cursor or len(batch) < 2:
            break
        cursor = oldest
        time.sleep(0.08)
    if len(rows) < 60:
        raise RuntimeError(f"{symbol} {tf}: insufficient candles ({len(rows)}); {errors}")
    return sorted(rows.values(), key=lambda x: x["time"]), "OKX fallback"


def ema(values, period):
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1)
    v = sum(values[:period]) / period
    for x in values[period:]:
        v = alpha * x + (1 - alpha) * v
    return v


def rsi(values, period):
    if len(values) <= period:
        return None
    changes = [b - a for a, b in zip(values[:-1], values[1:])]
    gains = [max(x, 0.0) for x in changes]
    losses = [max(-x, 0.0) for x in changes]
    ag, al = sum(gains[:period]) / period, sum(losses[:period]) / period
    for g, l in zip(gains[period:], losses[period:]):
        ag = (ag * (period - 1) + g) / period
        al = (al * (period - 1) + l) / period
    return 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)


def ema_series(values, period):
    if len(values) < period:
        return []
    alpha = 2.0 / (period + 1)
    v = sum(values[:period]) / period
    out = [None] * (period - 1) + [v]
    for x in values[period:]:
        v = alpha * x + (1 - alpha) * v
        out.append(v)
    return out


def macd(values):
    fast, slow = ema_series(values, 12), ema_series(values, 26)
    if not slow:
        return {"histogram": None, "histogram_rising": False}
    line = [fast[i] - slow[i] for i in range(25, len(values))]
    sig = ema(line, 9)
    prev_sig = ema(line[:-1], 9) if len(line) > 1 else None
    hist = line[-1] - sig if sig is not None else None
    prev_hist = line[-2] - prev_sig if prev_sig is not None and len(line) > 1 else None
    return {"histogram": hist, "histogram_rising": hist is not None and prev_hist is not None and hist > prev_hist}


def snapshot(rows):
    if len(rows) < 60:
        raise ValueError("need >=60 candles")
    closes = [x["close"] for x in rows]
    volumes = [x["volume"] for x in rows]
    prior = rows[-21:-1]
    avg_vol = sum(volumes[-21:-1]) / 20 if len(rows) >= 21 else 0
    prior_high = max(x["high"] for x in prior)
    last = rows[-1]
    return {
        "close": last["close"], "high": last["high"], "low": last["low"],
        "ema20": ema(closes, 20), "ema50": ema(closes, 50),
        "rsi14": rsi(closes, 14), "rsi6": rsi(closes, 6),
        "macd": macd(closes), "volume_ratio_20": volumes[-1] / avg_vol if avg_vol else None,
        "false_breakout": last["high"] > prior_high and last["close"] < prior_high,
    }


def atr(rows, period=14):
    if len(rows) < period + 1:
        return None
    trs = [max(c["high"] - c["low"], abs(c["high"] - p["close"]),
               abs(c["low"] - p["close"])) for p, c in zip(rows[:-1], rows[1:])]
    value = sum(trs[:period]) / period
    for tr in trs[period:]:
        value = (value * (period - 1) + tr) / period
    return value


def metrics(trades, days, sources, counts):
    wins = [x for x in trades if x["net_pnl_usdc"] > 0]
    losses = [x for x in trades if x["net_pnl_usdc"] <= 0]
    gross_win = sum(x["net_pnl_usdc"] for x in wins)
    gross_loss = abs(sum(x["net_pnl_usdc"] for x in losses))
    equity = peak = max_dd = 0.0
    streak = current = 0
    for x in trades:
        equity += x["net_pnl_usdc"]
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        if x["net_pnl_usdc"] <= 0:
            current += 1
            streak = max(streak, current)
        else:
            current = 0
    return {
        "period_days": days, "symbols": list(SYMBOLS), "candles": counts, "data_sources": sources,
        "trades": len(trades), "wins": len(wins), "losses": len(losses),
        "win_rate_pct": round(100 * len(wins) / len(trades), 2) if trades else 0,
        "gross_pnl_usdc": round(sum(x["gross_pnl_usdc"] for x in trades), 6),
        "fees_usdc": round(sum(x["fees_usdc"] for x in trades), 6),
        "funding_usdc": round(sum(x["funding_usdc"] for x in trades), 6),
        "net_pnl_usdc": round(sum(x["net_pnl_usdc"] for x in trades), 6),
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss else None,
        "max_drawdown_usdc": round(max_dd, 6), "max_consecutive_losses": streak,
        "assumptions": {"margin_usdc": MARGIN, "leverage": LEVERAGE, "one_global_position": True,
                        "fee_per_side": FEE, "slippage_per_side": SLIPPAGE,
                        "funding_hourly_stress": FUNDING_HOURLY,
                        "funding_note": "fixed stress assumption; historical funding not yet integrated",
                        "stop": f"{STOP_ATR}x ATR(14)", "target_R": TARGET_R,
                        "max_hold_hours": MAX_HOLD_HOURS, "same_bar_stop_target": "stop first"}
    }


def run(days):
    now = int(time.time() * 1000)
    data, sources, counts = {}, {}, {}
    for symbol in SYMBOLS:
        data[symbol] = {}
        sources[symbol] = {}
        counts[symbol] = {}
        for tf in TIMEFRAMES:
            rows, source = fetch_history(symbol, tf, days, now)
            data[symbol][tf] = rows
            sources[symbol][tf] = source
            counts[symbol][tf] = len(rows)
    # Hourly close times form the decision clock; each lower-TF snapshot uses only closed candles.
    clocks = {s: {tf: [x["close_time"] for x in data[s][tf]] for tf in TIMEFRAMES} for s in SYMBOLS}
    decisions = sorted(set(t for s in SYMBOLS for t in clocks[s]["1h"][60:]))
    trades, next_free = [], 0
    for signal_time in decisions:
        if signal_time < next_free:
            continue
        candidates = []
        btc_j = bisect.bisect_right(clocks["BTCUSDT"]["1h"], signal_time)
        if btc_j < 60:
            continue
        btc_item = {"1h": snapshot(data["BTCUSDT"]["1h"][:btc_j])}
        for symbol in SYMBOLS:
            idx = {}
            ok = True
            for tf in TIMEFRAMES:
                j = bisect.bisect_right(clocks[symbol][tf], signal_time)
                if j < 60:
                    ok = False
                    break
                idx[tf] = j
            if not ok:
                continue
            if symbol == "BTCUSDT":
                item = btc_item.copy()
                item["15m"] = snapshot(data[symbol]["15m"][:idx["15m"]])
                item["5m"] = snapshot(data[symbol]["5m"][:idx["5m"]])
            else:
                item = {tf: snapshot(data[symbol][tf][:idx[tf]]) for tf in TIMEFRAMES}
            if live.classify_symbol(symbol, item, btc_item) == "LONG":
                entry_i = idx["5m"]
                if entry_i >= len(data[symbol]["5m"]):
                    continue
                candidates.append((symbol, item, entry_i))
        if not candidates:
            continue
        # Deterministic tie-break: BTC, then ETH, then SOL.
        symbol, item, entry_i = candidates[0]
        bars = data[symbol]["5m"]
        entry_bar = bars[entry_i]
        entry = entry_bar["open"] * (1 + SLIPPAGE)
        h1j = bisect.bisect_right(clocks[symbol]["1h"], signal_time)
        current_atr = atr(data[symbol]["1h"][:h1j])
        if not current_atr or current_atr <= 0:
            continue
        stop = entry - STOP_ATR * current_atr
        target = entry + TARGET_R * (entry - stop)
        exit_i = min(len(bars) - 1, entry_i + MAX_HOLD_HOURS * 12)
        exit_price, exit_time, reason = None, None, "TIME"
        for k in range(entry_i, exit_i + 1):
            bar = bars[k]
            if bar["low"] <= stop:
                exit_price, exit_time, reason = stop, bar["close_time"], "STOP"
                break
            if bar["high"] >= target:
                exit_price, exit_time, reason = target, bar["close_time"], "TARGET"
                break
        if exit_price is None:
            exit_price, exit_time = bars[exit_i]["close"], bars[exit_i]["close_time"]
        fill = exit_price * (1 - SLIPPAGE)
        gross = NOTIONAL * (fill / entry - 1)
        fees = NOTIONAL * FEE + NOTIONAL * (fill / entry) * FEE
        held = max(0.0, (exit_time - entry_bar["time"]) / 3_600_000)
        funding = NOTIONAL * FUNDING_HOURLY * held
        net = gross - fees - funding
        trades.append({"symbol": symbol,
                       "signal_time_utc": datetime.fromtimestamp(signal_time/1000, timezone.utc).isoformat(),
                       "entry_time_utc": datetime.fromtimestamp(entry_bar["time"]/1000, timezone.utc).isoformat(),
                       "exit_time_utc": datetime.fromtimestamp(exit_time/1000, timezone.utc).isoformat(),
                       "scenario": "LIVE_CLASSIFIER_LONG", "entry": round(entry, 8),
                       "stop": round(stop, 8), "target": round(target, 8), "exit": round(fill, 8),
                       "exit_reason": reason, "held_hours": round(held, 3),
                       "gross_pnl_usdc": round(gross, 6), "fees_usdc": round(fees, 6),
                       "funding_usdc": round(funding, 6), "net_pnl_usdc": round(net, 6)})
        next_free = exit_time
    return {"generated_at": datetime.now(timezone.utc).isoformat(),
            "strategy": "bybit_monitor.classify_symbol shared live classifier; LONG only",
            "results": metrics(trades, days, sources, counts), "trades_detail": trades}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--output", default="data/multi_asset_backtest.json")
    a = p.parse_args()
    if a.days < 7 or a.days > 180:
        p.error("--days must be 7..180")
    report = run(a.days)
    import os
    os.makedirs(os.path.dirname(a.output) or ".", exist_ok=True)
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
    print(json.dumps(report["results"], ensure_ascii=False, indent=2))
