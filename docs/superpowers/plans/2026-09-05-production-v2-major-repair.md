# Production V2 Major Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair Production V2 so opportunity lifecycle, persistence, decision authority, and execution state are deterministic and separately observable from E1 through actual execution.

**Architecture:** Keep E1-E9 sequential and closed-candle-only. Make `opportunity_lifecycle.py` the only lifecycle state machine, make persistent memory explicit, and add an execution-event boundary so E9 approval cannot be mistaken for broker execution.

**Tech Stack:** Python 3, Flask, existing Production V2 `EngineResult` contracts, PostgreSQL via psycopg when configured, pytest.

**Spec:** `docs/superpowers/specs/2026-09-05-production-v2-major-repair.md`

## Global Constraints

- M5 closed-candle-only remains mandatory.
- No lookahead remains forbidden.
- E9 remains final decision authority.
- Do not lower signal thresholds to increase trade count.
- E7 cannot manufacture an E6 thesis.
- E8 cannot make an inapplicable setup tradeable.
- Decision state and execution state must remain separate.
- Duplicate candles must be idempotent.

---

### Task 1: Establish a canonical lifecycle state machine

**Files:**
- Modify: `production_v2/opportunity_lifecycle.py`
- Test: `tests/test_production_v2_lifecycle.py`

**Interfaces:**
- Produce one public transition function, `advance_opportunity(previous: dict | None, current: dict) -> dict`.
- Preserve canonical states `IDLE`, `WATCHING`, `WAITING`, `READY`, `EXECUTED`, `INVALIDATED`, `EXPIRED`, `REPLACED`.
- Do not expose a second independent transition implementation.

- [ ] **Step 1: Write failing lifecycle tests**

```python
def test_watch_promotes_only_when_current_setup_is_real():
    previous = {"state": "WATCHING", "opportunity_id": "BUY|OPPORTUNITY_WATCH", "direction": "BUY", "setup": "OPPORTUNITY_WATCH", "bars_waited": 0}
    current = {"candidate": True, "direction": "BUY", "setup": "AUCTION_ACCEPTANCE_CONTINUATION", "ready": False, "invalidated": False, "candle": "c2"}
    result = advance_opportunity(previous, current)
    assert result["state"] == "WAITING"
    assert result["opportunity_id"] == "BUY|OPPORTUNITY_WATCH"


def test_decision_does_not_create_executed_state():
    previous = {"state": "READY", "opportunity_id": "BUY|SETUP_THESIS", "direction": "BUY", "setup": "SETUP_THESIS", "bars_waited": 1}
    current = {"candidate": True, "direction": "BUY", "setup": "SETUP_THESIS", "ready": True, "executed": False, "candle": "c3"}
    result = advance_opportunity(previous, current)
    assert result["state"] == "READY"


def test_explicit_execution_event_is_required_for_executed():
    previous = {"state": "READY", "opportunity_id": "BUY|SETUP_THESIS", "direction": "BUY", "setup": "SETUP_THESIS", "bars_waited": 1}
    current = {"candidate": True, "direction": "BUY", "setup": "SETUP_THESIS", "ready": True, "executed": True, "execution_state": "POSITION_OPEN", "candle": "c4"}
    result = advance_opportunity(previous, current)
    assert result["state"] == "EXECUTED"
    assert result["execution_state"] == "POSITION_OPEN"
```

- [ ] **Step 2: Run the focused tests and verify the old duplicate semantics fail**

Run: `pytest tests/test_production_v2_lifecycle.py -q`
Expected: at least the execution-semantics test fails against the pre-repair implementation.

- [ ] **Step 3: Remove `advance_lifecycle()` as a second state machine and fold required behavior into `advance_opportunity()`**

The implementation must derive identity from the existing opportunity ID when an active opportunity continues, preserve watch age, and transition to `EXECUTED` only when `current["executed"] is True`.

- [ ] **Step 4: Run focused lifecycle tests**

Run: `pytest tests/test_production_v2_lifecycle.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add production_v2/opportunity_lifecycle.py tests/test_production_v2_lifecycle.py
git commit -m "fix: make opportunity lifecycle canonical"
```

