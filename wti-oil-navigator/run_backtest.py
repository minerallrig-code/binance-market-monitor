"""Fetch paginated closed WTI candles and compare fixed entry models.

Chronological split is used: first 70% is in-sample, final 30% is holdout.
No strategy parameters are optimized against the holdout.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from market_data import LighterAPIError, LighterPublicAPI
from backtest import run_backtest
from news_ingest import collect_news
from event_study import analyze_news_response

SECONDS = {"15m": 900, "1h": 3600, "4h": 14400}
DEFAULT_BARS = {"15m": 3000, "1h": 1000, "4h": 500}
ENTRY_MODES = ("pullback_recovery", "ema20_momentum_cross", "macd_zero_cross")


def fetch_history(api: LighterPublicAPI, market_id: int, resolution: str, now: int, target_bars: int):
    seconds = SECONDS[resolution]
    collected = {}
    cursor_end = now
    previous_oldest = None
    pages = 0
    while len(collected) < target_bars and pages < 20:
        start = cursor_end - 500 * seconds
        rows = api.candles(market_id, resolution, start, cursor_end, 500)
        if not rows:
            break
        page = sorted(rows, key=lambda row: int(row["t"]))
        for row in page:
            if int(row["t"]) + seconds * 1000 <= now * 1000:
                collected[int(row["t"])] = row
        oldest = int(page[0]["t"])
        if previous_oldest is not None and oldest >= previous_oldest:
            break
        previous_oldest = oldest
        cursor_end = oldest // 1000 - 1
        pages += 1
        if len(page) < 2:
            break
    result = sorted(collected.values(), key=lambda row: int(row["t"]))
    if len(result) < 70:
        raise LighterAPIError(f"Only {len(result)} historical {resolution} candles collected")
    return result[-target_bars:]


def _run_model(base, hourly, four_hour, mode, fee, slippage):
    split = int(len(base) * 0.7)
    if split < 70 or len(base) - split < 70:
        raise ValueError("Not enough 15m history for a 70/30 in-sample/holdout split")
    common = {
        "stop_atr": 1.5,
        "reward_risk": 2.0,
        "fee_rate_per_side": fee,
        "slippage_bps_per_side": slippage,
        "max_holding_bars": 48,
        "entry_mode": mode,
    }
    in_sample = run_backtest(base[:split], hourly, four_hour, **common)
    holdout = run_backtest(base[split:], hourly, four_hour, **common)
    full = run_backtest(base, hourly, four_hour, **common)
    return {
        "entry_mode": mode,
        "in_sample": {"trade_count": in_sample["trade_count"], "metrics": in_sample["metrics"]},
        "holdout": {"trade_count": holdout["trade_count"], "metrics": holdout["metrics"]},
        "full_sample": {"trade_count": full["trade_count"], "metrics": full["metrics"]},
        "assumptions": full["assumptions"],
        "holdout_trades": holdout["trades"],
    }


def main() -> int:
    api = LighterPublicAPI()
    symbol = os.getenv("LIGHTER_SYMBOL", "WTI")
    spec = api.market_spec(symbol)
    if spec.status.lower() != "active":
        raise LighterAPIError(f"{symbol} perpetual is not active")
    now = int(time.time())
    candles = {
        tf: fetch_history(
            api, spec.market_id, tf, now,
            int(os.getenv(f"BACKTEST_BARS_{tf.upper()}", str(DEFAULT_BARS[tf]))),
        )
        for tf in SECONDS
    }
    fee = float(os.getenv("BACKTEST_FEE_RATE_PER_SIDE", "0.0005"))
    slippage = float(os.getenv("BACKTEST_SLIPPAGE_BPS_PER_SIDE", "2.0"))
    results = [
        _run_model(candles["15m"], candles["1h"], candles["4h"], mode, fee, slippage)
        for mode in ENTRY_MODES
    ]
    news = collect_news()
    event_study = analyze_news_response(news, candles["15m"])
    output_data = {
        "status": "RESEARCH_ONLY",
        "instrument": {
            "symbol": spec.symbol,
            "market_id": spec.market_id,
            "multiplier": spec.multiplier,
            "min_base_amount": spec.min_base_amount,
            "min_quote_amount": spec.min_quote_amount,
            "maker_fee_metadata": spec.maker_fee,
            "taker_fee_metadata": spec.taker_fee,
        },
        "data_window": {
            tf: {
                "count": len(rows),
                "start_ms": int(rows[0]["t"]),
                "end_ms": int(rows[-1]["t"]),
            }
            for tf, rows in candles.items()
        },
        "split": "chronological 70% in-sample / 30% holdout",
        "models": results,
        "news_status": news["status"],
        "news_headlines_collected": news["unique_headlines"],
        "news_event_study": event_study,
        "fetched_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "warning": "Historical replay is not proof of future profitability. Funding is not included yet. Holdout is not to be used for parameter tuning.",
    }
    output = Path(os.getenv("WTI_BACKTEST_OUTPUT_PATH", "backtest-results/latest_backtest.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(output_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": output_data["status"],
        "symbol": spec.symbol,
        "market_id": spec.market_id,
        "data_window": output_data["data_window"],
        "news_status": output_data["news_status"],
        "news_headlines_collected": output_data["news_headlines_collected"],
        "news_events_matched": event_study["events_matched"],
        "models": [
            {
                "entry_mode": model["entry_mode"],
                "in_sample_trades": model["in_sample"]["trade_count"],
                "in_sample_metrics": model["in_sample"]["metrics"],
                "holdout_trades": model["holdout"]["trade_count"],
                "holdout_metrics": model["holdout"]["metrics"],
            }
            for model in results
        ],
        "output": str(output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LighterAPIError, ValueError, KeyError, TypeError) as exc:
        print(f"BACKTEST_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(2)
