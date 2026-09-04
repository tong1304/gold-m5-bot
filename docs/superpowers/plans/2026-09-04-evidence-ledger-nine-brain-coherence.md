# Evidence Ledger Nine-Brain Coherence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make E1-E8 collaborate through a shared evidence/claim contract so E9 reconciles specialist disagreement into BUY/SELL/WAIT/NO_TRADE without treating ordinary disagreement as automatic veto.

**Architecture:** Keep the existing closed-candle `shared_market_picture` as immutable fact truth. Add a typed, non-authoritative Evidence Ledger carrying each brain's role-scoped evidence, interpretation, support, counter-evidence, proof state, and invalidation state; then make E9 consume that ledger through explicit conflict severity and thesis-survival rules. E6 remains thesis owner, E7 remains confirmation owner, E8 remains economics owner, and E9 remains the only final decision authority.

**Tech Stack:** Python 3, existing `EngineResult` contracts, pytest, GitHub Actions, production_v2 runtime wrappers.

**Spec:** `docs/superpowers/specs/2026-09-03-mtf-nine-engine-coherence-design.md`

## Global Constraints

- M15 is context/regime; M5 is setup/entry.
- E1-E5 own market evidence and specialist interpretation only.
- E6 owns causal trade thesis; E7 cannot create a thesis; E8 cannot create a thesis.
- E9 alone owns final BUY/SELL/WAIT/NO_TRADE decision.
- `NO_THESIS` is not equivalent to `NO_OPPORTUNITY`.
- `OPPORTUNITY_WATCH` is not a trade setup and must persist until promoted or invalidated.
- All analysis uses closed candles only; no lookahead.
- Do not lower score/RR/quality gates to increase signal count.
- Re-entry for the same setup remains allowed.
- Hard invalidation, invalid trigger, or non-survivable economics can block execution; ordinary specialist disagreement is not an automatic veto.
- Existing E6/E7/E8/E9 authority membranes must remain intact.

---

### Task 1: Define the shared Evidence Ledger contract

**Files:**
- Create: `production_v2/evidence_ledger.py`
- Test: `tests/test_evidence_ledger_contract.py`

**Interfaces:**
- Consumes: `dict[str, EngineResult]`, existing `shared_market_picture`, existing engine outputs.
- Produces: `build_evidence_ledger(results) -> dict[str, Any]`, `classify_conflict(...) -> str`, `ledger_for_e9(results) -> dict[str, Any]`.

- [ ] **Step 1: Write the failing tests**

```python
from production_v2.contracts import EngineResult
from production_v2.evidence_ledger import build_evidence_ledger, classify_conflict


def result(engine_id, output):
    return EngineResult(engine_id, engine_id, output.get("gate_passed"), 0.0, output, tuple(output.get("reason_codes", ())))


def test_ledger_keeps_specialist_roles_and_does_not_make_a_decision():
    results = {
        "E1": result("E1", {"direction": "SELL", "finding": "BEARISH REGIME"}),
        "E3": result("E3", {"direction": "BUY", "finding": "BULLISH STRUCTURE"}),
        "E6": result("E6", {"direction": "SELL", "setup": "OPPORTUNITY_WATCH", "watch_only": True}),
    }
    ledger = build_evidence_ledger(results)
    assert ledger["authority"] == "NON_AUTHORITATIVE"
    assert ledger["decision_authority"] == "E9_ONLY"
    assert ledger["brains"]["E1"]["role"] == "MARKET_STATE"
    assert ledger["brains"]["E3"]["role"] == "MARKET_STRUCTURE"
    assert ledger["brains"]["E6"]["role"] == "SETUP_FORMATION"
    assert "decision" not in ledger


def test_soft_disagreement_is_not_a_blocking_conflict():
    assert classify_conflict("COUNTER_EVIDENCE", confirmed=False, invalidating=False) == "SOFT"


def test_confirmed_invalidation_is_hard():
    assert classify_conflict("THESIS_INVALIDATION", confirmed=True, invalidating=True) == "HARD"
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `python -m pytest -q tests/test_evidence_ledger_contract.py`
Expected: FAIL because `production_v2.evidence_ledger` does not yet provide the contract.

- [ ] **Step 3: Implement the minimal contract**

```python
ROLE = {
    "E1": "MARKET_STATE",
    "E2": "OPPORTUNITY_REGIME",
    "E3": "MARKET_STRUCTURE",
    "E4": "LIQUIDITY_AUCTION",
    "E5": "LOCATION_VALUE",
    "E6": "SETUP_FORMATION",
    "E7": "CONFIRMATION",
    "E8": "TRADE_ECONOMICS_RISK",
}