---

### Task 2: Separate execution events from E9 decisions

**Files:**
- Create: `production_v2/execution_state.py`
- Modify: `production_v2/opportunity_lifecycle.py`
- Test: `tests/test_production_v2_execution_state.py`

**Interfaces:**
- `normalize_execution_state(value: Any) -> str` returns `NONE`, `ORDER_INTENT`, `ORDER_SUBMITTED`, `ACCEPTED`, `REJECTED`, `POSITION_OPEN`, or `POSITION_CLOSED`.
- `advance_execution(previous: dict | None, event: dict) -> dict` validates legal transitions and records an execution reference when supplied.

- [ ] **Step 1: Write failing execution tests**

```python
def test_e9_buy_is_not_execution():
    result = advance_execution(None, {"decision": "BUY", "execution_event": False})
    assert result["state"] == "NONE"


def test_order_intent_is_distinct_from_position_open():
    result = advance_execution(None, {"decision": "BUY", "execution_state": "ORDER_INTENT", "execution_event": True})
    assert result["state"] == "ORDER_INTENT"


def test_rejected_order_never_becomes_executed():
    first = advance_execution(None, {"execution_state": "ORDER_SUBMITTED", "execution_event": True})
    second = advance_execution(first, {"execution_state": "REJECTED", "execution_event": True})
    assert second["state"] == "REJECTED"
    assert second.get("executed") is False
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_production_v2_execution_state.py -q`
Expected: FAIL because the execution state module does not yet exist.

- [ ] **Step 3: Implement the explicit state machine**

Permit only these forward transitions: `NONE -> ORDER_INTENT -> ORDER_SUBMITTED -> ACCEPTED -> POSITION_OPEN -> POSITION_CLOSED`; permit `ORDER_SUBMITTED -> REJECTED`. Set `executed=True` only for `POSITION_OPEN` or a terminal accepted execution event explicitly mapped to the lifecycle contract.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_production_v2_execution_state.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add production_v2/execution_state.py production_v2/opportunity_lifecycle.py tests/test_production_v2_execution_state.py
git commit -m "feat: add explicit execution state boundary"
```

---

### Task 3: Make persistent opportunity memory explicit and production-safe

**Files:**
- Modify: `production_v2/opportunity_memory.py`
- Modify: `production_v2/app.py`
- Test: `tests/test_production_v2_memory.py`

**Interfaces:**
- Keep `load_all()`, `load(symbol)`, `save(symbol, state)`, `remove(symbol)`, `backend()`, and `last_error()` compatible.
- Production with a configured PostgreSQL URL must fail health checks when PostgreSQL is unavailable instead of silently reverting to `/tmp`.

- [ ] **Step 1: Write failing persistence tests**

```python
def test_configured_postgres_is_reported_as_postgres(monkeypatch):
    monkeypatch.setenv("OPPORTUNITY_MEMORY_DATABASE_URL", "postgresql://example/db")
    assert backend() == "POSTGRES"


