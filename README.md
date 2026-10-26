# Bybit BTCUSDT LONG Monitor

Read-only signal monitor for **Bybit USDT Linear Futures**, focused on BTCUSDT. It does not connect to Walt, hold credentials, or place/modify orders.

## Data
- Public Bybit V5 market endpoint: `/v5/market/kline`, category `linear`
- Closed candles only: 1H, 15m, 5m
- Data source is recorded in `data/latest.json`; no silent exchange fallback
- If any required timeframe fails, the overall decision is `WAIT` (fail-closed)

## Indicators
- EMA20 / EMA50
- RSI6, RSI12, RSI14, RSI24
- MACD(12,26,9), including histogram direction
- Volume versus MA5 and MA10
- 50-candle swing high/low and Fibonacci retracements 50%, 61.8%, 78.6%

## LONG scenarios
A. Trend continuation: 1H EMA20 > EMA50; 15m price/momentum confirmation; volume filter; 5m early confirmation.

B. Reversal after sharp decline: requires a meaningful 1H decline plus improving MACD and 5m/15m confirmation. Oversold RSI or a green candle alone never qualifies.

The classifier returns `LONG_CANDIDATE` or `WAIT`. It is an analytical filter, not an executable trade signal. Before any trade, separately verify Walt balance and open positions, calculate entry/SL/TP and risk, and follow the user's two-confirmation protocol.

## Run
Python 3.12+. Standard library only.

```bash
python monitor.py
```

Output: `data/latest.json`.

## Safety constraints
- LONG only; no SHORT signals
- No order, cancellation, leverage, position, wallet or transfer APIs
- No secrets or API keys
- No averaging down logic
- Incomplete/stale/missing timeframe data => WAIT
- This repository monitor is not an autonomous trading bot
