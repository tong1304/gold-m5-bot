# V12.9 Control/Backtest Interface Map

## Reusable pure strategy path

- `v11.engine.ENGINE_VERSION` identifies the live strategy as `12.9-MTF-H1-M15-TREND-M5-BTC-GOLD-MULTI-TP`.
- `v11.engine.analyze(m5, m15=..., h1=..., symbol=..., setup_state=...)` is the core strategy evaluation entry point and does not start threads by itself.
- `v11.replay_m5.replay_frames(m5, m15, h1, symbol=..., start_time=..., end_time=...)` already provides a closed-candle replay loop, bounded H1/M15/M5 context, trade resolution, aggregate R statistics, and explicit `lookahead_safe=True` output.
- Replay resolves TP/SL only from the current candle and marks a candle hitting both levels as `AMBIGUOUS`; it does not use future candles to make the entry decision.

## Live-only paths that the control/backtest app must not import at startup

- `app.py` calls `_start_runtime_services()` from `before_request`, which starts `live_price` and `scheduler_v11`.
- `live_scanner_v11` imports `v11.telegram.send_telegram` and `signal_history`; it is a live-signal path and must not be used by the isolated app.
- `live_price.py` starts a WebSocket worker when started by the production app; the control/backtest app must never call it.
- `scheduler_v11.py` is explicitly a recurring live scan loop and is forbidden in the isolated app.

## Historical data adapter

- Production scanner uses `lse.LSE(api_key=...).candles(market, timeframe, start=..., end=..., limit=..., order="desc")`.
- The control/backtest app can use the same LSE candle endpoint through a dedicated historical-data adapter, but it must normalize/close-sort candles itself and must not call `live_scanner_v11._lse_frame()` because that function intentionally rejects stale data based on current time.
- Backtest tests should inject DataFrames directly so no network/API key is required.

## Persistence/UI interfaces

- SQLite is appropriate for durable Telegram state and backtest runs/trades.
- User-facing Telegram control is exactly one boolean: enabled/disabled.
- Backtest API should return a run id and persist every simulated trade plus aggregate metrics.
- Statistics UI should consume only the isolated app APIs and must not access production signal-history storage.
