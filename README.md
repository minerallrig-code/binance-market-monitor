# Bybit BTCUSDT LONG Monitor

Read-only analytics for **BTCUSDT USDT Linear Futures on Bybit**. The monitor uses public market data only. It does not connect to Walt, hold credentials, or place, cancel, or modify orders.

## Data contract
- Exchange: Bybit V5, category `linear`
- Instrument: `BTCUSDT`
- Timeframes: 1H, 15m, 5m
- Closed candles only; the active candle is discarded
- No silent OKX/Binance fallback. If any timeframe is unavailable, the decision is `WAIT`.

## Indicators
- EMA20 / EMA50
- RSI6, RSI12, RSI14, RSI24
- MACD(12,26,9), DIF/DEA/histogram and histogram direction
- Volume against the preceding closed candles' MA5 and MA10 (the current candle is excluded from the baseline)
- 50-candle swing high/low and Fibonacci retracements 50%, 61.8%, 78.6%

## LONG scenarios
A. **Trend continuation** — 1H EMA20 > EMA50; 15m close above EMA20 with positive MACD and RSI14 in the configured momentum band; volume filter; 5m early confirmation.

B. **Reversal after a sharp decline** — 1H drawdown from the recent 50-candle high, seller-volume spike, improving 1H MACD histogram, and confirming 5m/15m conditions. Oversold RSI or a green candle alone never qualifies.

The classifier returns `LONG_CANDIDATE` or `WAIT`. This is a screening result, not an order instruction. A candidate must still pass the separate Walt checks: available USDC collateral, no existing position, 2x leverage, margin no greater than 5 USDC, entry/SL/TP calculation, and the user's two explicit confirmations.

## Run locally
Python 3.12+. Standard library only.

```bash
python monitor.py
python -m unittest discover -s tests -v
python backtest.py --days 30
```

Outputs: `data/latest.json` and `data/backtest_latest.json`. The backtest fetches historical Bybit candles and evaluates the same LONG classifier; it enters at the next 5m open, uses an ATR(14) stop (1.5x), a 2R target, and includes configured taker fees, adverse slippage, and hourly funding. It uses a conservative stop-first rule if stop and target are both touched in one candle. Funding is a fixed stress assumption, not actual historical funding.

## GitHub Actions
The workflow is configured for a manual run and a 15-minute schedule on the `bybit-long-v1` branch. It runs the monitor and unit tests, then commits the refreshed snapshot to that branch. Scheduled runs require this workflow to be merged into the repository's default branch or otherwise enabled there; this feature branch alone does not guarantee scheduled execution.

## Safety
- LONG-only; no SHORT logic
- No trading, wallet, leverage-setting, transfer, or position-management API calls
- No API keys or secrets
- No averaging-down logic
- Missing timeframe data or insufficient history => WAIT / failed run
- No claim of profitability until a fee-, slippage-, funding-, stop/target-aware historical backtest has been completed
