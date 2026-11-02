"""Conservative, no-lookahead WTI strategy replay on closed candles.

The simulator is deliberately signal research only. It does not size or place orders.
Costs are configurable assumptions because venue fees, spread and slippage vary.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from bisect import bisect_right
from math import isfinite
from statistics import mean
from typing import Any

from indicators import _atr, _ema, _rsi


@dataclass
class Trade:
    side: str
    signal_time_ms: int
    entry_time_ms: int
    exit_time_ms: int
    entry: float
    stop: float
    target: float
    exit: float
    exit_reason: str
    gross_return_pct: float
    net_return_pct: float
    funding_cost_pct: float
    funding_payments_count: int
    r_multiple: float
    bars_held: int


def _rsi_series(values: list[float], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return output
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(value, 0.0) for value in changes]
    losses = [max(-value, 0.0) for value in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def value(gain: float, loss: float) -> float:
        if loss == 0:
            return 100.0 if gain > 0 else 50.0
        rs = gain / loss
        return 100.0 - (100.0 / (1.0 + rs))

    output[period] = value(avg_gain, avg_loss)
    for i in range(period + 1, len(values)):
        gain, loss = gains[i - 1], losses[i - 1]
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        output[i] = value(avg_gain, avg_loss)
    return output


def _atr_series(candles: list[dict[str, Any]], period: int = 14) -> list[float | None]:
    output: list[float | None] = [None] * len(candles)
    if len(candles) <= period:
        return output
    true_ranges = []
    previous_close = float(candles[0]["c"])
    for candle in candles[1:]:
        high, low, close = float(candle["h"]), float(candle["l"]), float(candle["c"])
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
        previous_close = close
    current = sum(true_ranges[:period]) / period
    output[period] = current
    for i in range(period + 1, len(candles)):
        current = ((current * (period - 1)) + true_ranges[i - 1]) / period
        output[i] = current
    return output


def _series(candles: list[dict[str, Any]]) -> dict[str, list[float | None]]:
    rows = sorted(candles, key=lambda row: int(row["t"]))
    close = [float(row["c"]) for row in rows]
    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    # Start MACD only after both EMAs are valid; feeding leading NaNs into EMA
    # would poison the signal line for the entire series.
    macd_start = 25
    macd_line_valid = [ema12[i] - ema26[i] for i in range(macd_start, len(close))]
    macd_signal_valid = _ema(macd_line_valid, 9)
    hist = [None] * len(close)
    for offset, value in enumerate(macd_line_valid):
        signal_value = macd_signal_valid[offset]
        if isfinite(value) and isfinite(signal_value):
            hist[macd_start + offset] = value - signal_value
    rsi6 = _rsi_series(close, 6)
    rsi14 = _rsi_series(close, 14)
    atr = _atr_series(rows, 14)
    duration_ms = _resolution_ms(rows)
    close_times = [int(row["t"]) + duration_ms for row in rows]
    return {
        "close_times": close_times,
        "close": close,
        "ema20": [v if isfinite(v) else None for v in ema20],
        "ema50": [v if isfinite(v) else None for v in ema50],
        "hist": hist,
        "rsi6": rsi6,
        "rsi14": rsi14,
        "atr": atr,
    }


def _trend_at(candles: list[dict[str, Any]], series: dict[str, list[float | None]], time_ms: int) -> str | None:
    # Only use a higher-timeframe candle whose close timestamp is <= decision time.
    close_times = series["close_times"]
    i = bisect_right(close_times, time_ms) - 1
    if i < 0:
        return None
    close = series["close"][i]
    ema20, ema50 = series["ema20"][i], series["ema50"][i]
    if ema20 is None or ema50 is None:
        return None
    if close > ema20 > ema50:
        return "LONG"
    if close < ema20 < ema50:
        return "SHORT"
    return "NEUTRAL"


def _resolution_ms(candles: list[dict[str, Any]]) -> int:
    if len(candles) < 2:
        raise ValueError("At least two candles required to infer timeframe")
    diffs = [int(candles[i]["t"]) - int(candles[i - 1]["t"]) for i in range(1, min(len(candles), 30))]
    return int(sorted(diffs)[len(diffs) // 2])


def _signal_at(
    i: int,
    base: list[dict[str, Any]],
    base_s: dict[str, list[float | None]],
    h1: list[dict[str, Any]],
    h1_s: dict[str, list[float | None]],
    h4: list[dict[str, Any]],
    h4_s: dict[str, list[float | None]],
    entry_mode: str,
) -> str | None:
    candle = base[i]
    decision_time = int(candle["t"]) + _resolution_ms(base)
    trend1 = _trend_at(h1, h1_s, decision_time)
    trend4 = _trend_at(h4, h4_s, decision_time)
    if trend1 != trend4 or trend1 not in ("LONG", "SHORT"):
        return None

    rsi6, rsi14 = base_s["rsi6"][i], base_s["rsi14"][i]
    hist = base_s["hist"][i]
    prev_hist = base_s["hist"][i - 1] if i > 0 else None
    atr = base_s["atr"][i]
    ema20 = base_s["ema20"][i]
    if None in (rsi6, rsi14, hist, prev_hist, atr, ema20) or atr <= 0:
        return None

    previous_close = float(base[i - 1]["c"])
    previous_ema20 = base_s["ema20"][i - 1]
    if entry_mode == "pullback_recovery":
        if trend1 == "LONG":
            if base_s["rsi6"][i - 1] is not None and base_s["rsi6"][i - 1] <= 30 and rsi6 > 30:
                if rsi14 >= 45 and hist > prev_hist and float(candle["c"]) > ema20:
                    return "LONG"
        else:
            if base_s["rsi6"][i - 1] is not None and base_s["rsi6"][i - 1] >= 70 and rsi6 < 70:
                if rsi14 <= 55 and hist < prev_hist and float(candle["c"]) < ema20:
                    return "SHORT"
    elif entry_mode == "ema20_momentum_cross":
        if previous_ema20 is None:
            return None
        if trend1 == "LONG" and previous_close <= previous_ema20 and float(candle["c"]) > ema20:
            if rsi14 >= 50 and hist > 0 and hist > prev_hist:
                return "LONG"
        if trend1 == "SHORT" and previous_close >= previous_ema20 and float(candle["c"]) < ema20:
            if rsi14 <= 50 and hist < 0 and hist < prev_hist:
                return "SHORT"
    elif entry_mode == "macd_zero_cross":
        if trend1 == "LONG" and prev_hist <= 0 < hist and rsi14 >= 50 and float(candle["c"]) > ema20:
            return "LONG"
        if trend1 == "SHORT" and prev_hist >= 0 > hist and rsi14 <= 50 and float(candle["c"]) < ema20:
            return "SHORT"
    else:
        raise ValueError(f"Unsupported entry_mode: {entry_mode}")
    return None


def _funding_cost_fraction(
    side: str, entry_time_ms: int, exit_time_ms: int, records: list[dict[str, Any]]
) -> tuple[float, int]:
    total = 0.0
    count = 0
    for record in records:
        timestamp = int(record["timestamp"]) * 1000  # Lighter funding timestamps are seconds.
        if not (entry_time_ms <= timestamp <= exit_time_ms):
            continue
        direction = str(record.get("direction", "")).lower()
        if direction not in ("long", "short"):
            raise ValueError(f"Unknown Lighter funding direction: {direction!r}")
        rate_percent_per_hour = float(record["rate"])
        signed_rate_fraction = (rate_percent_per_hour / 100.0) * (1.0 if direction == "long" else -1.0)
        # Lighter direction=long means longs pay shorts; invert for short positions.
        total += signed_rate_fraction if side == "LONG" else -signed_rate_fraction
        count += 1
    return total, count


def run_backtest(
    candles_15m: list[dict[str, Any]],
    candles_1h: list[dict[str, Any]],
    candles_4h: list[dict[str, Any]],
    *,
    stop_atr: float = 1.5,
    reward_risk: float = 2.0,
    fee_rate_per_side: float = 0.0005,
    slippage_bps_per_side: float = 2.0,
    max_holding_bars: int = 48,
    entry_mode: str = "pullback_recovery",
    funding_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return trade list and metrics. Entry occurs at next bar open (no lookahead)."""
    if min(len(candles_15m), len(candles_1h), len(candles_4h)) < 70:
        raise ValueError("Need at least 70 candles on 15m, 1h and 4h")
    if stop_atr <= 0 or reward_risk <= 0 or fee_rate_per_side < 0 or slippage_bps_per_side < 0:
        raise ValueError("Invalid backtest parameters")

    funding_records = funding_records or []
    base = sorted(candles_15m, key=lambda row: int(row["t"]))
    h1 = sorted(candles_1h, key=lambda row: int(row["t"]))
    h4 = sorted(candles_4h, key=lambda row: int(row["t"]))
    base_s, h1_s, h4_s = _series(base), _series(h1), _series(h4)
    trades: list[Trade] = []
    i = 60
    last_exit_i = -1
    # Slippage is already applied to entry and exit prices; subtract fees only here.
    total_cost = 2 * fee_rate_per_side

    while i < len(base) - 1:
        if i <= last_exit_i:
            i += 1
            continue
        side = _signal_at(i, base, base_s, h1, h1_s, h4, h4_s, entry_mode)
        atr = base_s["atr"][i]
        if side is None or atr is None:
            i += 1
            continue

        entry_i = i + 1
        entry_bar = base[entry_i]
        raw_entry = float(entry_bar["o"])
        slip = slippage_bps_per_side / 10000
        entry = raw_entry * (1 + slip if side == "LONG" else 1 - slip)
        risk_distance = float(atr) * stop_atr
        stop = entry - risk_distance if side == "LONG" else entry + risk_distance
        target = entry + risk_distance * reward_risk if side == "LONG" else entry - risk_distance * reward_risk

        exit_i = None
        exit_price = None
        reason = None
        final_i = min(len(base) - 1, entry_i + max_holding_bars)
        for j in range(entry_i, final_i + 1):
            high, low = float(base[j]["h"]), float(base[j]["l"])
            # If both levels are touched within one candle, pessimistically assume stop first.
            if side == "LONG":
                if low <= stop:
                    exit_i, exit_price, reason = j, stop, "STOP"
                    break
                if high >= target:
                    exit_i, exit_price, reason = j, target, "TARGET"
                    break
            else:
                if high >= stop:
                    exit_i, exit_price, reason = j, stop, "STOP"
                    break
                if low <= target:
                    exit_i, exit_price, reason = j, target, "TARGET"
                    break
        if exit_i is None:
            exit_i = final_i
            exit_price = float(base[final_i]["c"])
            reason = "TIME_EXIT"

        exit_slipped = float(exit_price) * (1 - slip if side == "LONG" else 1 + slip)
        gross = ((exit_slipped - entry) / entry) if side == "LONG" else ((entry - exit_slipped) / entry)
        exit_time_ms = int(base[exit_i]["t"]) + _resolution_ms(base)
        funding_cost, funding_count = _funding_cost_fraction(
            side, int(entry_bar["t"]), exit_time_ms, funding_records
        )
        net = gross - total_cost - funding_cost
        r_multiple = net / (risk_distance / entry)
        trades.append(Trade(
            side=side,
            signal_time_ms=int(base[i]["t"]) + _resolution_ms(base),
            entry_time_ms=int(entry_bar["t"]),
            exit_time_ms=int(base[exit_i]["t"]) + _resolution_ms(base),
            entry=round(entry, 5),
            stop=round(stop, 5),
            target=round(target, 5),
            exit=round(exit_slipped, 5),
            exit_reason=str(reason),
            gross_return_pct=round(gross * 100, 4),
            net_return_pct=round(net * 100, 4),
            funding_cost_pct=round(funding_cost * 100, 6),
            funding_payments_count=funding_count,
            r_multiple=round(r_multiple, 4),
            bars_held=exit_i - entry_i + 1,
        ))
        last_exit_i = exit_i
        i = exit_i + 1

    if not trades:
        return {
            "trade_count": 0,
            "metrics": None,
            "trades": [],
            "status": "NO_TRADES",
            "assumptions": {
                "stop_atr": stop_atr,
                "reward_risk": reward_risk,
                "fee_rate_per_side": fee_rate_per_side,
                "slippage_bps_per_side": slippage_bps_per_side,
                "max_holding_bars": max_holding_bars,
                "entry_mode": entry_mode,
                "entry": "next 15m candle open after signal candle closes",
                "same_bar_stop_target": "stop first (conservative)",
                "equity_curve_assumption": "100% of unlevered notional per sequential trade; not a position-sizing forecast",
                "funding_cost": "historical Lighter hourly rate and direction applied to each position holding interval",
            },
        }

    returns = [trade.net_return_pct / 100 for trade in trades]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value <= 0]
    gross_profit = sum(value for value in returns if value > 0)
    gross_loss = abs(sum(value for value in returns if value < 0))
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in returns:
        equity *= (1 + value)
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak)

    metrics = {
        "win_rate_pct": round(len(wins) / len(trades) * 100, 2),
        "net_profit_pct_compounded": round((equity - 1) * 100, 2),
        "average_trade_pct": round(mean(returns) * 100, 4),
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else None,
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "average_r_multiple": round(mean(trade.r_multiple for trade in trades), 3),
        "long_trades": sum(trade.side == "LONG" for trade in trades),
        "short_trades": sum(trade.side == "SHORT" for trade in trades),
        "stop_exits": sum(trade.exit_reason == "STOP" for trade in trades),
        "target_exits": sum(trade.exit_reason == "TARGET" for trade in trades),
        "time_exits": sum(trade.exit_reason == "TIME_EXIT" for trade in trades),
        "funding_cost_pct_total": round(sum(trade.funding_cost_pct for trade in trades), 6),
        "funding_payments_count": sum(trade.funding_payments_count for trade in trades),
    }
    return {
        "trade_count": len(trades),
        "metrics": metrics,
        "trades": [asdict(trade) for trade in trades],
        "status": "RESEARCH_ONLY",
        "assumptions": {
            "stop_atr": stop_atr,
            "reward_risk": reward_risk,
            "fee_rate_per_side": fee_rate_per_side,
            "slippage_bps_per_side": slippage_bps_per_side,
            "max_holding_bars": max_holding_bars,
            "entry_mode": entry_mode,
            "entry": "next 15m candle open after signal candle closes",
            "same_bar_stop_target": "stop first (conservative)",
            "equity_curve_assumption": "100% of unlevered notional per sequential trade; not a position-sizing forecast",
            "funding_cost": "historical Lighter hourly rate and direction applied to each position holding interval; entry price is used as a constant notional approximation",
        },
    }
