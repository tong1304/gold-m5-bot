# Trading Control & Backtest App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a separate web app for controlling Telegram notifications and running/displaying historical V12.9 trading statistics without starting or modifying the live trading engine.

**Architecture:** The app is an isolated Flask application with its own control state, backtest runner, results storage, API endpoints, and web UI. It may reuse/import pure strategy/backtest logic from the existing repository, but must never start the live scheduler, live-price worker, order execution, or Telegram sender as a side effect of startup or backtest execution.

**Tech Stack:** Flask, existing Python/pandas/numpy/scipy stack, SQLite for control/results persistence, vanilla HTML/CSS/JavaScript, pytest.

**Spec:** `docs/superpowers/specs/2026-08-25-trading-control-backtest-app-design.md`

## Global Constraints

- The application is separate from V12.9 live runtime.
- Telegram control has exactly one user-facing control: ON/OFF notifications.
- Turning Telegram OFF must not stop live price, scheduler, signal generation, or other live services.
- Backtest must never send Telegram messages or execute live orders.
- Backtest must use closed historical candles and must not use future candles/look-ahead data.
- Backtest results must be persisted so the statistics page can be revisited after refresh/restart.
- Live trading code must not be started merely by importing the backtest/control app.
- Market-session filtering must be respected for instruments that are closed outside their configured sessions.

---

### Task 1: Map existing strategy/backtest interfaces

**Files:**
- Inspect: existing V12.9 engine, scheduler, scanner, data/provider modules, tests
- Create: `docs/superpowers/plans/notes/trading-control-backtest-interface-map.md`

**Interfaces:**
- Identify the pure strategy evaluation entry point(s), historical candle/data structures, trade/result structures, and any existing replay/statistics implementation.
- Identify imports that accidentally start scheduler/live threads and mark them forbidden for the new app.

- [ ] **Step 1: Locate V12.9 engine and replay/statistics code.**
- [ ] **Step 2: Trace data flow from candles to signal to simulated trade result.**
- [ ] **Step 3: Identify side-effectful imports/startup paths.**
- [ ] **Step 4: Document reusable pure interfaces and required adapters.**
- [ ] **Step 5: Run the existing test suite and record the baseline.**

---

### Task 2: Build isolated application skeleton

**Files:**
- Create: `control_app/app.py`
- Create: `control_app/config.py`
- Create: `control_app/__init__.py`
- Create: `control_app/templates/index.html`
- Create: `control_app/static/app.js`
- Create: `control_app/static/app.css`
- Create: `tests/control_app/test_app.py`

**Interfaces:**
- `create_app()` returns the Flask application without starting live workers.
- `GET /` renders the control/backtest UI.
- `GET /api/health` returns application health and current Telegram state.

- [ ] **Step 1: Write tests proving app creation has no live-thread side effects.**
- [ ] **Step 2: Implement `create_app()` and basic routes.**
- [ ] **Step 3: Add minimal UI shell.**
- [ ] **Step 4: Run targeted tests.**

---

### Task 3: Implement Telegram ON/OFF control

**Files:**
- Create: `control_app/telegram_control.py`
- Create: `control_app/state_store.py`
- Modify: `control_app/app.py`
- Create: `tests/control_app/test_telegram_control.py`

**Interfaces:**
- `get_telegram_enabled() -> bool`
- `set_telegram_enabled(enabled: bool) -> bool`
- `POST /api/telegram/toggle` accepts only `{enabled: boolean}` and returns the persisted state.

- [ ] **Step 1: Write tests for default state, ON, OFF, persistence, and invalid payloads.**
- [ ] **Step 2: Implement SQLite-backed state store.**
- [ ] **Step 3: Implement Telegram state API.**
- [ ] **Step 4: Ensure this state is the only Telegram control exposed in UI.**
- [ ] **Step 5: Run tests.**

---

### Task 4: Add backtest engine adapter

**Files:**
- Create: `control_app/backtest/engine.py`
- Create: `control_app/backtest/data.py`
- Create: `control_app/backtest/models.py`
- Create: `tests/control_app/test_backtest_engine.py`

**Interfaces:**
- `run_backtest(symbol: str, start: datetime, end: datetime) -> BacktestResult`
- `BacktestResult` contains run metadata, trades, and aggregate statistics.
- Historical data access must be injectable so tests can use deterministic fixtures.

- [ ] **Step 1: Write deterministic fixture tests for candle ordering and no look-ahead.**
- [ ] **Step 2: Implement historical-data loader/adapter.**
- [ ] **Step 3: Implement pure replay loop using closed candles only.**
- [ ] **Step 4: Reuse V12.9 pure strategy logic through an adapter where safe; otherwise isolate equivalent deterministic evaluation logic without importing live startup.**
- [ ] **Step 5: Add session filter so GOLD is skipped outside configured market sessions while BTC remains available according to its configured market availability.**
- [ ] **Step 6: Run targeted tests.**

