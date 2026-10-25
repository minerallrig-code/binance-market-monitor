# Binance Market Monitor

Read-only Binance Spot and USD-M Futures analytics for BTCUSDT, SOLUSDT, ZECUSDT, HYPEUSDT and WLDUSDT.

## Features
- 15m and 4h closed candles
- EMA 20/50, RSI 14, MACD (12, 26, 9)
- Volume and ratio versus the previous 20 closed candles
- LONG / SHORT / WAIT signals; UNAVAILABLE when an API request fails
- Latest snapshot: `data/latest.json`

## Run
Python 3.12+. No dependencies or API keys are required.

`python monitor.py`

## GitHub Actions
Runs every 15 minutes (UTC), with manual execution available under Actions. The workflow commits refreshed `data/latest.json` to the default branch. Actions must have read/write repository permissions, and branch protection must permit the Actions bot to push.

## Signal rules
LONG requires EMA20 above EMA50, close above EMA20, RSI 50-70 and positive MACD histogram. SHORT requires EMA20 below EMA50, close below EMA20, RSI 30-50 and negative MACD histogram. Otherwise WAIT. These are analytical filters, not financial advice or guaranteed trade entries.

## Safety
Public market data only. This project does not use wallet credentials, place orders, cancel orders or modify positions.