# Production-v2 Runtime Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `production-v2` a self-contained 9-Engine runtime with E1→E9 as the only production decision path and no V11/V12 dependency.

**Architecture:** The production entrypoint will live under `production_v2/` and call a deterministic nine-engine pipeline. Existing V11/V12 code remains archived but is not imported, scheduled, used as fallback, or used as a Telegram source. Telegram receives the E9 decision/result directly.

**Tech Stack:** Python 3.11, Flask, Gunicorn, pytest, existing market-data dependencies.

**Spec:** `Trading_System_Engine_Specs/PHASE_4_SPECIFICATION_v1.1.md` and `Trading_System_Engine_Specs/ENGINE_01_MARKET_STATE_ENGINE_v1.0.md` through `ENGINE_09_EXECUTION_DECISION_ENGINE_v1.0.md`.

## Global Constraints

- Production decision flow is exactly `Market Data → E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9`.
- E9 is the sole final decision authority.
- Production-v2 must not import, execute, schedule, or fall back to V11/V12.
- Telegram is presentation only and must consume E9 output.
- Legacy V11/V12 code may remain archived but is outside the production execution path.
- CI must validate legacy isolation, API contracts, and E1→E9 integration.

---

### Task 1: Define the new runtime boundary

**Files:**
- Create: `production_v2/__init__.py`
- Create: `production_v2/contracts.py`
- Create: `production_v2/pipeline.py`
- Test: `tests/test_production_v2_runtime_isolation.py`

**Interfaces:**
- `DecisionResult` carries symbol, timeframe, decision, gate state, engine trace, risk data, and reason codes.
- `ProductionPipeline.run(market_data)` executes E1 through E9 in order.

- [ ] Write isolation tests that fail if production_v2 imports legacy modules.
- [ ] Write pipeline ordering and E9-authority tests.
- [ ] Implement contracts and pipeline boundary.
- [ ] Run focused tests.

### Task 2: Implement the nine engine adapters

**Files:**
- Create/Modify: `production_v2/engines/e1.py` through `production_v2/engines/e9.py`
- Test: `tests/test_production_v2_engine_pipeline.py`

**Interfaces:**
- Each engine exposes `run(context) -> EngineResult`.
- Each engine receives only approved upstream context and returns structured output.
- A failed gate stops downstream processing.

- [ ] Write engine contract tests for E1→E9.
- [ ] Implement E1–E9 adapters against the approved Phase 4 contracts.
- [ ] Verify no engine performs order placement directly.
- [ ] Run focused integration tests.

### Task 3: Build independent production data/API runtime

**Files:**
- Create: `production_v2/app.py`
- Create: `production_v2/market_data.py`
- Test: `tests/test_production_v2_api.py`

**Interfaces:**
- `GET /` reports production-v2 and E1→E9 architecture.
- `GET /health` reports runtime health and `legacy_runtime=false`.
- `GET /signal` invokes only the new pipeline.

- [ ] Write API tests that assert no V11/V12 architecture appears.
- [ ] Implement market-data input normalization.
- [ ] Implement Flask endpoints.
- [ ] Run API tests.

### Task 4: Connect Telegram directly to E9

**Files:**
- Create/Modify: `production_v2/notifications/telegram.py`
- Test: `tests/test_production_v2_telegram.py`

**Interfaces:**
- Telegram formatter consumes `DecisionResult` only.
- Startup, status, decision, rejection, and error notifications use the new schema.

- [ ] Write Telegram contract tests.
- [ ] Implement E9-only formatting.
- [ ] Assert legacy architecture strings never appear.
- [ ] Run notification tests.

### Task 5: Make Render use the new runtime

**Files:**
- Create/Modify: `render.yaml`
- Modify: `.github/workflows/production-v2-tests.yml`
- Test: `tests/test_render_runtime.py`

**Interfaces:**
- Render start command targets `production_v2.app:app`.
- Health check targets `/health`.
- CI validates the Render command and production entrypoint.

- [ ] Write deployment configuration tests.
- [ ] Configure Render for Python 3.11 and Gunicorn.
- [ ] Ensure CI uses Node-24-compatible GitHub Actions.
- [ ] Run the full production-v2 test suite.

### Task 6: Archive legacy execution paths and verify isolation

**Files:**
- Modify: `.github/workflows/*` only where legacy workflows could execute against `production-v2`.
- Create: `tests/test_no_legacy_runtime_dependency.py`
- Create: `LEGACY_ARCHITECTURE.md`

- [ ] Identify workflows that must not gate or execute production-v2.
- [ ] Disable/remove only legacy workflow triggers that execute on `production-v2`.
- [ ] Add static import checks for V11/V12 names in production_v2.
- [ ] Run the complete suite.

### Task 7: Verification and deployment gate

- [ ] Run all production-v2 tests.
- [ ] Confirm CI is green with no Node 20 warning.
- [ ] Confirm the production entrypoint imports without V11/V12.
- [ ] Confirm `/health` reports `legacy_runtime=false`.
- [ ] Deploy Render only after all checks pass.
- [ ] Verify production health and Telegram startup message.
