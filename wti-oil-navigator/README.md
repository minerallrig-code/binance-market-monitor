# WTI Oil Navigator

A separate, read-only signal engine for the WTI perpetual contract shown in Walt.

## Operating mode
- Signal-only: never places, edits, or closes orders.
- Walt remains the manual execution venue; every order requires the user's confirmation.
- Scheduled checks must not exceed once per hour unless the user explicitly changes this limit.
- No wallet/API keys, deposits, withdrawals, or access to the user's funds.

## Decision pipeline
1. Collect WTI market data and normalize timestamps.
2. Collect timestamped news from multiple independent sources.
3. Classify each event by topic (Iran/US, Strait of Hormuz, OPEC+, Saudi Arabia, US inventories, sanctions, shipping, USD/macro).
4. Score source reliability, event novelty, direction, and expected impact. Deduplicate syndicated copies.
5. Analyze closed candles on 1D/4H/1H/15M; never use an unfinished candle for confirmation.
6. Produce LONG / SHORT / WAIT only when market structure and the news impulse agree. Otherwise WAIT.
7. Publish entry zone, invalidation/stop, targets, risk/reward, confidence, timestamp, source links, and reasons.
8. Log every signal and subsequent outcome for walk-forward evaluation.

## Safety and validation
- No automatic execution.
- No signal if price data is stale, sources conflict materially, or the contract mapping is unverified.
- News is context, not an automatic trading trigger. A headline alone cannot open a position.
- Stop-loss distance and position sizing must be calculated from the actual contract specification and user-approved risk limits.
- Backtest with realistic spread, slippage, fees, funding, and contract trading hours before live use.
- Do not reuse crypto-bot leverage, margin, or indicator thresholds for WTI without testing.

## Current implementation status
Scaffold only. The exact Walt WTI instrument identifier and a reliable matching market-data feed must be verified before implementing signal calculations. News provider/source selection and Telegram delivery are also pending.

## Planned modules
- market_data/: contract adapter and candle validation
- news/: RSS/API ingestion, deduplication, event classification
- analysis/: technical indicators and event/price alignment
- signals/: confluence rules, risk model, stale-data guards
- storage/: SQLite signal and outcome journal
- delivery/: Telegram notifications
- tests/: unit tests and historical replay
