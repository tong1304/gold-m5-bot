# Regime Engine + 8 Strategies + Controlled Re-entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current V11 strategy-selection behavior with the approved Regime Engine architecture: TREND → E1-E5, RANGE → E6-E8, TRANSITION → E3/E4/E7, followed by Setup Scorer, Entry Trigger, Setup ID/State, Initial/Re-entry, Risk Engine, RR/Target, and Final Signal.

**Architecture:** `v11/engine.py` becomes the production orchestration boundary. `v11/regime.py` classifies the market deterministically into TREND/RANGE/TRANSITION and exposes evidence. A new `v11/strategy_engine.py` owns the eight strategy contracts, setup scoring, trigger validation, setup identity, and controlled re-entry state. Existing risk calculation remains the final risk gate. Live scanner, replay, validation, and API continue calling the same V11 engine so live and replay share identical signal logic.

**Tech Stack:** Python 3, pandas, existing V11 data/risk/Telegram/replay stack, unittest/pytest-compatible tests.

**Spec:** Approved architecture in the conversation: Market Data → Regime Engine → TREND(E1-E5)/RANGE(E6-E8)/TRANSITION(E3/E4/E7) → Setup Scorer → Entry Trigger → Setup ID/State → Initial/Re-entry → Risk Engine → RR/Target → Final Signal.

## Global Constraints

- Production engine must expose only the approved 8-engine architecture; legacy strategy modules must not be selected by production flow.
- No weighted confluence engine is introduced.
- Regime selection is a hard gate before strategy selection.
- A strategy may emit a signal only after its setup and M5 trigger are valid.
- Re-entry is allowed only for a new valid trigger belonging to the same setup identity; duplicate firing from the same candle/setup is forbidden.
- Every re-entry receives independently calculated risk levels and RR.
- If any hard gate fails, final result is `NO_TRADE`.
- Existing BTC and GOLD production symbols remain supported.
- Existing `live_orders_allowed=False` safety behavior remains unchanged unless separately authorized.

---

### Task 1: Add failing tests for regime routing and re-entry state

**Files:**
- Create: `tests/test_strategy_architecture.py`

**Interfaces:**
- Consumes: `v11.regime.classify_regime`, `v11.strategy_engine.SetupState`, `v11.strategy_engine.build_setup_id`, `v11.strategy_engine.can_emit_entry`.
- Produces: executable regression tests for regime-to-engine routing and duplicate/re-entry behavior.

- [ ] **Step 1: Write tests** for TREND allowing E1-E5 only, RANGE allowing E6-E8 only, TRANSITION allowing E3/E4/E7, duplicate trigger rejection, and a genuinely new trigger allowing re-entry.
- [ ] **Step 2: Run the tests** and verify they fail because the new interfaces do not yet exist.
- [ ] **Step 3: Keep the failing tests as the contract** for implementation.

### Task 2: Implement the Regime Engine

**Files:**
- Modify: `v11/regime.py`
- Test: `tests/test_strategy_architecture.py`

**Interfaces:**
- Produces: `classify_regime(m5, m15) -> dict` with `regime`, `allowed_engines`, and evidence fields including EMA alignment/slope, ADX/DMI, ATR expansion/compression, VWAP, range structure, and transition evidence.

- [ ] **Step 1:** Add deterministic ADX(14), DI+/DI-, EMA20/50/200, ATR14, VWAP, volume ratio, candle body/range, and recent range/compression calculations using existing project helpers where available.
- [ ] **Step 2:** Implement hard regime classification: TREND when directional EMA/structure and ADX/DMI evidence agree; RANGE when trend evidence is weak and range/compression/flatness dominate; TRANSITION when a range is breaking or trend/range state is changing.
- [ ] **Step 3:** Return explicit allowed-engine sets: TREND `{E1,E2,E3,E4,E5}`, RANGE `{E6,E7,E8}`, TRANSITION `{E3,E4,E7}`.
- [ ] **Step 4:** Run the regime tests and verify they pass.

### Task 3: Implement the eight approved strategy contracts

**Files:**
- Create: `v11/strategy_engine.py`
- Modify: `v11/strategy_catalog.py`
- Test: `tests/test_strategy_architecture.py`

**Interfaces:**
- Produces: `evaluate_strategy(engine_id, m5, context, direction) -> dict` and `evaluate_all_allowed(m5, context) -> list[dict]`.
- Engine names are exactly `E1_TREND`, `E2_TREND_PULLBACK`, `E3_BREAKOUT`, `E4_BREAKOUT_RETEST`, `E5_MOMENTUM`, `E6_MEAN_REVERSION`, `E7_LIQUIDITY_REVERSAL`, `E8_RANGE`.

