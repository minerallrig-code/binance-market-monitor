# WTI Oil Navigator

A separate, read-only signal engine for the WTI perpetual contract shown in Walt.

## Verified instrument mapping
- Walt's official help centre says perpetual-futures chart data is supplied by Lighter; the chart shows executed trades, while the headline price is the mark price.
- Lighter market identity independently listed by DeFiLlama: `WTI-USDC` (Lighter market slug `lighter:wti`), commodity perpetual, base asset Crude Oil (WTI), quote/margin/settlement asset USDC.
- Oracle provider listed by DeFiLlama: Pyth Lazer.
- Maximum leverage listed: 20x. This is an exchange maximum, not the bot's recommended leverage.
- Size decimals listed: 3. Exact minimum base/quote size, price decimals, market_id, contract multiplier and fee schedule must be read from Lighter's live market metadata before use.
- Walt screenshots showed 24h volume/open interest snapshots and a funding display of -0.008%. Those values are time-sensitive and must not be hardcoded. DeFiLlama snapshots have shown different funding values at other times, confirming funding must be fetched live.
- Walt says funding may be charged or credited hourly. The exact displayed sign convention and payment schedule must be checked against Lighter market funding data before interpreting a value.

## Data source and endpoints
- Public Lighter market-data API base: `https://mainnet.zklighter.elliot.ai/api/v1`
- Discover the WTI perpetual by querying `orderBooks` and matching `symbol=WTI`, `market_type=perp`, and active status; do not hardcode a market_id.
- Read live precision, fees, minimums, mark/index/last price and open interest from `orderBookDetails` for the discovered market_id.
- Read executed-trade OHLCV from `candles`; separately read mark-price candles from `markPriceCandles`.
- Read historical funding from `fundings` and current market statistics from `orderBookDetails` / WebSocket market stats.
- Confirm all endpoint schemas and timestamp units against the current official Lighter API docs before production use.

## Operating mode
- Signal-only: never places, edits, or closes orders.
- Walt remains the manual execution venue; every order requires the user's confirmation.
- Scheduled checks must not exceed once per hour unless the user explicitly changes this limit.
- No wallet/API keys, deposits, withdrawals, or access to the user's funds.

## Decision pipeline
1. Discover WTI market_id and validate that the market is active.
2. Verify contract multiplier, quote currency, tick size, minimum order size, fees, funding interval, and settlement rules from live metadata.
3. Collect Lighter trade candles, mark-price data, funding, order-book/liquidity data and normalize timestamps.
4. Collect timestamped news from multiple independent sources.
5. Classify each event by topic (Iran/US, Strait of Hormuz, OPEC+, Saudi Arabia, US inventories, sanctions, shipping, USD/macro).
6. Score source reliability, event novelty, direction, and expected impact. Deduplicate syndicated copies.
7. Analyze closed candles on 1D/4H/1H/15M/5M; never use an unfinished candle for confirmation.
8. Produce LONG / SHORT / WAIT only when market structure and the news impulse agree. Otherwise WAIT.
9. Publish entry zone, invalidation/stop, targets, risk/reward, confidence, timestamp, source links, and reasons.
10. Log every signal and subsequent outcome for walk-forward evaluation.

## Funding interpretation
A negative perpetual funding rate commonly means shorts pay longs, but do not infer payer direction from the sign alone. Confirm Lighter's `direction` / funding fields and Walt's displayed convention. Funding is positioning/carry context, not a standalone directional signal.

## Safety and validation
- No automatic execution.
- No signal if price data is stale, sources conflict materially, or the contract mapping is unverified.
- News is context, not an automatic trading trigger. A headline alone cannot open a position.
- Stop-loss distance and position sizing must be calculated from the actual contract specification and user-approved risk limits.
- Backtest with realistic spread, slippage, fees, funding, and contract trading hours before live use.
- Do not use Walt/Lighter's maximum 20x leverage as a default. Establish risk-based sizing after contract multiplier and stop distance are known.
- Do not reuse crypto-bot leverage, margin, or indicator thresholds for WTI without testing.

## Current implementation status
Instrument venue and symbol mapping are identified: Lighter `WTI-USDC` perpetual, market slug `lighter:wti`, Pyth Lazer oracle. Added a GET-only Python adapter, unit tests, and a multi-timeframe runner for 1D/4H/1H/15M/5M candles. A GitHub Actions workflow is configured for hourly checks and manual runs; scheduled GitHub workflows only execute after the workflow is present on the repository's default branch. The live API call could not be executed from this environment (DNS/network access unavailable), so the actual `market_id`, minimums, precision, multiplier and fee values remain unverified. No trading signals or orders are generated.

## Planned modules
- `market_data.py`: public API client, dynamic WTI discovery, market details and OHLC candles
- `test_market_data.py`: tests for market selection and fail-closed behavior
- `run_market_check.py`: validates live market data and closed candles across 1D/4H/1H/15M/5M; outputs a JSON snapshot
- `.github/workflows/wti-market-check.yml`: hourly and manual read-only data check (activate by merging this branch to the default branch)
- news/: RSS/API ingestion, deduplication, event classification
- analysis/: technical indicators and event/price alignment
- signals/: confluence rules, risk model, stale-data guards
- storage/: SQLite signal and outcome journal
- delivery/: Telegram notifications
- tests/: unit tests and historical replay
