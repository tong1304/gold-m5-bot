# Structure V6 Trading Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the pattern-score entry model with a structure/location/liquidity/pullback engine and replay it against real LSE history without enabling live orders.

**Architecture:** Add `engine_v6.py` as the single decision engine. `live_scanner.py` adapts live M5/H1/M15 data into V6 inputs and records V6 evidence. `replay_signal_history.py` calls the same V6 decision function at each closed M5 candle, then resolves outcomes using only subsequent candles. The existing statistics UI remains compatible and receives V6 metadata through `payload_json`.

**Tech Stack:** Python 3.14, pandas, NumPy, Flask, existing LSE client, existing signal-history SQLite layer.

**Spec:** `docs/superpowers/specs/2026-08-23-structure-v6-design.md`

## Global Constraints

- Supported assets remain BTC and GOLD only.
- M5 is the execution timeframe; H1 is bias and M15 is location/context.
- Minimum effective RR is 2.0R.
- No future candle may influence a historical decision.
- No automatic live order execution.
- Existing `/statistics`, `/api/statistics`, `/api/signals`, and Telegram history remain functional.
- V6 must emit `NO_TRADE` instead of forcing a signal when a required gate is absent.

---

### Task 1: Implement V6 decision engine

**Files:**
- Create: `engine_v6.py`
- Test: `tests/test_engine_v6.py`

**Interfaces:**
- Produces `analyze_structure_setup(m5, m15, h1, index) -> dict`.
- Produces `build_v6_trade_levels(m5, index, direction, invalidation, target) -> dict`.

- [ ] **Step 1: Write failing tests for BUY/SELL gates, no-lookahead structure, RR rejection, and duplicate setup key.**
- [ ] **Step 2: Run `pytest tests/test_engine_v6.py -q` and verify failures before implementation.**
- [ ] **Step 3: Implement causal swing detection, H1 structure, M15 location/liquidity, M5 sweep, MSS/BOS confirmation, pullback validation, and trade-level construction.**
- [ ] **Step 4: Run the focused tests and verify all gates behave deterministically.**
- [ ] **Step 5: Commit `feat: add structure v6 decision engine`.**

### Task 2: Switch live scanner to V6

**Files:**
- Modify: `live_scanner.py`
- Modify: `app.py`
- Test: `tests/test_live_scanner_v6.py`

**Interfaces:**
- `scan_once(symbol)` continues to return the existing API shape plus `engine_version=6.0` and V6 evidence.
- Telegram keeps the existing entry/SL/TP presentation and adds the V6 setup explanation.

- [ ] **Step 1: Write tests proving a valid V6 setup is emitted only when all required gates pass.**
- [ ] **Step 2: Run the focused tests and confirm the old score-based path fails the new expectations.**
- [ ] **Step 3: Replace pattern majority/confluence as the entry decision with `engine_v6.analyze_structure_setup`.**
- [ ] **Step 4: Preserve BTC/GOLD configuration, history recording, duplicate suppression, and live-orders-disabled behavior.**
- [ ] **Step 5: Run focused tests and commit `feat: route live signals through structure v6`.**

### Task 3: Make historical replay use the exact V6 engine

**Files:**
- Modify: `replay_signal_history.py`
- Test: `tests/test_replay_v6.py`

**Interfaces:**
- `replay_symbol(symbol, start, end, dry_run=False)` remains the CLI entry point.
- Replay payload contains `v6_setup`, `structure_bias`, `location`, `liquidity_event`, `m5_trigger`, `entry_model`, and `rejection_reasons`.

- [ ] **Step 1: Write tests that verify replay calls V6 only on closed candles and resolves outcomes only from later candles.**
- [ ] **Step 2: Run focused tests and verify the expected failures.**
- [ ] **Step 3: Replace `pattern_engine`/`_resolve_m5_direction` as the signal generator with V6.**
- [ ] **Step 4: Keep the existing LSE date-only request format and normalize returned candles locally.**
- [ ] **Step 5: Run focused tests and commit `feat: replay structure v6 on real history`.**

### Task 4: Preserve statistics and expose V6 diagnostics

**Files:**
- Modify: `statistics_page.py`
- Test: `tests/test_statistics_v6.py`

**Interfaces:**
- `/api/statistics` remains backward compatible.
- Rows expose V6 fields without breaking legacy pattern fields.

- [ ] **Step 1: Write tests for V6 evidence extraction and fallback to legacy pattern fields.**
- [ ] **Step 2: Run focused tests and confirm the new fields are absent before implementation.**
- [ ] **Step 3: Add V6 columns/details to the statistics response and page.**
- [ ] **Step 4: Run focused tests and verify legacy rows still render.**
- [ ] **Step 5: Commit `feat: expose structure v6 statistics`.**

### Task 5: Run historical statistics test

**Files:**
- Modify: `README.md` only if the final replay command needs documenting.

- [ ] **Step 1: Run `python replay_signal_history.py --start 2026-08-01 --end 2026-08-23 --dry-run`.**
- [ ] **Step 2: Run the real replay with `--symbol BTC` and then `--symbol GOLD` when `LSE_API_KEY` is available.**
- [ ] **Step 3: Record WIN/LOSS/OPEN, Win Rate, Net R, Profit Factor, Max Drawdown, MFE/MAE, and setup-level breakdown.**
- [ ] **Step 4: Compare V6 against the stored legacy replay without changing live-order behavior.**
- [ ] **Step 5: Commit the verified replay/report changes.**

---

## Verification checklist

- `pytest -q`
- `python replay_signal_history.py --start 2026-08-01 --end 2026-08-23 --symbol BTC --dry-run`
- `python replay_signal_history.py --start 2026-08-01 --end 2026-08-23 --symbol GOLD --dry-run`
- Confirm `/statistics` still loads.
- Confirm `engine_version` is 6.0 on new signals.
- Confirm no automatic order execution is introduced.
