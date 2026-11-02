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

The read-only pipeline has passed live GitHub Actions validation on 2026-11-02:
- Active Lighter WTI perpetual discovered dynamically as `WTI-USDC`, `market_id=145`.
- Live contract metadata returned minimum base amount `0.060`, minimum quote amount `10 USDC`, size/price precision 3/3 and multiplier 1.0. API fee fields currently returned `0.0000`; these values must be checked every run and are not treated as a guarantee of zero execution cost.
- Market snapshots collect 1D/4H/1H/15M/5M candles, funding history, top-of-book spread, recent trades and technical indicators.
- Historical research fetches 3,000 15m, 1,000 1h and 500 4h candles (roughly 31, 42 and 83 days respectively), then compares three fixed entry models using a chronological 70% in-sample / 30% holdout split.
- The latest completed replay showed very small sample counts: pullback recovery 1 in-sample / 0 holdout trades; EMA20 momentum cross 6 / 1; MACD zero cross 27 / 2. EMA20's holdout trade lost 0.53%; MACD zero-cross holdout had two trades and +0.21%. These are far too few observations to establish an edge. No strategy is approved for live signals.
- Replay assumptions: 1.5 ATR stop, 2R target, next 15m open entry, stop-first if stop and target touch in the same candle, 0.05% assumed fee per side and 2 bps assumed slippage per side. Funding is not yet included. Equity return compounds sequentially at 100% unlevered notional and is not a position-sizing forecast.
- News ingestion collected 206 recent headlines in the latest run. Event study clustered overlapping topic windows and compared post-headline returns with non-overlapping same-period price windows. Results remain descriptive only; news timing, anticipation, broad market trend and overlapping macro events prevent causal or predictive conclusions.
- Latest validated run: https://github.com/minerallrig-code/binance-market-monitor/actions/runs/41423901510
- Hourly schedule activates only after the draft PR is merged into the repository's default branch. No wallet credentials, signing, order placement or live trading are included.

## Implemented modules
- `market_data.py`: public Lighter API client, dynamic WTI discovery, contract details, candles, funding, order-book spread and recent trades
- `indicators.py`: RSI(6/14/24), EMA(20/50), MACD, ATR, volume and multi-timeframe bias
- `news_ingest.py`: Google News RSS searches, publisher attribution, deduplication and topic tags
- `event_study.py`: post-headline 1h/4h/24h price response, clustered by topic/time window and compared with same-period baseline
- `backtest.py`: no-lookahead replay with ATR stops, 2R target, conservative same-candle stop handling and configurable costs
- `run_market_check.py`: live market-data validation and JSON snapshot
- `run_backtest.py`: paginated history retrieval, model comparison and 70/30 chronological holdout
- `test_*.py`: unit tests for market discovery, indicators, news, event study and backtest
- `.github/workflows/wti-market-check.yml`: pull-request, manual and hourly read-only checks

## Next gates before any signal is enabled
1. Extend the historical sample and obtain a materially larger number of independent trades.
2. Validate funding sign, settlement interval and funding costs from actual Lighter records.
3. Improve news event clustering and verify source publication timestamps against original articles.
4. Run walk-forward tests across distinct volatility/regime periods, including realistic fees, spread, slippage and funding.
5. Define user-approved WTI position sizing and maximum loss per trade. Crypto leverage settings are not reused.
6. Only after those gates, consider producing manual-confirmation LONG/SHORT signals. Automatic execution remains out of scope.