def test_file_backend_is_not_presented_as_durable_production_storage(monkeypatch):
    monkeypatch.delenv("OPPORTUNITY_MEMORY_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("RENDER_ENV", "production")
    assert backend() == "FILE"
    assert is_persistent_backend() is False
```

- [ ] **Step 2: Run tests and verify the new production-safety assertion fails**

Run: `pytest tests/test_production_v2_memory.py -q`
Expected: FAIL until `is_persistent_backend()` and health semantics are implemented.

- [ ] **Step 3: Add explicit backend durability reporting**

Add `is_persistent_backend() -> bool`. Keep FILE for local/test operation, but expose it as non-durable. When PostgreSQL is configured and connection/setup fails, preserve the error and let health return degraded rather than hiding it.

- [ ] **Step 4: Update `/health`**

Return HTTP 503 when runtime is not started or when the configured persistent backend is unhealthy. Include `opportunity_memory_backend`, `opportunity_memory_persistent`, and `opportunity_memory_error`.

- [ ] **Step 5: Run focused memory tests**

Run: `pytest tests/test_production_v2_memory.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add production_v2/opportunity_memory.py production_v2/app.py tests/test_production_v2_memory.py
git commit -m "fix: make opportunity memory durability explicit"
```

---

### Task 4: Remove the app/pipeline lifecycle double-write

**Files:**
- Modify: `production_v2/pipeline.py`
- Modify: `production_v2/app.py`
- Test: `tests/test_production_v2_lifecycle_integration.py`

**Interfaces:**
- Pipeline owns lifecycle transition and returns it in `result.risk["opportunity_lifecycle"]`.
- App only loads the persisted previous state before evaluation and persists the lifecycle returned by the pipeline; it must not call `advance_opportunity()` again.

- [ ] **Step 1: Write an integration test that spies on lifecycle advancement**

```python
def test_pipeline_advances_lifecycle_once(monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline_module, "advance_opportunity", lambda previous, current: calls.append((previous, current)) or {"state": "WATCHING", "opportunity_id": "BUY|OPPORTUNITY_WATCH", "bars_waited": 0})
    # invoke the pipeline through the production lifecycle entry point
    # and assert one transition call for one closed candle
    assert len(calls) == 1
```

- [ ] **Step 2: Run the test and verify the double-owner behavior is exposed**

Run: `pytest tests/test_production_v2_lifecycle_integration.py -q`
Expected: FAIL or observe more than one lifecycle advancement with the current app monkeypatch path.

- [ ] **Step 3: Move the lifecycle write boundary into the pipeline result contract**

The pipeline should accept the previous persisted state, calculate one `current` lifecycle input, call the canonical transition once, attach it to `risk`, and not claim execution unless an execution event is supplied.

- [ ] **Step 4: Simplify `_run_with_lifecycle()`**

App-level code may inject `opportunity_resume_state` and persist the returned lifecycle, but must not recompute it. Remove the second `advance_opportunity()` call and preserve the existing result shape.

- [ ] **Step 5: Run integration tests**

Run: `pytest tests/test_production_v2_lifecycle_integration.py -q`
Expected: PASS with exactly one lifecycle transition.

- [ ] **Step 6: Commit**

```bash
git add production_v2/pipeline.py production_v2/app.py tests/test_production_v2_lifecycle_integration.py
git commit -m "fix: make pipeline the lifecycle transition owner"
```

---

### Task 5: Correct E9 decision versus execution semantics and statistics

**Files:**
- Modify: `production_v2/app.py`
- Modify: `production_v2/statistics.py`
- Test: `tests/test_production_v2_statistics.py`

**Interfaces:**
- `StatisticsStore.record(result, price=None, execution_event=None)` accepts an optional execution event.
- `actionable_trades` counts only explicit execution events that reach `POSITION_OPEN`; decisions remain separately observable.

- [ ] **Step 1: Write failing statistics tests**

```python
def test_buy_decision_is_not_counted_as_trade():
    store = StatisticsStore()
    result = fake_result(decision="BUY", gate_passed=True)
    store.record(result)
    assert store.snapshot()["actionable_trades"] == 0


def test_position_open_is_counted_as_trade():
    store = StatisticsStore()
    result = fake_result(decision="BUY", gate_passed=True)
    store.record(result, execution_event={"state": "POSITION_OPEN", "execution_event": True})
    assert store.snapshot()["actionable_trades"] == 1
```

- [ ] **Step 2: Run tests to verify the old behavior fails**

Run: `pytest tests/test_production_v2_statistics.py -q`
Expected: first test fails because the current implementation counts E9 approval as a trade.

- [ ] **Step 3: Implement event-based trade counting**

Keep `decisions` incrementing on every pipeline evaluation. Increment `actionable_trades` only when `execution_event` is true and normalized execution state is `POSITION_OPEN`.

- [ ] **Step 4: Remove inferred execution from `_current_opportunity_input()`**

Replace `executed = bool(e9_decision in {"BUY","SELL"} and result.gate_passed)` with execution-state input from the execution boundary. An E9 BUY/SELL remains an authorization/decision only.

- [ ] **Step 5: Run statistics tests**

Run: `pytest tests/test_production_v2_statistics.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add production_v2/app.py production_v2/statistics.py tests/test_production_v2_statistics.py
git commit -m "fix: separate trade statistics from E9 decisions"
```

---

### Task 6: Harden E5 tradeability and preserve E2 evidence semantics

**Files:**
- Modify: `production_v2/e6_brain.py`
- Modify: `production_v2/e5_brain.py` if the current implementation exposes location classification there
- Modify: `production_v2/e2_brain.py` only where the current contract conflates unresolved evidence with hard veto
- Test: `tests/test_production_v2_opportunity_gates.py`

**Interfaces:**
- E2 continues to expose unresolved/developing evidence without manufacturing confirmation.
- E5 exposes location and space independently.
- E6 requires the existing minimum structural space and does not convert favorable location into trade readiness.

- [ ] **Step 1: Write failing semantic tests**

```python
def test_favorable_location_does_not_imply_tradeable():
    e5 = {"finding": "FAVORABLE_LOCATION", "available_space_atr_long": 0.35}
    assert is_tradeable_location(e5, "BUY") is False


def test_e2_unresolved_is_not_positive_confirmation():
    e2 = {"finding": "UNRESOLVED", "opportunity_state": "UNRESOLVED"}
    assert e2_confirmation_state(e2) != "CONFIRMED"
```

- [ ] **Step 2: Run focused gate tests**

Run: `pytest tests/test_production_v2_opportunity_gates.py -q`
Expected: FAIL until the semantic predicates are explicit.

- [ ] **Step 3: Implement explicit location/space predicates**

Use the existing E6 `MIN_SPACE_ATR = 0.75` as the structural floor; do not lower it. A favorable location may support a thesis but cannot satisfy tradeability alone.

- [ ] **Step 4: Preserve hard contradictions as vetoes**

Only explicit contradiction/invalidation codes become hard vetoes. `UNRESOLVED`, `DEVELOPING`, and `PENDING` remain non-confirming states that can keep a candidate in watch/wait mode.

- [ ] **Step 5: Run focused tests**

Run: `pytest tests/test_production_v2_opportunity_gates.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add production_v2/e2_brain.py production_v2/e5_brain.py production_v2/e6_brain.py tests/test_production_v2_opportunity_gates.py
git commit -m "fix: separate evidence, location, and tradeability"
```

---

### Task 7: Consolidate runtime wrappers and authority logging

**Files:**
- Modify: `production_v2/final_runtime_binding.py`
- Modify: `production_v2/e9_watch_boundary.py`
- Modify: `production_v2/e7_thesis_boundary.py`
- Modify: `production_v2/e8_applicability_boundary.py`
- Modify: `production_v2/evidence_collaboration_runtime.py`
- Modify: `production_v2/runtime_trace_boundary.py`
- Modify: `production_v2/__init__.py`
- Test: `tests/test_production_v2_runtime_binding.py`

**Interfaces:**
- E6/E8/E9 authority remains deterministic.
- Wrappers may validate/enrich but may not create competing lifecycle or decision state machines.

- [ ] **Step 1: Write a binding-order test**

```python
def test_runtime_binding_has_one_authoritative_run_entrypoint():
    import production_v2.pipeline as pipeline
    assert getattr(pipeline.ProductionPipeline.run, "__name__", "")
    # the test additionally records wrapper installation count and requires one lifecycle owner
```

- [ ] **Step 2: Run the binding test and inspect current wrapper chain**

Run: `pytest tests/test_production_v2_runtime_binding.py -q`
Expected: the test documents the current nested wrapper behavior before consolidation.

- [ ] **Step 3: Make authority installation idempotent**

Each boundary installer must mark its wrapper as installed and return without nesting a second copy. Preserve authoritative E6/E8/E9 bindings.

- [ ] **Step 4: Rename misleading pipeline stage logs**

Change `PIPELINE_STAGE ENTER E6_E7_E8_E9` to an accurate stage label indicating the actual E6-E9 section only when that section is entered, while retaining the full E1-E9 architecture string.

- [ ] **Step 5: Run runtime-binding tests**

Run: `pytest tests/test_production_v2_runtime_binding.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add production_v2/final_runtime_binding.py production_v2/e9_watch_boundary.py production_v2/e7_thesis_boundary.py production_v2/e8_applicability_boundary.py production_v2/evidence_collaboration_runtime.py production_v2/runtime_trace_boundary.py production_v2/__init__.py tests/test_production_v2_runtime_binding.py
git commit -m "fix: make production v2 runtime binding deterministic"
```

---

### Task 8: Add end-to-end closed-candle lifecycle verification

**Files:**
- Create: `tests/test_production_v2_e2e_lifecycle.py`
- Modify: `production_v2/pipeline.py` only if a missing test seam is required

**Interfaces:**
- Exercise the production lifecycle boundary with deterministic fixtures/mocks.
- Do not weaken real E1-E9 gates just to make the fixture pass.

- [ ] **Step 1: Write the full-path tests**

```python
def test_full_path_requires_e7_e8_before_e9_trade():
    watch = run_fixture("watch")
    assert watch.decision == "NO_TRADE"
    assert watch.risk["opportunity_lifecycle"]["state"] in {"WATCHING", "WAITING"}

    setup = run_fixture("confirmed_setup")
    assert setup.engines[5].output["setup_exists"] is True

    confirmed = run_fixture("e7_confirmed_e8_ready")
    assert confirmed.decision in {"BUY", "SELL"}
    assert confirmed.risk["opportunity_lifecycle"]["state"] == "READY"


def test_duplicate_closed_candle_is_idempotent():
    first = run_fixture("watch", candle="c1")
    second = run_fixture("watch", candle="c1")
    assert second.risk["opportunity_lifecycle"]["bars_waited"] == first.risk["opportunity_lifecycle"]["bars_waited"]


def test_e9_trade_does_not_equal_execution():
    result = run_fixture("e9_trade_no_execution")
    assert result.decision in {"BUY", "SELL"}
    assert result.risk["opportunity_lifecycle"]["state"] != "EXECUTED"
```

- [ ] **Step 2: Run E2E tests and fix fixture/setup issues without weakening production gates**

Run: `pytest tests/test_production_v2_e2e_lifecycle.py -q`
Expected: initial failures identify missing seams or semantic mismatches.

- [ ] **Step 3: Implement only the missing integration seams**

Fixtures must provide closed timestamps and explicit upstream outputs. Never use future candles to create a current decision.

- [ ] **Step 4: Run E2E tests**

Run: `pytest tests/test_production_v2_e2e_lifecycle.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_production_v2_e2e_lifecycle.py production_v2/pipeline.py
git commit -m "test: verify production v2 lifecycle end to end"
```

---

### Task 9: Full regression and deployment verification

**Files:**
- Modify: `docs/superpowers/plans/2026-09-05-production-v2-major-repair.md` only for checked-off completion notes if desired

- [ ] **Step 1: Run the complete test suite**

Run: `pytest -q`
Expected: PASS with no regressions in existing tests.

- [ ] **Step 2: Verify static contracts**

Run: `python -m compileall production_v2`
Expected: exit code 0 with no syntax errors.

- [ ] **Step 3: Verify the production health contract**

With persistent storage configured and healthy, `/health` must return HTTP 200 and expose `opportunity_memory_persistent=true`. With configured PostgreSQL unavailable, `/health` must return HTTP 503 rather than silently claiming healthy operation.

- [ ] **Step 4: Verify runtime logs on a closed candle**

Expected sequence includes one E1-E9 evaluation, one lifecycle transition, explicit E9 decision, and no `EXECUTED` lifecycle state unless an execution event reaches `POSITION_OPEN`.

- [ ] **Step 5: Verify duplicate candle behavior**

Submit the same closed candle twice and verify the second evaluation is skipped/idempotent without incrementing lifecycle age or execution counters twice.

- [ ] **Step 6: Verify no-lookahead invariant**

Confirm normalized market data still reports `closed_candle_only=true` and `lookahead_allowed=false` and that no future bar is consumed by E1-E9.

- [ ] **Step 7: Commit final verification changes**

```bash
git status
git add docs/superpowers/specs docs/superpowers/plans tests production_v2
git commit -m "chore: verify production v2 major repair"
```