---

### Task 5: Persist backtest runs and statistics

**Files:**
- Create: `control_app/backtest/repository.py`
- Modify: `control_app/state_store.py`
- Create: `tests/control_app/test_backtest_repository.py`

**Interfaces:**
- `save_backtest(result: BacktestResult) -> str`
- `get_backtest(run_id: str) -> BacktestResult`
- `list_backtests(limit: int = 20) -> list[BacktestSummary]`

- [ ] **Step 1: Write persistence round-trip tests.**
- [ ] **Step 2: Implement SQLite tables for runs and trades.**
- [ ] **Step 3: Persist aggregate metrics and every simulated trade.**
- [ ] **Step 4: Run tests.**

---

### Task 6: Expose Backtest API

**Files:**
- Modify: `control_app/app.py`
- Create: `tests/control_app/test_backtest_api.py`

**Interfaces:**
- `POST /api/backtest` starts a backtest request and returns a run identifier/status.
- `GET /api/backtest/<run_id>` returns run status, summary, and trade results.
- `GET /api/backtests` returns recent runs.

- [ ] **Step 1: Write API tests for valid BTC/GOLD requests and invalid date ranges.**
- [ ] **Step 2: Implement request validation.**
- [ ] **Step 3: Invoke isolated backtest engine.**
- [ ] **Step 4: Persist result and return run ID.**
- [ ] **Step 5: Verify Telegram is never called during backtest.**
- [ ] **Step 6: Run tests.**

---

### Task 7: Build Statistics UI

**Files:**
- Modify: `control_app/templates/index.html`
- Modify: `control_app/static/app.js`
- Modify: `control_app/static/app.css`

**Interfaces:**
- UI displays Total Trades, Wins, Losses, BE, Win Rate, Net Result, Average R, Profit Factor, and Max Drawdown.
- UI displays strategy breakdown, BUY/SELL breakdown, and detailed trade table.
- UI provides `Run Backtest` and a recent-run selector.

- [ ] **Step 1: Add Telegram ON/OFF control card.**
- [ ] **Step 2: Add backtest form for symbol/date range.**
- [ ] **Step 3: Add summary metric cards.**
- [ ] **Step 4: Add strategy and side breakdown tables.**
- [ ] **Step 5: Add detailed trade table with entry/exit, side, strategy, result, R, and timestamps.**
- [ ] **Step 6: Add loading/error/empty states.**
- [ ] **Step 7: Verify responsive layout.**

---

### Task 8: Add standalone deployment configuration

**Files:**
- Create: `control_app/requirements.txt`
- Create: `control_app/Procfile`
- Create: `control_app/README.md`
- Create: `tests/control_app/test_import_isolation.py`

**Interfaces:**
- Deployment starts only the control/backtest Flask app.
- No live scheduler or WebSocket worker starts from the deployed app.

- [ ] **Step 1: Write import-isolation test.**
- [ ] **Step 2: Add minimal dependencies.**
- [ ] **Step 3: Add Gunicorn start command.**
- [ ] **Step 4: Document environment variables and deployment.**
- [ ] **Step 5: Run deployment smoke test.**

---

### Task 9: End-to-end verification

**Files:**
- Modify: `tests/control_app/test_e2e.py`
- Modify: `control_app/README.md`

- [ ] **Step 1: Start the control app locally.**
- [ ] **Step 2: Toggle Telegram OFF and verify persisted state.**
- [ ] **Step 3: Run deterministic BTC backtest and verify non-empty statistics.**
- [ ] **Step 4: Run GOLD backtest through an interval containing a configured market closure and verify closed-session candles are excluded.**
- [ ] **Step 5: Verify no live scheduler/live-price thread is started.**
- [ ] **Step 6: Verify no Telegram call occurs.**
- [ ] **Step 7: Run the complete test suite.**
- [ ] **Step 8: Only after verification, publish/deploy the app.**

---

## Completion Criteria

The implementation is complete only when:

1. The new app can be deployed independently of V12.9.
2. The UI has exactly one Telegram control: ON/OFF.
3. Telegram OFF persists across restart and does not stop live trading services.
4. A user can run BTC/GOLD historical backtests from the UI.
5. Backtests do not send Telegram messages or execute live orders.
6. Statistics include aggregate metrics plus per-trade details.
7. GOLD closed-session periods are skipped instead of producing stale-data errors.
8. The app imports without starting V12.9 scheduler/live-price workers.
9. Automated tests pass, including isolation and no-look-ahead checks.
