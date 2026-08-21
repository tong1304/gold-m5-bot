# Real-Money Validation v5 Design

## Goal
Make the XAU/USD M5 signal/backtest engine conservative enough to validate whether an apparent trading edge survives realistic execution costs, incomplete intrabar information, timeouts, and account-level risk controls.

## Scope
This change covers `app.py`, `engine_v42.py`, and focused regression tests. The existing signal-generation concepts (patterns, directional filter, regime, location, momentum, trigger quality, score, ATR-based levels) remain intact unless a change is required to prevent optimistic execution or unsafe live behavior.

## Design

### 1. Execution model
Use explicit execution-side semantics. BUY entries are modeled on Ask and BUY exits on Bid; SELL entries are modeled on Bid and SELL exits on Ask. Spread and slippage remain configurable and are applied consistently to both entry and exit assumptions. The engine will expose `raw_entry`, `expected_entry`, `execution_cost`, and execution assumptions in backtest results.

Because Twelve Data OHLC data cannot reveal intrabar tick order, the simulator will use a conservative deterministic rule when multiple barriers can be reached within one candle: adverse protection is assumed before favorable target unless a known state transition proves otherwise. This rule will be documented in the result warning.

### 2. Timeout and expectancy accounting
`TIMEOUT` remains a first-class outcome. Historical probability may still report resolved win rate, but the primary performance metric becomes `net_expectancy_r`, which includes WIN, LOSS, BREAKEVEN and TIMEOUT outcomes according to the configured timeout policy. Reports will always expose the complete outcome distribution so TIMEOUT cannot be hidden.

### 3. Entry realism
Backtests continue to use the next candle as the earliest theoretical entry, but the result explicitly distinguishes theoretical next-open from modeled execution price. Live `/signal` responses will expose a maximum entry-age/tolerance policy and reject stale or materially moved prices instead of implying that a delayed Telegram notification is the next-open fill.

### 4. Costs and market conditions
Spread and slippage are configurable per symbol and can be bounded by a maximum acceptable live spread/slippage. Backtest outputs include gross and net R so the cost impact is visible. Signals are rejected when live spread is unavailable, stale, or above the configured maximum.

### 5. SL/TP and break-even
SL/TP calculations retain structure and ATR constraints but validate that the resulting stop is not implausibly compressed by `MAX_STOP_ATR`. A trade is rejected when the effective risk is invalid or the post-cost reward/risk falls below the minimum requirement. Break-even is represented as an explicit state transition and is not treated as a free intrabar action; with candle-only data, activation and stop-hit ordering use the same conservative rule as the simulator.

### 6. Validation
Add out-of-sample and walk-forward summaries using the available historical candles. Results are separated into calibration/training and evaluation windows. Score buckets and directional/regime/pattern statistics require a minimum sample before being described as an empirical edge. Score remains a model score, never a probability.

### 7. Live risk controls
Add a runtime risk guard with configurable limits for maximum spread, stale data, price jumps, consecutive losses, daily loss in R, and trades per day. A tripped guard returns `NO_TRADE` and records a machine-readable reason. These controls are protective defaults, not position sizing or broker-order execution.

### 8. Production security and symbol isolation
Remove traceback and exception internals from public JSON responses. Keep detailed tracebacks in server logs. Replace mutable cross-request symbol state where practical with request-scoped configuration; if the existing engine requires compatibility globals, the middleware lock remains the final isolation boundary and tests verify restoration after both success and failure.

## Acceptance Criteria
1. Backtest cost accounting applies consistently to both entry and exit semantics.
2. Every simulated trade has one explicit outcome: WIN, LOSS, BREAKEVEN, or TIMEOUT.
3. Primary performance reporting includes net expectancy after modeled costs and shows timeout counts.
4. Intrabar ambiguity is conservative and documented.
5. Live signal rejects stale data, excessive spread, or excessive price movement.
6. Daily loss, consecutive-loss, and daily-trade limits can force `NO_TRADE`.
7. Public error responses do not contain tracebacks or exception class details.
8. BUY/SELL and symbol configurations remain isolated across requests.
9. Regression tests cover execution cost, timeout accounting, BE state, risk guard, and error sanitization.
10. Existing `/signal`, `/backtest`, `/health`, `/test-data`, and `/diagnostics` routes remain functional.
11. The resulting engine is labeled validation/paper-trading safe until broker-specific live execution has been separately verified.
