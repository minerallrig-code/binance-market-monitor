"""Read-only oil-market headline collection from Google News RSS.

Publisher names and original links are retained. This module tags topics only;
it deliberately does not infer bullish/bearish impact from headlines.
"""
from __future__ import annotations

import hashlib
import re
import time
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


QUERIES = {
    "geopolitics_shipping": '"WTI" OR "crude oil" Iran OR "Strait of Hormuz" tanker',
    "opec_supply": '"OPEC+" OR OPEC oil production OR Saudi crude exports',
    "us_inventories": 'EIA crude inventories OR US oil stocks OR API crude stockpiles',
    "demand_macro": 'oil demand forecast OR China crude imports OR dollar oil prices',
}

TOPIC_RULES = {
    "geopolitics": ("iran", "israel", "united states", "u.s.", "war", "missile", "attack", "sanction", "diplomacy", "ceasefire"),
    "shipping": ("hormuz", "tanker", "shipping", "vessel", "freight", "insurance", "red sea", "strait"),
    "opec": ("opec", "opec+", "quota", "production target"),
    "inventories": ("inventory", "inventories", "stockpile", "crude stocks", "eia", "api report"),
    "production": ("production", "output", "exports", "export", "supply", "pipeline", "refinery"),
    "demand": ("demand", "consumption", "imports", "refining margins"),
    "macro": ("dollar", "federal reserve", "interest rate", "inflation", "recession", "china"),
}

TRUSTED_PUBLISHERS = (
    "reuters", "associated press", "ap news", "bloomberg", "financial times",
    "wall street journal", "cnbc", "bbc", "al jazeera", "eia", "opec",
    "u.s. energy information administration", "argus", "s&p global",
)


def _topics(text: str) -> list[str]:
    normalized = text.casefold()
    return [
        topic for topic, words in TOPIC_RULES.items()
        if any(word in normalized for word in words)
    ]


def _parse_time(value: str) -> str | None:
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _fetch_feed(query: str, timeout: int = 15) -> list[dict[str, Any]]:
    params = urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    url = f"https://news.google.com/rss/search?{params}"
    request = Request(url, headers={"User-Agent": "WTI-Oil-Navigator/0.1"})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
    root = ET.fromstring(raw)
    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        published = _parse_time(item.findtext("pubDate") or "")
        source_node = item.find("{*}source")
        publisher = (source_node.text or "").strip() if source_node is not None else ""
        description = re.sub(r"<[^>]+>", " ", item.findtext("description") or "")
        if not title or not link:
            continue
        full_text = f"{title} {description} {publisher}"
        publisher_lower = publisher.casefold()
        items.append({
            "id": hashlib.sha256((title.casefold() + link).encode("utf-8")).hexdigest()[:16],
            "title": title,
            "publisher": publisher,
            "publisher_trusted_list_match": any(name in publisher_lower for name in TRUSTED_PUBLISHERS),
            "url": link,
            "published_at": published,
            "topics": _topics(full_text),
            "query_group": None,
        })
    return items


def collect_news() -> dict[str, Any]:
    now = int(time.time())
    collected: dict[str, dict[str, Any]] = {}
    errors = []
    query_counts = {}
    for group, query in QUERIES.items():
        try:
            entries = _fetch_feed(query)
            query_counts[group] = len(entries)
            for entry in entries:
                entry["query_group"] = group
                collected.setdefault(entry["id"], entry)
        except Exception as exc:  # feed outages must not break the market-data capture
            query_counts[group] = 0
            errors.append({"query_group": group, "error": str(exc)[:300]})

    items = list(collected.values())
    items.sort(key=lambda item: item.get("published_at") or "", reverse=True)
    return {
        "status": "OK" if items and not errors else ("PARTIAL" if items else "FAILED"),
        "fetched_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "unique_headlines": len(items),
        "query_counts": query_counts,
        "errors": errors,
        "items": items[:300],
        "interpretation": "Topic tags only. No automatic bullish/bearish interpretation; verify the original report and its timestamp.",
    }
