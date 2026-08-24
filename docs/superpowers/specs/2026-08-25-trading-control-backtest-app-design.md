# Trading Control & Backtest App — Design Specification

## Goal

Build a separate web application from the live V12.9 trading service. The app is a control/analysis console only; it must not become part of the live signal engine.

## Scope

### 1. Telegram alert control
- One control only: **Telegram Notifications ON/OFF**.
- ON: the live bot is allowed to send Telegram alerts.
- OFF: Telegram alerts are suppressed without stopping market-data ingestion or signal analysis.
- The control state is persisted so a restart does not silently re-enable notifications.
- The control app communicates the state through a small shared state/API mechanism rather than modifying trading decisions.

### 2. Historical backtest
- A dedicated **Run Backtest** button.
- User can select symbol (BTC/GOLD) and a historical period/bars.
- Backtest uses the same V12.9 strategy logic/data assumptions as the live system where practical, but runs independently and never sends Telegram alerts.
- Results are saved as a backtest run record.

### 3. Statistics page
Display, at minimum:
- total trades
- wins / losses / breakeven
- win rate
- net result / cumulative result
- average R
- profit factor when computable
- maximum drawdown when computable
- average trade duration when available
- strategy/setup breakdown
- BUY vs SELL breakdown
- chronological trade list with entry, SL, TP/result and timestamp

### 4. Separation
- The new app is deployed as a separate Render service.
- It must not start the V12.9 scheduler or live-price worker.
- It must not place live orders.
- It must not independently generate Telegram alerts.
- The live `gold-m5-bot` service remains the source of live scanning and notifications.

## Proposed structure

`control-app/`
- `app.py` — Flask web/API entry point
- `templates/index.html` — control dashboard
- `static/app.js` — UI interactions
- `static/style.css` — responsive dashboard styling
- `backtest.py` — isolated backtest runner
- `stats.py` — metrics aggregation
- `state.py` — persistent Telegram enabled/disabled state
- `requirements.txt`
- `render.yaml` — optional Render configuration for this service
- `README.md` — deployment/configuration instructions

## Data flow

Live bot → shared Telegram-control state → live bot's Telegram sender

Historical data/strategy → isolated backtest runner → stored run/result → statistics API → dashboard

The dashboard can read live control state and backtest results, but it does not control the scheduler, market-data connection, or trading logic.

## Error handling

- Backtest failure is shown as a failed run with an error message; it must not affect the live bot.
- Missing/stale historical data produces a clear data-quality error rather than fabricated statistics.
- Telegram OFF must fail closed: if the control state cannot be read, notification sending should default to OFF where the live sender integrates this state.
- A backtest must never call the live Telegram sender.

## Testing

- Unit tests for Telegram state persistence and fail-closed behavior.
- Unit tests for win rate, profit factor, drawdown, R calculations and trade grouping.
- Backtest smoke test proving no Telegram call is made.
- API smoke tests for control state, backtest start, run status and statistics.
- UI smoke test for ON/OFF and Run Backtest flows.

## Acceptance criteria

1. Opening the new app does not start the V12.9 scheduler.
2. Telegram can be switched ON/OFF from one visible control.
3. OFF remains OFF after app restart.
4. Run Backtest starts an isolated historical test and shows progress/result.
5. Statistics page displays aggregate metrics and individual historical trades.
6. Backtest results are distinguishable from live signal history.
7. No backtest operation sends a Telegram message or changes live trading state.
8. The live V12.9 app continues operating independently.
