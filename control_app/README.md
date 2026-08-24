# V12.9 Control & Backtest App

Standalone web service for:

1. Telegram notification ON/OFF only.
2. Running BTC/GOLD historical V12.9 MTF H1→M15→M5 replay.
3. Viewing persisted statistics and individual simulated trades.

## Safety boundaries

- Does not start `scheduler_v11`, `live_price`, live scanner, or order execution.
- Backtest never calls Telegram and never places live orders.
- Backtest uses closed historical candles and the existing `v11.replay_m5` bounded-context replay.
- GOLD candles are filtered by the New York DST-aware market session gate.
- Telegram state is stored in a dedicated SQLite database.

## Render deployment

Use this branch as an independent service deployment.

- Root directory: repository root
- Build command: `pip install -r control_app/requirements.txt`
- Start command: `gunicorn control_app.app:app`
- Environment variable: `LSE_API_KEY`
- Optional: `CONTROL_APP_DB=/var/data/control_app.db`
- Optional: `CONTROL_APP_MAX_DAYS=90`

The service must be deployed as a separate Render service from the live V12.9 service. It does not use the live application's `app.py` startup path.
