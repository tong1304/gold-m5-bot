# V11 Strategy Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build V11 as the single shared M5/M15 decision engine for BTC and GOLD, with each strategy implemented in its own module and Replay/Live/Statistics consuming the same result schema.

**Architecture:** A small V11 orchestration layer owns timeframe preparation, strategy registry, M15 direction, alignment and RR=1:2 levels. Asset-specific strategy modules own only their own setup logic. Live scanner and date-range replay both call the same `analyze()` function.

**Tech Stack:** Python, pandas, Flask, existing LSE client, existing signal history/Telegram modules, pytest/GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-24-v11-strategy-architecture-design.md`

## Global Constraints

- Engine version is `11.0-M5-M15-STRATEGY-SPLIT`.
- M5 is the entry/setup timeframe; M15 is trend context.
- Global Candle Confirmation is not a V11 filter.
- BTC and GOLD have separate strategy registries.
- Default target RR is exactly 1:2; lower effective RR is rejected.
- Replay uses real LSE historical OHLCV and Bangkok calendar date selection with warm-up.
- Replay never sends Telegram.
- Live orders remain disabled.

---

### Task 1: Add V11 strategy contracts and shared helpers

**Files:**
- Create: `v11/__init__.py`
- Create: `v11/common.py`
- Create: `v11/contracts.py`
- Create: `tests/test_v11_contracts.py`

**Interfaces:**
- `StrategyResult(status, direction, strategy, reasons, evidence)`.
- `evaluate_strategy(name, m5, direction, context)` registry-independent helper.
- Shared candle/body/wick, ATR, momentum and structure helpers.

- [ ] Write tests for BUY/SELL direction normalization, candle metrics, ATR availability and structured strategy results.
- [ ] Run `pytest tests/test_v11_contracts.py -v` and verify the new tests fail because V11 does not exist.
- [ ] Implement the minimal contracts/helpers.
- [ ] Run the same test and verify it passes.

### Task 2: Implement BTC strategies separately

**Files:**
- Create: `v11/strategies/__init__.py`
- Create: `v11/strategies/btc/__init__.py`
- Create: `v11/strategies/btc/trend_pullback.py`
- Create: `v11/strategies/btc/breakout_retest.py`
- Create: `v11/strategies/btc/range_breakout.py`
- Create: `v11/strategies/btc/momentum.py`
- Create: `v11/strategies/btc/volatility_breakout.py`
- Create: `tests/test_v11_btc_strategies.py`

**Interfaces:**
- Every module exposes `evaluate(m5, direction, context) -> StrategyResult`.

- [ ] Write deterministic fixture tests proving each strategy evaluates only its own rules and does not apply the global Candle Confirmation filter.
- [ ] Run the BTC test file and verify the expected failures.
- [ ] Implement each strategy using the current V10.3 high-rated intent as the starting behavior, but isolate its filters.
- [ ] Run the BTC test file and verify it passes.

### Task 3: Implement GOLD strategies separately

**Files:**
- Create: `v11/strategies/gold/__init__.py`
- Create: `v11/strategies/gold/trend_pullback.py`
- Create: `v11/strategies/gold/breakout_retest.py`
- Create: `v11/strategies/gold/ema_pullback.py`
- Create: `v11/strategies/gold/liquidity_sweep.py`
- Create: `v11/strategies/gold/sr_reversal.py`
- Create: `v11/strategies/gold/volatility_breakout.py`
- Create: `tests/test_v11_gold_strategies.py`

**Interfaces:**
- Every module exposes `evaluate(m5, direction, context) -> StrategyResult`.

- [ ] Write deterministic fixture tests for all GOLD strategies.
- [ ] Run the GOLD test file and verify the expected failures.
- [ ] Implement each strategy independently.
- [ ] Run the GOLD test file and verify it passes.

### Task 4: Build V11 orchestration, M15 trend and risk levels

**Files:**
- Create: `v11/engine.py`
- Create: `tests/test_v11_engine.py`

**Interfaces:**
- `analyze(m5, m15, symbol, index=None) -> dict`.
- `get_strategy_registry(symbol) -> tuple[str, ...]`.
- `detect_m15_trend(m15) -> dict`.
- `build_v11_levels(m5, direction, strategy, context) -> dict`.

- [ ] Write tests for M5/M15 alignment, NO_TRADE on disagreement, valid RR=2.0 levels, and rejection of RR below 2.
- [ ] Run tests and verify they fail before implementation.
- [ ] Implement orchestration and levels while preserving existing spread/slippage/risk guards.
- [ ] Run tests and verify they pass.

### Task 5: Switch Live scanner and scheduler to V11

**Files:**
- Create: `live_scanner_v11.py`
- Create: `scheduler_v11.py`
- Modify: `app.py`
- Modify: `scheduler.py`
- Create: `tests/test_v11_live_path.py`

**Interfaces:**
- Live scan keeps `/signal` behavior but returns the V11 schema.
- Scheduler status reports V11 and M5/M15 timeframes.

- [ ] Write tests proving live scan calls V11 and that NO_TRADE cannot trigger Telegram.
- [ ] Run the tests and verify failure against the old V10.3 path.
- [ ] Implement V11 adapters and switch app/scheduler imports.
- [ ] Run tests and verify they pass.

### Task 6: Switch DATE_RANGE Replay to V11

**Files:**
- Create: `replay_signal_history_v11.py`
- Modify: replay route registration file identified by the current `/api/replay/start` implementation.
- Create: `tests/test_replay_v11.py`

**Interfaces:**
- Replay remains date-based, not candle-selection based.
- `replay_symbol(symbol, start, end, dry_run=False)` returns generated/inserted/outcomes/strategy_stats and V11 engine metadata.

- [ ] Write tests for Bangkok date bounds, LSE date-only requests, warm-up and shared-engine invocation.
- [ ] Run tests and verify the expected failures.
- [ ] Implement the V11 replay adapter using the existing corrected date-only LSE fetch behavior.
- [ ] Run tests and verify they pass.

### Task 7: Update Statistics for V11 entry detail

**Files:**
- Modify: `statistics_page.py`
- Create/update: `tests/test_statistics_entries.py` only as needed.

- [ ] Add assertions for strategy, M5 direction, M15 trend, entry, SL, TP, RR and result detail.
- [ ] Run the statistics tests.
- [ ] Update rendering/API mapping to accept V11 records without breaking historical V10.3 records.
- [ ] Run the statistics tests again.

### Task 8: Integration verification and deployment

**Files:**
- Modify: `VALIDATION.md` if required.
- Add/adjust GitHub workflow tests if required.

- [ ] Run the full pytest suite in GitHub Actions.
- [ ] Verify `/`, `/signal`, `/scheduler/status`, `/replay`, and `/statistics` use V11.
- [ ] Verify replay does not send Telegram.
- [ ] Verify live orders remain disabled.
- [ ] Create PR from `v11-strategy-architecture` to `main`.
- [ ] Review CI results and merge only after verification passes.