def classify_conflict(code, *, confirmed=False, invalidating=False):
    if invalidating and confirmed:
        return "HARD"
    if confirmed:
        return "CONFIRMED"
    return "SOFT"


def build_evidence_ledger(results):
    brains = {}
    for engine_id, engine in results.items():
        if engine_id == "E9":
            continue
        output = dict(engine.output or {})
        brains[engine_id] = {
            "role": ROLE.get(engine_id, "SPECIALIST"),
            "direction": output.get("direction") or output.get("direction_thesis") or output.get("opportunity_direction"),
            "interpretation": output.get("finding"),
            "supporting_evidence": output.get("observations") or output.get("evidence") or [],
            "counter_evidence": output.get("counter_evidence") or [],
            "missing_evidence": output.get("missing_evidence") or output.get("missing_proof") or [],
            "proof_state": output.get("confirmation_state") or output.get("proof_state") or output.get("state"),
            "invalidations": output.get("active_invalidations") or output.get("invalidations") or [],
        }
    return {
        "schema": "EVIDENCE_LEDGER_V1",
        "authority": "NON_AUTHORITATIVE",
        "decision_authority": "E9_ONLY",
        "principle": "SPECIALISTS_SHARE_EVIDENCE;_E9_RECONCILES_DECISION",
        "brains": brains,
        "decision": None,
    }


def ledger_for_e9(results):
    ledger = build_evidence_ledger(results)
    ledger["decision"] = None
    return ledger
```

- [ ] **Step 4: Run the focused test and verify it passes**

Run: `python -m pytest -q tests/test_evidence_ledger_contract.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add production_v2/evidence_ledger.py tests/test_evidence_ledger_contract.py
git commit -m "feat: add shared evidence ledger contract"
```

### Task 2: Connect the existing conflict ledger to the new evidence ledger

**Files:**
- Modify: `production_v2/conflict_resolution.py`
- Modify: `production_v2/pipeline.py`
- Test: `tests/test_cross_brain_reconciliation.py`

**Interfaces:**
- Consumes: `build_conflict_ledger(results)`, `build_evidence_ledger(results)`.
- Produces: `cross_brain_conflicts` containing severity plus `supporting`, `counter_evidence`, `hard_invalidations`, and `resolution_policy`.

- [ ] **Step 1: Write the failing tests**

```python
from production_v2.conflict_resolution import build_conflict_ledger
from production_v2.contracts import EngineResult


def r(engine_id, output):
    return EngineResult(engine_id, engine_id, output.get("gate_passed"), 0.0, output, tuple())


def test_counterflow_pending_is_tension_not_veto():
    results = {
        "E1": r("E1", {"direction": "SELL"}),
        "E3": r("E3", {"direction": "SELL"}),
        "E5": r("E5", {"value_state": "PREMIUM", "available_space_atr_short": 1.4}),
        "E6": r("E6", {"direction": "SELL", "setup_state": "MATURE"}),
        "E7": r("E7", {"confirmation_state": "PENDING", "counter_evidence": ["BUY_SWEEP_PENDING"]}),
        "E8": r("E8", {"economic_state": "READY"}),
    }
    ledger = build_conflict_ledger(results)
    assert ledger["summary"]["blocking_conflicts"] == 0
    assert any(x["severity"] == "MEDIUM" for x in ledger["conflicts"])


