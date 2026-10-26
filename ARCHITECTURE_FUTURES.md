# Futures Bot Architecture (Phase 1: Paper Trading)

## Project status
This branch extends the existing read-only Binance market monitor. It does not enable live order placement.

## Trading specification
- Venue: Binance USDⓈ-M Futures.
- Direction: LONG-only, preserving the existing strategy constraint.
- Leverage target: 3x, isolated margin.
- Trend timeframe: 4h; entry timeframe: 15m.
- Evaluation cadence: every 15 minutes, using closed candles only.
- Initial reference equity: 100 USDT.
- Maximum planned loss per trade: 1% of current account equity, including estimated fees and slippage in sizing.
- Initial watchlist inherited from the monitor: BTCUSDT, SOLUSDT, ZECUSDT, HYPEUSDT, WLDUSDT. Each symbol must be checked against Futures exchange metadata before use.

## Phased implementation
1. Futures market-data adapter using public USD-M Futures endpoints; validate symbols, filters, timestamps, and closed candles.
2. Strategy engine: 4h trend gate plus 15m entry trigger. No signal if data is stale, incomplete, contradictory, or unavailable.
3. Risk engine: size from stop distance and account equity; cap notional exposure at the configured leverage ceiling; enforce isolated margin and one position at a time initially.
4. Paper execution: simulate fills, fees, slippage, stop-loss, take-profit, and position lifecycle. Persist a trade journal and equity curve.
5. Backtest and walk-forward validation with out-of-sample periods. Report net PnL, drawdown, profit factor, expectancy, win rate, trade count, and fee sensitivity.
6. Binance Futures Testnet integration. Verify order sizing, exchange precision, position mode, leverage, margin type, protective stop placement, reconciliation, and idempotency.
7. Live execution remains disabled until paper/testnet acceptance criteria and an explicit live-enable step are completed.

## Hard safety requirements
- Never store API keys or secrets in source control, logs, artifacts, or snapshots.
- Testnet and live credentials must be separate. Live API key must have Futures trading permission only, withdrawals disabled, and IP restrictions enabled where available.
- Fail closed: no new order if market data, account state, open orders, position state, exchange filters, or protective-order state cannot be verified.
- Every entry must have a verified protective stop. If stop placement fails after entry, immediately attempt a reduce-only emergency close and halt trading.
- Use deterministic client order IDs and reconcile exchange state before retrying any timed-out order.
- Enforce daily loss and drawdown circuit breakers, maximum position/notional limits, and a global kill switch.
- Never average down or increase risk after a loss.
- No live order endpoint may be called by the paper-trading workflow.

## Provisional controls requiring validation
- Maximum concurrent positions: 1.
- Maximum daily realized loss: 3% of start-of-day equity.
- Maximum notional exposure: 3x account equity.
- These are conservative starting controls for simulation, not claims of optimal risk.

## Deployment boundary
GitHub Actions may continue collecting public market data every 15 minutes. It must not hold live trading credentials or execute live trades. A persistent execution service with durable state and reliable exchange reconciliation is required before live automation; scheduled CI runs alone are not an adequate live trading runtime.
