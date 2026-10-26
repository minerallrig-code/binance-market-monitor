#!/usr/bin/env python3
"""Historical, read-only backtest for the Bybit BTCUSDT LONG monitor.

Downloads public Bybit V5 candles. No keys, wallet access, or order execution.
Conservative execution model: next 5m open, market slippage + taker fees,
hourly funding paid by longs, ATR stop, 2R target, stop-first on ambiguous bars.
"""
import argparse
import json
import math
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import monitor

BASE = "https://api.bybit.com"
SYMBOL = "BTCUSDT"
CATEGORY = "linear"
FEE_RATE = 0.0009       # taker fee per side; conservative configured assumption
SLIPPAGE_RATE = 0.0001  # 1 bp adverse per side; assumption, not exchange quote
FUNDING_RATE_HOURLY = 0.000096  # positive funding: long pays; fixed stress assumption
MARGIN_USDC = 5.0
LEVERAGE = 2.0
NOTIONAL = MARGIN_USDC * LEVERAGE
ATR_PERIOD = 14
STOP_ATR = 1.5
TARGET_R = 2.0
MAX_HOLD_HOURS = 12


def fetch_history(interval, days, now_ms=None):
    """Fetch up to 1000 closed candles, paging backwards using Bybit start/end."""
    now_ms = now_ms or int(time.time() * 1000)
    duration = int(interval) * 60_000
    cursor = now_ms
    cutoff = now_ms - days * 86_400_000
    rows = {}
    while cursor > cutoff:
        params = urllib.parse.urlencode({
            "category": CATEGORY, "symbol": SYMBOL, "interval": interval,
            "limit": 1000, "end": cursor - 1,
        })
        req = urllib.request.Request(
            f"{BASE}/v5/market/kline?{params}",
            headers={"User-Agent": "bybit-long-backtest/1.0"},
        )
        with urllib.request.urlopen(req, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("retCode") != 0:
            raise RuntimeError(f"Bybit retCode={payload.get('retCode')}: {payload.get('retMsg')}")
        batch = payload.get("result", {}).get("list", [])
        if not batch:
            break
        oldest = min(int(row[0]) for row in batch)
        for raw in batch:
            start = int(raw[0])
            if start + duration <= now_ms and start >= cutoff:
                rows[start] = {
                    "time": start, "close_time": start + duration - 1,
                    "open": float(raw[1]), "high": float(raw[2]),
                    "low": float(raw[3]), "close": float(raw[4]),
                    "volume": float(raw[5]), "turnover": float(raw[6]),
                }
        if oldest >= cursor or len(batch) < 2:
            break
        cursor = oldest
        time.sleep(0.08)
    return sorted(rows.values(), key=lambda row: row["time"])


def atr(candles, period=ATR_PERIOD):
    if len(candles) < period + 1:
        return None
    trs = []
    for prev, cur in zip(candles[:-1], candles[1:]):
        trs.append(max(cur["high"] - cur["low"],
                       abs(cur["high"] - prev["close"]),
                       abs(cur["low"] - prev["close"])))
    value = sum(trs[:period]) / period
    for tr in trs[period:]:
        value = (value * (period - 1) + tr) / period
    return value


def summarize(trades, days, candle_counts):
    wins = [t for t in trades if t["net_pnl_usdc"] > 0]
    losses = [t for t in trades if t["net_pnl_usdc"] <= 0]
    gross = sum(t["gross_pnl_usdc"] for t in trades)
    net = sum(t["net_pnl_usdc"] for t in trades)
    fees = sum(t["fees_usdc"] for t in trades)
    funding = sum(t["funding_usdc"] for t in trades)
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for trade in trades:
        equity += trade["net_pnl_usdc"]
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "period_days_requested": days,
        "candles": candle_counts,
        "trades": len(trades), "wins": len(wins), "losses": len(losses),
        "win_rate_pct": round(100 * len(wins) / len(trades), 2) if trades else 0.0,
        "gross_pnl_usdc": round(gross, 6),
        "fees_usdc": round(fees, 6),
        "funding_usdc": round(funding, 6),
        "net_pnl_usdc": round(net, 6),
        "return_on_initial_margin_pct": round(100 * net / MARGIN_USDC, 4),
        "profit_factor": round(sum(t["net_pnl_usdc"] for t in wins) /
                               abs(sum(t["net_pnl_usdc"] for t in losses)), 4)
                          if losses and sum(t["net_pnl_usdc"] for t in losses) else None,
        "max_drawdown_usdc": round(max_dd, 6),
        "assumptions": {
            "margin_usdc": MARGIN_USDC, "leverage": LEVERAGE,
            "notional_usdc": NOTIONAL, "taker_fee_per_side": FEE_RATE,
            "slippage_per_side": SLIPPAGE_RATE,
            "hourly_funding_paid_by_long": FUNDING_RATE_HOURLY,
            "stop": f"{STOP_ATR}x ATR({ATR_PERIOD})",
            "target": f"{TARGET_R}R", "max_hold_hours": MAX_HOLD_HOURS,
            "ambiguous_stop_and_target_same_bar": "stop first",
        },
        "warning": "Historical simulation, not a guarantee. Funding is a fixed stress assumption; actual historical funding and execution differ.",
    }