def test_confirmed_thesis_invalidation_is_blocking():
    results = {
        "E1": r("E1", {"direction": "SELL"}),
        "E3": r("E3", {"direction": "BUY", "active_invalidations": ["THESIS_INVALIDATION"]}),
        "E5": r("E5", {"available_space_atr_short": 1.2}),
        "E6": r("E6", {"direction": "SELL", "setup_state": "MATURE"}),
        "E7": r("E7", {"confirmation_state": "CONFIRMED"}),
        "E8": r("E8", {"economic_state": "READY"}),
    }
    ledger = build_conflict_ledger(results)
    assert any(x["severity"] == "HIGH" for x in ledger["conflicts"])
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `python -m pytest -q tests/test_cross_brain_reconciliation.py`
Expected: FAIL because the current conflict ledger does not distinguish pending counter-evidence from confirmed invalidation.

- [ ] **Step 3: Implement severity using proof state and invalidation state**

Add a helper in `production_v2/conflict_resolution.py` that preserves existing conflict codes but derives severity from evidence state:

```python
def _severity(*, confirmed: bool, invalidating: bool, pending: bool) -> str:
    if confirmed and invalidating:
        return "HIGH"
    if pending or not confirmed:
        return "MEDIUM"
    return "LOW"
```

Use it for counter-evidence and thesis invalidation only; do not downgrade existing genuine E8 economic blockers or explicit structural invalidations. Add `resolution_policy` to every conflict with one of `OBSERVE`, `WAIT_FOR_CONFIRMATION`, or `BLOCK_EXECUTION`.

In `pipeline.py`, construct the evidence ledger before conflict attachment and expose both without allowing either to rewrite upstream engine outputs:

```python
from .evidence_ledger import build_evidence_ledger

...
evidence_ledger = build_evidence_ledger(results)
conflict_ledger = _ensure_cross_brain_conflict_visibility(
    results, build_conflict_ledger(results)
)
snapshot["evidence_ledger"] = evidence_ledger
snapshot["cross_brain_conflicts"] = conflict_ledger
_attach_conflict_ledger(results, conflict_ledger)
```

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `python -m pytest -q tests/test_cross_brain_reconciliation.py tests/test_evidence_ledger_contract.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add production_v2/conflict_resolution.py production_v2/pipeline.py tests/test_cross_brain_reconciliation.py
git commit -m "feat: classify cross-brain conflicts by proof state"
```

### Task 3: Make E9 reconcile evidence instead of treating disagreement as veto

**Files:**
- Modify: `production_v2/e9_brain.py`
- Modify: `production_v2/e9_watch_boundary.py` only if required to preserve watch semantics
- Test: `tests/test_e9_evidence_reconciliation.py`

**Interfaces:**
- Consumes: E1-E8 outputs, `snapshot["evidence_ledger"]`, `snapshot["cross_brain_conflicts"]`.
- Produces: final E9 decision plus `decision_basis`, `supporting_brains`, `counter_evidence`, `blocking_evidence`, `thesis_survival`, and `resolution_mode`.

- [ ] **Step 1: Write failing tests for the three decision modes**

