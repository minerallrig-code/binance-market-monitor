"""Read-only public market-data adapter for Lighter WTI perpetuals.

No wallet credentials and no order-placement methods are included.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class LighterAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class MarketSpec:
    symbol: str
    market_id: int
    market_type: str
    status: str
    min_base_amount: str | None = None
    min_quote_amount: str | None = None
    maker_fee: str | None = None
    taker_fee: str | None = None
    size_decimals: int | None = None
    price_decimals: int | None = None
    multiplier: str | None = None
    mark_price: str | None = None
    index_price: str | None = None
    last_trade_price: str | None = None
    open_interest: str | None = None
    open_interest_usd: str | None = None
    daily_quote_token_volume: str | None = None


class LighterPublicAPI:
    """Small GET-only client. API schemas are validated defensively at runtime."""

    def __init__(self, base_url: str | None = None, timeout: int = 15):
        self.base_url = (base_url or os.getenv(
            "LIGHTER_API_BASE", "https://mainnet.zklighter.elliot.ai/api/v1"
        )).rstrip("/")
        self.timeout = timeout

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = f"?{urlencode(params)}" if params else ""
        request = Request(
            f"{self.base_url}/{endpoint.lstrip('/')}{query}",
            headers={"Accept": "application/json", "User-Agent": "WTI-Oil-Navigator/0.1"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LighterAPIError(f"Lighter {endpoint} request failed: {exc}") from exc

        if not isinstance(payload, dict):
            raise LighterAPIError(f"Unexpected {endpoint} response: expected JSON object")
        api_code = payload.get("code")
        if api_code is not None and api_code not in (200, "200"):
            raise LighterAPIError(f"Lighter {endpoint} returned API code {api_code}")
        return payload

    @staticmethod
    def _rows(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        # Some API versions may return a direct list under a generic data key.
        value = payload.get("data")
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        return []

    def discover_wti_perpetual(self, symbol: str = "WTI") -> dict[str, Any]:
        payload = self.get("orderBooks")
        rows = self._rows(payload, "order_books", "orderBooks", "order_book_details")
        matches = [
            row for row in rows
            if str(row.get("symbol", "")).upper() == symbol.upper()
            and str(row.get("market_type", "")).lower() == "perp"
            and str(row.get("status", "")).lower() == "active"
        ]
        if len(matches) != 1:
            raise LighterAPIError(
                f"Expected exactly one active {symbol} perpetual, found {len(matches)}. "
                "Refusing to guess a market_id."
            )
        market = matches[0]
        if market.get("market_id") is None:
            raise LighterAPIError("WTI market metadata has no market_id")
        return market

    def market_spec(self, symbol: str = "WTI") -> MarketSpec:
        discovered = self.discover_wti_perpetual(symbol)
        market_id = int(discovered["market_id"])
        detail_payload = self.get("orderBookDetails", {"market_id": market_id})
        details = self._rows(
            detail_payload, "order_book_details", "orderBookDetails", "perp_order_book_details"
        )
        detail = next(
            (row for row in details if int(row.get("market_id", -1)) == market_id),
            discovered,
        )

        def value(name: str) -> str | None:
            raw = detail.get(name, discovered.get(name))
            return None if raw is None else str(raw)

        def integer(name: str) -> int | None:
            raw = detail.get(name, discovered.get(name))
            return None if raw is None else int(raw)

        return MarketSpec(
            symbol=str(detail.get("symbol", symbol)),
            market_id=market_id,
            market_type=str(detail.get("market_type", "perp")),
            status=str(detail.get("status", "unknown")),
            min_base_amount=value("min_base_amount"),
            min_quote_amount=value("min_quote_amount"),
            maker_fee=value("maker_fee"),
            taker_fee=value("taker_fee"),
            size_decimals=integer("size_decimals") or integer("supported_size_decimals"),
            price_decimals=integer("price_decimals") or integer("supported_price_decimals"),
            multiplier=value("multiplier"),
            mark_price=value("mark_price"),
            index_price=value("index_price"),
            last_trade_price=value("last_trade_price"),
            open_interest=value("open_interest"),
            open_interest_usd=value("open_interest_usd"),
            daily_quote_token_volume=value("daily_quote_token_volume"),
        )

    def candles(
        self, market_id: int, resolution: str, start_timestamp: int,
        end_timestamp: int, count_back: int = 500
    ) -> list[dict[str, Any]]:
        if end_timestamp <= start_timestamp:
            raise ValueError("end_timestamp must be greater than start_timestamp")
        payload = self.get("candles", {
            "market_id": market_id,
            "resolution": resolution,
            "start_timestamp": start_timestamp,
            "end_timestamp": end_timestamp,
            "count_back": min(max(int(count_back), 1), 500),
        })
        rows = payload.get("c")
        if not isinstance(rows, list):
            raise LighterAPIError("Unexpected candles response: missing 'c' array")
        # Lighter candle 't' values are milliseconds; request timestamps are seconds.
        return [row for row in rows if isinstance(row, dict) and row.get("t") is not None]

    def funding_history(
        self, market_id: int, start_timestamp: int, end_timestamp: int
    ) -> list[dict[str, Any]]:
        payload = self.get("fundings", {
            "market_id": market_id,
            "start_timestamp": start_timestamp,
            "end_timestamp": end_timestamp,
        })
        rows = self._rows(payload, "fundings", "funding")
        # Funding timestamps have been observed in seconds, unlike candle timestamps.
        return rows


def main() -> None:
    api = LighterPublicAPI()
    symbol = os.getenv("LIGHTER_SYMBOL", "WTI")
    spec = api.market_spec(symbol)
    print(json.dumps(asdict(spec), indent=2, ensure_ascii=False))
    print(f"Discovered at Unix time: {int(time.time())}")
    if spec.status.lower() != "active":
        raise SystemExit("Market is not active; no analysis should proceed.")
    if not spec.mark_price and not spec.last_trade_price:
        raise SystemExit("No live price returned; data validation failed.")


if __name__ == "__main__":
    main()
