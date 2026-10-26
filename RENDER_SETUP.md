# Render deployment

## Live read-only monitor

This repository includes `render.yaml` for a Singapore-region Render Cron Job.

1. Open the Render Dashboard and choose **New → Blueprint**.
2. Connect `minerallrig-code/binance-market-monitor`.
3. Select branch `bybit-long-v1`.
4. Review the Blueprint resource `bybit-long-monitor`:
   - Region: Singapore
   - Plan: 0.5 CPU / 512 MB
   - Schedule: every 15 minutes (UTC cron: `*/15 * * * *`)
   - Command: `python monitor.py`
5. Deploy the Blueprint.

The monitor uses public Bybit V5 market data only. It does not need API keys and cannot place orders. Each run prints a compact JSON signal to the Render logs. If required market data is unavailable, it exits as failed and reports WAIT rather than producing a trade signal.

## Historical backtest

Run this as a one-off job from the Render service context (or from a permitted-region Python environment), using the same branch:

```bash
python backtest.py --days 30
```

For additional periods:

```bash
python backtest.py --days 90
python backtest.py --days 180
```

The report is written to `data/backtest_latest.json` and printed to standard output. Cron jobs use ephemeral filesystems, so download or copy the report from the run logs/artifacts before the job exits if persistent retention is required.

## Important

- The Render Blueprint creates a billable Cron Job. Review the plan and expected cost in Render before deploying.
- Singapore is selected as the intended deployment region, but API reachability is not guaranteed; validate with the first run.
- Do not use proxies or attempt to bypass exchange geographic restrictions. If Bybit returns HTTP 403, stop and use an officially permitted endpoint/region.
- This is analytics only. No exchange credentials, wallet connection, or order execution are included.
- The current backtest uses a fixed funding stress assumption, not historical funding records. Treat its results accordingly.
