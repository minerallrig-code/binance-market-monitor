# WTI Oil Navigator

A separate, read-only signal engine for the WTI perpetual contract shown in Walt.

## Walt instrument facts observed from the user's screenshots
- Display name: WTI Crude Oil (WTI) versus USD.
- Instrument is described in Walt as a perpetual futures contract.
- Walt advertises leverage up to 20x; this is a platform maximum, not the bot's recommended leverage.
- One screenshot showed funding at -0.008%; the funding interval and exact payment timestamp remain unverified.
- A later screenshot showed 24h volume of $6.43m and open interest of $8.02m. These are time-sensitive snapshots, not constants.
- Walt UI exposes 5m, 15m, 1h, and 4h chart intervals in the supplied screenshot.
- LONG and SHORT actions are available in the UI.

## Operating mode
- Signal-only: never places, edits, or closes orders.
- Walt remains the manual execution venue; every order requires the user's confirmation.
- Scheduled checks must not exceed once per hour unless the user explicitly changes this limit.
- No wallet/API keys, deposits, withdrawals, or access to the user's funds.

## Decision pipeline
1. Verify the exact Walt instrument identifier, contract multiplier, quote currency, tick size, minimum order size, funding interval, and settlement rules.
2. Identify a market-data feed that tracks the Walt contract closely; do not assume a generic WTI benchmark is identical.
3. Collect WTI market data and normalize timestamps.
4. Collect timestamped news from multiple independent sources.
5. Classify each event by topic (Iran/US, Strait of Hormuz, OPEC+, Saudi Arabia, US inventories, sanctions, shipping, USD/macro).
6. Score source reliability, event novelty, direction, and expected impact. Deduplicate syndicated copies.
7. Analyze closed candles on 1D/4H/1H/15M/5M; never use an unfinished candle for confirmation.
8. Produce LONG / SHORT / WAIT only when market structure and the news impulse agree. Otherwise WAIT.
9. Publish entry zone, invalidation/stop, targets, risk/reward, confidence, timestamp, source links, and reasons.
10. Log every signal and subsequent outcome for walk-forward evaluation.

## Funding interpretation
A negative perpetual funding rate commonly means shorts pay longs, but the exact convention, interval, and payment schedule must be confirmed from Walt's contract details. Funding is positioning/carry context, not a standalone directional signal.

## Safety and validation
- No automatic execution.
- No signal if price data is stale, sources conflict materially, or the contract mapping is unverified.
- News is context, not an automatic trading trigger. A headline alone cannot open a position.
- Stop-loss distance and position sizing must be calculated from the actual contract specification and user-approved risk limits.
- Backtest with realistic spread, slippage, fees, funding, and contract trading hours before live use.
- Do not use Walt's maximum 20x leverage as a default. Establish risk-based sizing after contract multiplier and stop distance are known.
- Do not reuse crypto-bot leverage, margin, or indicator thresholds for WTI without testing.

## Current implementation status
Project scaffold and Walt instrument facts have been recorded. The exact contract identifier, multiplier, tick/minimum size, funding interval, and a reliable matching market-data feed are still unverified. News provider/source selection and Telegram delivery are also pending. No live trading or signal automation is active.

## Planned modules
- market_data/: contract adapter and candle validation
- news/: RSS/API ingestion, deduplication, event classification
- analysis/: technical indicators and event/price alignment
- signals/: confluence rules, risk model, stale-data guards
- storage/: SQLite signal and outcome journal
- delivery/: Telegram notifications
- tests/: unit tests and historical replay