- [ ] **Step 1:** Implement E1 using EMA20/50/200, structure, ADX/DMI direction and slope.
- [ ] **Step 2:** Implement E2 as Impulse → Pullback → Continuation.
- [ ] **Step 3:** Implement E3 as Range → confirmed Break → Expansion.
- [ ] **Step 4:** Implement E4 as Break → Retest → Continuation.
- [ ] **Step 5:** Implement E5 as strong candle + volume ratio + ATR/volatility expansion.
- [ ] **Step 6:** Implement E6 as Extreme → Rejection → return-to-VWAP/mean, disabled when the regime is TREND.
- [ ] **Step 7:** Implement E7 as Sweep → Rejection → Reversal.
- [ ] **Step 8:** Implement E8 as Range High/Low → Rejection.
- [ ] **Step 9:** Ensure each result carries `engine`, `direction`, `status`, `setup_anchor`, `trigger_id`, evidence, and quality score.
- [ ] **Step 10:** Run the strategy tests and verify they pass.

### Task 4: Add Setup Scorer, Trigger Gate, Setup ID, and controlled re-entry

**Files:**
- Modify: `v11/strategy_engine.py`
- Create: `v11/setup_state.py`
- Test: `tests/test_strategy_architecture.py`

**Interfaces:**
- Produces: `score_setup(result) -> dict`, `build_setup_id(symbol, engine, direction, anchor, regime) -> str`, `can_emit_entry(state, setup_id, trigger_id) -> tuple[bool,str]`, and state serialization helpers.

- [ ] **Step 1:** Score only setups that already passed regime/setup/trigger gates; score structure, location, trigger, volume/volatility, and RR readiness without turning score into a substitute for hard gates.
- [ ] **Step 2:** Build stable setup IDs from symbol + regime + engine + direction + normalized setup anchor.
- [ ] **Step 3:** Track last emitted setup ID and trigger ID per symbol/direction.
- [ ] **Step 4:** Reject repeated calls for the same setup and trigger.
- [ ] **Step 5:** Allow re-entry only when the setup ID remains compatible but a new trigger ID is produced.
- [ ] **Step 6:** Enforce configurable `MAX_REENTRIES_PER_SETUP` and `MAX_TOTAL_RISK_PER_SETUP` without changing existing live-order safety.
- [ ] **Step 7:** Run state/re-entry tests and verify they pass.

### Task 5: Replace V11 orchestration with the approved pipeline

**Files:**
- Modify: `v11/engine.py`
- Modify: `v11/selection.py` or retire it from production imports
- Test: `tests/test_strategy_architecture.py`

**Interfaces:**
- `analyze(m5, m15, symbol, index=None)` remains the public production interface used by live scanner/replay.
- Result contains `regime`, `allowed_engines`, `setup_candidates`, `selected_setup`, `setup_id`, `entry_type` (`INITIAL`/`RE_ENTRY`), `risk`, `rr`, `score`, and final `signal`/`NO_TRADE`.

- [ ] **Step 1:** Make data-quality validation the first hard gate.
- [ ] **Step 2:** Call `classify_regime` and route only to its allowed engines.
- [ ] **Step 3:** Evaluate setups, then apply setup scorer and M5 entry trigger.
- [ ] **Step 4:** Apply setup state/re-entry gate before risk calculation.
- [ ] **Step 5:** Call existing risk engine only after setup/trigger validation; require valid RR/target.
- [ ] **Step 6:** Return one canonical final signal and rich rejection reasons.
- [ ] **Step 7:** Ensure no legacy V9/V5/V7 strategy selection path can be reached from `v11.engine.analyze`.
- [ ] **Step 8:** Run all available tests and import/compile checks.

### Task 6: Align live scanner, replay, validation, and API metadata

**Files:**
- Modify: `live_scanner_v11.py`
- Modify: `v11/replay.py`
- Modify: `v11/validation.py`
- Modify: `app.py`
- Test: `tests/test_strategy_architecture.py`

**Interfaces:**
- All callers continue using `v11.engine.analyze` as the single source of signal truth.

- [ ] **Step 1:** Remove any caller-side assumptions about the old strategy names.
- [ ] **Step 2:** Persist the new regime/engine/setup ID/entry type fields in signal history where the existing schema permits.
- [ ] **Step 3:** Make replay and live return the same signal schema and strategy identifiers.
- [ ] **Step 4:** Update API metadata from old dynamic-strategy wording to the approved 8-engine architecture.
- [ ] **Step 5:** Run syntax/import checks for all touched modules.

### Task 7: Documentation and regression verification

**Files:**
- Modify: `VALIDATION.md`
- Create: `docs/regime-engine-8-strategies.md`

- [ ] **Step 1:** Document all eight engines, regime routing, scoring, trigger rules, setup identity, and re-entry rules.
- [ ] **Step 2:** Document that Win Rate is not hard-coded and must be established by replay/backtest; thresholds remain configurable.
- [ ] **Step 3:** Run the complete available test suite plus Python compilation/import checks.
- [ ] **Step 4:** Verify no production import references the legacy multi-strategy registry as the decision maker.
- [ ] **Step 5:** Verify the final API response for both BTC and GOLD includes regime, engine, setup ID, entry type, risk, RR, and final signal.
