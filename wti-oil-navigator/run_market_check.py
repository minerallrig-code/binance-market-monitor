"""Fetch a read-only WTI market snapshot from Lighter and validate candle freshness."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from market_data import LighterAPIError, LighterPublicAPI
from indicators import analyze_all_timeframes
from news_ingest import collect_news

TIMEFRAMES = {
    "1d": 86400,
    "4h": 14400,
    "1h": 3600,
    "15m": 900,
    "5m": 300,
}


def main() -> int:
    api = LighterPublicAPI()
    symbol = os.getenv("LIGHTER_SYMBOL", "WTI")
    spec = api.market_spec(symbol)
    if spec.status.lower() != "active":
        raise LighterAPIError(f"{symbol} perpetual is not active: {spec.status}")
    if not (spec.mark_price or spec.last_trade_price):
        raise LighterAPIError("Market details did not contain a usable live price")

    now = int(time.time())
    now_ms = now * 1000
    market_data = {}
    for resolution, seconds in TIMEFRAMES.items():
        bars = 120
        end_ts = now
        start_ts = end_ts - bars * seconds
        rows = api.candles(spec.market_id, resolution, start_ts, end_ts, bars)
        if not rows:
            raise LighterAPIError(f"No candles returned for {resolution}")
        normalized = sorted(rows, key=lambda row: int(row["t"]))
        closed = [row for row in normalized if int(row["t"]) + seconds * 1000 <= now_ms]
        if len(closed) < 10:
            raise LighterAPIError(f"Insufficient closed candles for {resolution}: {len(closed)}")
        latest = closed[-1]
        age_seconds = (now_ms - (int(latest["t"]) + seconds * 1000)) // 1000
        if age_seconds > seconds * 2:
            raise LighterAPIError(f"Stale {resolution} candles: latest closed bar is {age_seconds}s old")
        market_data[resolution] = {
            "count_received": len(normalized),
            "count_closed": len(closed),
            "latest_closed_candle": latest,
            "latest_closed_age_seconds": age_seconds,
            "candles": closed,
        }

    funding = api.funding_history(spec.market_id, now - 48 * 3600, now)
    book = api.order_book_top(spec.market_id, limit=20)
    trades = api.recent_trades(spec.market_id, limit=50)
    technical = analyze_all_timeframes(market_data)
    news = collect_news()

    result = {
        "status": "DATA_OK_NO_SIGNAL",
        "fetched_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "source": "Lighter public REST API",
        "symbol": symbol,
        "market": spec.__dict__,
        "timeframes": market_data,
        "technical_analysis": technical,
        "news_context": news,
        "funding_history_48h": funding,
        "order_book_top": book,
        "recent_trades_count": len(trades),
        "recent_trades_sample": trades[:10],
        "execution_enabled": False,
        "note": "Market data validated. No trading signal has been generated and no orders can be placed.",
    }
    output = Path(os.getenv("WTI_OUTPUT_PATH", "wti-oil-navigator/latest_snapshot.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "symbol": symbol,
        "market_id": spec.market_id,
        "mark_price": spec.mark_price,
        "last_trade_price": spec.last_trade_price,
        "candles": {tf: item["count_closed"] for tf, item in market_data.items()},
        "spread_bps": book["spread_bps"],
        "funding_records_48h": len(funding),
        "recent_trades": len(trades),
        "technical_bias": technical["higher_timeframe_bias"],
        "signal": technical["signal"],
        "news_status": news["status"],
        "news_headlines": news["unique_headlines"],
        "snapshot": str(output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LighterAPIError, ValueError, KeyError, TypeError) as exc:
        print(f"DATA_CHECK_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(2)