def run_backtest(days=30):
    candles = {
        "1h": fetch_history("60", days),
        "15m": fetch_history("15", days),
        "5m": fetch_history("5", days),
    }
    for tf, rows in candles.items():
        if len(rows) < 80:
            raise RuntimeError(f"Insufficient {tf} history ({len(rows)} candles); refusing to report a result")
    close_times = {tf: [r["close_time"] for r in rows] for tf, rows in candles.items()}
    trades = []
    next_free_ms = 0
    # A decision is made only after a closed 1h candle; entry is the next 5m open.
    import bisect
    for i in range(60, len(candles["1h"]) - 1):
        h1 = candles["1h"][:i + 1]
        signal_time = h1[-1]["close_time"]
        if signal_time < next_free_ms:
            continue
        j15 = bisect.bisect_right(close_times["15m"], signal_time)
        j5 = bisect.bisect_right(close_times["5m"], signal_time)
        if j15 < 60 or j5 < 60 or j5 >= len(candles["5m"]):
            continue
        snapshots = {
            "1h": monitor.analyze(h1),
            "15m": monitor.analyze(candles["15m"][:j15]),
            "5m": monitor.analyze(candles["5m"][:j5]),
        }
        decision = monitor.classify_long(snapshots)
        if decision["signal"] != "LONG_CANDIDATE":
            continue
        entry_bar = candles["5m"][j5]
        entry_raw = entry_bar["open"]
        entry = entry_raw * (1 + SLIPPAGE_RATE)
        current_atr = atr(h1)
        if not current_atr or current_atr <= 0:
            continue
        stop = entry - STOP_ATR * current_atr
        risk = entry - stop
        target = entry + TARGET_R * risk
        exit_price = None
        exit_time = None
        exit_reason = "TIME"
        max_exit_index = min(len(candles["5m"]) - 1,
                             j5 + MAX_HOLD_HOURS * 12)
        for k in range(j5, max_exit_index + 1):
            bar = candles["5m"][k]
            hit_stop = bar["low"] <= stop
            hit_target = bar["high"] >= target
            if hit_stop:
                exit_price, exit_time, exit_reason = stop, bar["close_time"], "STOP"
                break
            if hit_target:
                exit_price, exit_time, exit_reason = target, bar["close_time"], "TARGET"
                break
        if exit_price is None:
            bar = candles["5m"][max_exit_index]
            exit_price, exit_time = bar["close"], bar["close_time"]
        exit_fill = exit_price * (1 - SLIPPAGE_RATE)
        gross = NOTIONAL * (exit_fill / entry - 1)
        fees = NOTIONAL * FEE_RATE + NOTIONAL * (exit_fill / entry) * FEE_RATE
        held_hours = max(0.0, (exit_time - entry_bar["time"]) / 3_600_000)
        funding = NOTIONAL * FUNDING_RATE_HOURLY * held_hours
        net = gross - fees - funding
        trades.append({
            "signal_time_utc": datetime.fromtimestamp(signal_time / 1000, timezone.utc).isoformat(),
            "entry_time_utc": datetime.fromtimestamp(entry_bar["time"] / 1000, timezone.utc).isoformat(),
            "exit_time_utc": datetime.fromtimestamp(exit_time / 1000, timezone.utc).isoformat(),
            "scenario": decision["scenario"], "entry": round(entry, 4),
            "stop": round(stop, 4), "target": round(target, 4),
            "exit": round(exit_fill, 4), "exit_reason": exit_reason,
            "held_hours": round(held_hours, 3),
            "gross_pnl_usdc": round(gross, 6), "fees_usdc": round(fees, 6),
            "funding_usdc": round(funding, 6), "net_pnl_usdc": round(net, 6),
        })
        next_free_ms = exit_time
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "exchange": "Bybit", "category": CATEGORY, "symbol": SYMBOL,
        "strategy": "Existing monitor.classify_long; LONG only",
        "results": summarize(trades, days, {tf: len(rows) for tf, rows in candles.items()}),
        "trades_detail": trades,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--output", default="data/backtest_latest.json")
    args = parser.parse_args()
    if args.days < 7 or args.days > 365:
        parser.error("--days must be between 7 and 365")
    report = run_backtest(args.days)
    import os
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
    print(json.dumps(report["results"], ensure_ascii=False, indent=2))
