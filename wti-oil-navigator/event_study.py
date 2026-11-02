"""Descriptive post-headline WTI price-response study (not causal inference)."""
from __future__ import annotations

from datetime import datetime
from statistics import mean, median
from typing import Any


HORIZONS = {"1h": 4, "4h": 16, "24h": 96}


def _timestamp_ms(value: str | None) -> int | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError, OverflowError):
        return None


def analyze_news_response(news: dict[str, Any], candles_15m: list[dict[str, Any]]) -> dict[str, Any]:
    candles = sorted(candles_15m, key=lambda row: int(row["t"]))
    if len(candles) < 100:
        return {"status": "INSUFFICIENT_PRICE_HISTORY", "events_matched": 0, "by_topic": {}}
    times = [int(row["t"]) + 900_000 for row in candles]
    closes = [float(row["c"]) for row in candles]
    observations = []
    for item in news.get("items", []):
        published = _timestamp_ms(item.get("published_at"))
        if published is None:
            continue
        # Find the first candle close after the headline timestamp.
        index = next((i for i, close_time in enumerate(times) if close_time >= published), None)
        if index is None:
            continue
        event = {
            "id": item.get("id"),
            "title": item.get("title"),
            "publisher": item.get("publisher"),
            "published_at": item.get("published_at"),
            "topics": item.get("topics") or [],
            "trusted_publisher_match": item.get("publisher_trusted_list_match", False),
            "returns_pct": {},
        }
        for horizon, bars in HORIZONS.items():
            future_index = index + bars
            if future_index < len(closes) and closes[index] > 0:
                event["returns_pct"][horizon] = round((closes[future_index] / closes[index] - 1) * 100, 4)
        if event["returns_pct"]:
            observations.append(event)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in observations:
        for topic in set(event["topics"]):
            grouped.setdefault(topic, []).append(event)

    baseline = {}
    for horizon, bars in HORIZONS.items():
        values = [(closes[i + bars] / closes[i] - 1) * 100 for i in range(len(closes) - bars) if closes[i] > 0]
        if values:
            baseline[horizon] = {
                "n": len(values),
                "mean_return_pct": round(mean(values), 4),
                "median_return_pct": round(median(values), 4),
                "positive_return_pct": round(sum(value > 0 for value in values) / len(values) * 100, 2),
            }

    summary = {}
    for topic, events in grouped.items():
        horizons = {}
        for horizon in HORIZONS:
            values = [event["returns_pct"][horizon] for event in events if horizon in event["returns_pct"]]
            if values:
                horizons[horizon] = {
                    "n": len(values),
                    "mean_return_pct": round(mean(values), 4),
                    "median_return_pct": round(median(values), 4),
                    "positive_return_pct": round(sum(value > 0 for value in values) / len(values) * 100, 2),
                    "excess_mean_vs_period_baseline_pct": round(mean(values) - baseline[horizon]["mean_return_pct"], 4),
                    "positive_rate_difference_vs_baseline_pct_points": round(sum(value > 0 for value in values) / len(values) * 100 - baseline[horizon]["positive_return_pct"], 2),
                }
        summary[topic] = {
            "headline_count": len(events),
            "trusted_publisher_headline_count": sum(event["trusted_publisher_match"] for event in events),
            "forward_returns": horizons,
        }

    return {
        "status": "DESCRIPTIVE_ONLY",
        "events_matched": len(observations),
        "period_baseline": baseline,
        "topics": summary,
        "sample_events": observations[:50],
        "warning": "Observed price changes after headlines are not proof of causation or predictive edge. Headlines may be duplicated, delayed, anticipated by markets, or published after price moves.",
    }