```python
def test_e9_executes_when_thesis_trigger_and_economics_align():
    # E1-E8: SELL thesis survives, E7 confirmed, E8 ready, one soft BUY counter-event.
    result = analyze_fixture("SELL_CONFIRMED_WITH_SOFT_COUNTERFLOW")
    assert result.output["decision"] == "SELL"
    assert result.output["resolution_mode"] == "RECONCILE_AND_EXECUTE"
    assert result.output["thesis_survival"] == "SURVIVES"


def test_e9_waits_when_thesis_survives_but_trigger_is_pending():
    result = analyze_fixture("SELL_THESIS_TRIGGER_PENDING")
    assert result.output["decision"] == "WAIT"
    assert result.output["resolution_mode"] == "WAIT_FOR_MISSING_PROOF"
    assert result.output["next_required_event"] == "NEXT_CLOSED_M5_CANDLE"


def test_e9_blocks_when_thesis_is_confirmedly_invalidated():
    result = analyze_fixture("SELL_THESIS_INVALIDATED_BY_CONFIRMED_STRUCTURE")
    assert result.output["decision"] == "NO_TRADE"
    assert result.output["resolution_mode"] == "BLOCK_INVALIDATED_THESIS"
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `python -m pytest -q tests/test_e9_evidence_reconciliation.py`
Expected: FAIL because E9 does not yet expose these reconciliation semantics.

- [ ] **Step 3: Implement a pure E9 reconciliation function**

Add a pure helper with no market-data mutation:

```python
def reconcile_evidence(*, e6, e7, e8, conflicts, evidence_ledger):
    thesis_alive = bool(e6.get("setup")) and not bool(e6.get("active_invalidations")) and not e6.get("watch_only")
    trigger_confirmed = str(e7.get("confirmation_state") or e7.get("confirmation") or "").upper() in {"CONFIRMED", "VALIDATED", "TRIGGERED", "READY"}
    economics_ready = str(e8.get("economic_state") or e8.get("risk_state") or "").upper() in {"READY", "VIABLE", "PASS", "TRADE_READY"}
    hard = [c for c in conflicts.get("conflicts", []) if c.get("severity") == "HIGH" and c.get("resolution_policy") == "BLOCK_EXECUTION"]
    direction = str(e6.get("direction") or e6.get("direction_thesis") or "").upper()
    if hard or not thesis_alive:
        return "NO_TRADE", "BLOCK_INVALIDATED_THESIS"
    if not trigger_confirmed or not economics_ready:
        return "WAIT", "WAIT_FOR_MISSING_PROOF"
    if direction not in {"BUY", "SELL"}:
        return "NO_TRADE", "NO_SURVIVING_DIRECTIONAL_THESIS"
    return direction, "RECONCILE_AND_EXECUTE"
```

The production implementation must preserve existing E9 hard governance checks and watch-boundary behavior; the helper is only the reconciliation layer. Add `decision_basis` fields from the ledger rather than rewriting E1-E8 outputs.

- [ ] **Step 4: Run focused E9 and existing authority tests**

Run: `python -m pytest -q tests/test_e9_evidence_reconciliation.py tests/test_e7_concrete_thesis_boundary.py tests/test_e8_applicability_boundary.py tests/test_final_runtime_binding.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add production_v2/e9_brain.py production_v2/e9_watch_boundary.py tests/test_e9_evidence_reconciliation.py
git commit -m "feat: make E9 reconcile specialist evidence"
```

### Task 4: Preserve opportunity lifecycle semantics and verify the full runtime path

**Files:**
- Modify: `production_v2/app.py` only where lifecycle state drops the evidence-ledger/watch identity.
- Modify: `production_v2/opportunity_lifecycle.py` only where a surviving opportunity is reset because a specialist disagrees.
- Modify: `.github/workflows/production-v2-tests.yml`
- Test: `tests/test_evidence_ledger_lifecycle.py`

**Interfaces:**
- Consumes: E2/E6 watch state, evidence ledger, opportunity ID, closed-candle identity.
- Produces: persistent `opportunity_id`, `WAITING`/`WATCHING` continuity, promotion to READY only after E7/E8, invalidation only on explicit hard invalidation.

- [ ] **Step 1: Write lifecycle regression tests**

```python
def test_pending_counter_evidence_preserves_opportunity_identity():
    first = advance_fixture("SELL_WATCH", candle_id="c1")
    second = advance_fixture("SELL_WATCH_COUNTERFLOW_PENDING", candle_id="c2", previous=first)
    assert second["opportunity_id"] == first["opportunity_id"]
    assert second["continuity"] == "PRESERVED_EXISTING_OPPORTUNITY"
    assert second["state"] in {"WAITING", "WATCHING"}


