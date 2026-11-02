"""Fetch up to 500 closed candles per timeframe and run research-only replay."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from market_data import LighterAPIError, LighterPublicAPI
from backtest import run_backtest

SECONDS = {"15m": 900, "1h": 3600, "4h": 14400}


def fetch_closed(api: LighterPublicAPI, market_id: int, resolution: str, now: int):
    seconds = SECONDS[resolution]
    rows = api.candles(market_id, resolution, now - 500 * seconds, now, 500)
    closed = sorted(
        [row for row in rows if int(row["t"]) + seconds * 1000 <= now * 1000],
        key=lambda row: int(row["t"]),
    )
    if len(closed) < 70:
        raise LighterAPIError(f"Only {len(closed)} closed {resolution} candles; need at least 70")
    return closed


def main() -> int:
    api = LighterPublicAPI()
    symbol = os.getenv("LIGHTER_SYMBOL", "WTI")
    spec = api.market_spec(symbol)
    if spec.status.lower() != "active":
        raise LighterAPIError(f"{symbol} perpetual is not active")
    now = int(time.time())
    candles = {
        tf: fetch_closed(api, spec.market_id, tf, now)
        for tf in SECONDS
    }
    result = run_backtest(
        candles["15m"], candles["1h"], candles["4h"],
        stop_atr=float(os.getenv("BACKTEST_STOP_ATR", "1.5")),
        reward_risk=float(os.getenv("BACKTEST_REWARD_RISK", "2.0")),
        fee_rate_per_side=float(os.getenv("BACKTEST_FEE_RATE_PER_SIDE", "0.0005")),
        slippage_bps_per_side=float(os.getenv("BACKTEST_SLIPPAGE_BPS_PER_SIDE", "2.0")),
        max_holding_bars=int(os.getenv("BACKTEST_MAX_HOLDING_BARS", "48")),
    )
    result["instrument"] = {
        "symbol": spec.symbol,
        "market_id": spec.market_id,
        "multiplier": spec.multiplier,
        "min_base_amount": spec.min_base_amount,
        "min_quote_amount": spec.min_quote_amount,
        "maker_fee_metadata": spec.maker_fee,
        "taker_fee_metadata": spec.taker_fee,
    }
    result["data_window"] = {
        tf: {
            "count": len(rows),
            "start_ms": int(rows[0]["t"]),
            "end_ms": int(rows[-1]["t"]),
        }
        for tf, rows in candles.items()
    }
    result["fetched_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    output = Path(os.getenv("WTI_BACKTEST_OUTPUT_PATH", "backtest-results/latest_backtest.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "symbol": spec.symbol,
        "market_id": spec.market_id,
        "trade_count": result["trade_count"],
        "metrics": result["metrics"],
        "data_window": result["data_window"],
        "assumptions": result["assumptions"],
        "output": str(output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LighterAPIError, ValueError, KeyError, TypeError) as exc:
        print(f"BACKTEST_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(2)