def test_confirmed_invalidation_closes_opportunity():
    first = advance_fixture("SELL_WATCH", candle_id="c1")
    second = advance_fixture("SELL_INVALIDATED", candle_id="c2", previous=first)
    assert second["state"] == "IDLE"
    assert second["continuity"] == "INVALIDATED"
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest -q tests/test_evidence_ledger_lifecycle.py`
Expected: FAIL if a specialist disagreement currently resets the opportunity identity.

- [ ] **Step 3: Implement the minimal lifecycle fix**

Preserve the existing `opportunity_lifecycle.advance_opportunity()` state machine. Only treat a new evidence-ledger conflict as invalidating when it contains a confirmed hard invalidation. Do not reset on `SOFT`, `MEDIUM`, `PENDING`, `COUNTER_EVIDENCE`, or `WAIT_FOR_CONFIRMATION`.

Keep `NEXT_CLOSED_M5_CANDLE` as the next event for unresolved confirmation and retain the existing opportunity ID.

- [ ] **Step 4: Add the focused tests to CI**

```yaml
- name: Run evidence-ledger and E9 reconciliation regressions
  run: >-
    python -m pytest -q
    tests/test_evidence_ledger_contract.py
    tests/test_cross_brain_reconciliation.py
    tests/test_e9_evidence_reconciliation.py
    tests/test_evidence_ledger_lifecycle.py
```

- [ ] **Step 5: Run verification**

Run locally/CI:

```bash
python -m pytest -q \
  tests/test_evidence_ledger_contract.py \
  tests/test_cross_brain_reconciliation.py \
  tests/test_e9_evidence_reconciliation.py \
  tests/test_evidence_ledger_lifecycle.py \
  tests/test_e7_concrete_thesis_boundary.py \
  tests/test_e8_applicability_boundary.py \
  tests/test_final_runtime_binding.py
```

Expected: all listed tests PASS. Separately report any pre-existing E1 Professional Test Matrix failure; do not label the entire suite green unless every required CI job passes.

- [ ] **Step 6: Verify production behavior on two consecutive closed M5 candles**

Expected first candle:

```text
continuity=NEW_DEVELOPING_OPPORTUNITY
```

Expected next candle when evidence survives:

```text
continuity=PRESERVED_EXISTING_OPPORTUNITY
bars_waited=1
opportunity_id=<same id>
next=NEXT_CLOSED_M5_CANDLE
```

Expected when hard invalidation occurs:

```text
continuity=INVALIDATED
state=IDLE
```

- [ ] **Step 7: Commit**

```bash
git add production_v2/app.py production_v2/opportunity_lifecycle.py .github/workflows/production-v2-tests.yml tests/test_evidence_ledger_lifecycle.py
git commit -m "test: verify evidence-ledger lifecycle continuity"
```

## Verification Checklist

- [ ] E1-E8 outputs remain specialist-owned; no engine rewrites another engine's facts.
- [ ] Shared closed-candle snapshot remains immutable and lookahead-free.
- [ ] Pending counter-evidence is represented as tension, not automatic veto.
- [ ] Confirmed thesis invalidation is a hard blocker.
- [ ] E6 remains the only thesis owner.
- [ ] E7 cannot create a thesis.
- [ ] E8 cannot create a thesis and remains non-applicable without a surviving E6 thesis.
- [ ] E9 can execute a coherent setup despite non-invalidating specialist disagreement.
- [ ] E9 waits when thesis survives but trigger/economics are not ready.
- [ ] E9 blocks when the thesis is explicitly invalidated or economics are genuinely non-survivable.
- [ ] Opportunity ID persists across a surviving next candle.
- [ ] No score/RR threshold is weakened to increase trade frequency.
- [ ] Full CI status is reported honestly, including any unrelated pre-existing failures.
