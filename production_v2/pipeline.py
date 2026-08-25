from __future__ import annotations

from typing import Any

from .contracts import DecisionResult, EngineResult
from .engines import run_e9_decision, run_engine


# WAIT is not time-based. It ends when the missing evidence appears or the
# thesis becomes invalid. A professional setup is allowed to remain valid
# across any number of closed M5 candles while its structure is intact.
WAIT_MAX_BARS = None

# These are conditions a discretionary professional would normally abandon
# immediately rather than "wait" for. Scores never override these decisions.
HARD_FAIL_REASONS = {
    "E1_MARKET_STATE_TRANSITION",
    "E3_STRUCTURE_NOT_CONFIRMED",
    "E4_LIQUIDITY_EVIDENCE_INSUFFICIENT",
    "E5_LOCATION_DISADVANTAGED",
    "E6_SETUP_NOT_MATURE",
    "E6_SETUP_NOT_DIRECTIONAL",
    "E7_CONFIRMATION_INVALIDATED",
    "E8_RISK_PLAN_INVALID",
    "E8_RISK_GATE_NOT_READY",
    "E8_RR_BELOW_MINIMUM",
}

ENGINE_ORDER = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8")
ENGINE_INDEX = {engine_id: i for i, engine_id in enumerate(ENGINE_ORDER)}


def resolve_engine_state(
    gate_passed: bool,
    reason_codes: tuple[str, ...] = (),
    *,
    wait_bars: int = 0,
    score: float | None = None,
) -> str:
    """Resolve PASS / WAIT / FAIL. Score is informational only."""
    if gate_passed:
        return "PASS"
    if any(reason in HARD_FAIL_REASONS for reason in reason_codes):
        return "FAIL"
    return "WAIT" if reason_codes else "FAIL"


def resume_from_wait(waiting_engine: str, *, structure_changed: bool) -> str:
    """Return the first engine that must be recomputed after a WAIT.

    Before E3 there is no established structural thesis to preserve. Once the
    pipeline has reached E4+, unchanged structure lets us resume exactly at the
    waiting engine. A structural change invalidates the downstream thesis and
    reopens the decision from E3, while deliberately preserving E1/E2.
    """
    if waiting_engine not in ENGINE_INDEX:
        raise ValueError(f"unknown waiting engine: {waiting_engine}")
    if structure_changed and ENGINE_INDEX[waiting_engine] >= ENGINE_INDEX["E4"]:
        return "E3"
    return waiting_engine


def _structure_signature(result: EngineResult | None) -> tuple[Any, ...] | None:
    if result is None:
        return None
    output = result.output or {}
    return (
        output.get("3B", {}).get("state"),
        output.get("3C", {}).get("state"),
        output.get("3F", {}).get("state"),
        output.get("3B", {}).get("direction"),
        output.get("3F", {}).get("direction"),
    )


class ProductionPipeline:
    """Professional decision path: E1 -> E2 -> ... -> E9.

    PASS means evidence is sufficient. WAIT means the thesis is still valid but
    one missing condition must appear. FAIL means the thesis/risk is invalid.
    A WAIT resumes from the waiting engine; E1/E2/E3 are reused unless E3 is
    being monitored and its structural signature has changed.
    """

    ENGINE_ORDER = ENGINE_ORDER

    def _blocked_result(
        self,
        symbol: str,
        timeframe: str,
        result: EngineResult,
        context: dict[str, Any],
        wait_bars: int,
        engines: list[EngineResult],
    ) -> DecisionResult:
        state = resolve_engine_state(
            result.gate_passed,
            result.reason_codes,
            wait_bars=wait_bars,
            score=result.score,
        )
        decision = "WAIT" if state == "WAIT" else "NO_TRADE"
        reason = (
            f"{result.engine_id}_WAITING_FOR_CONFIRMATION"
            if state == "WAIT"
            else f"{result.engine_id}_GATE_FAILED"
        )
        e9 = EngineResult(
            "E9",
            "Execution Decision Engine",
            False,
            result.score,
            {
                "decision": decision,
                "decision_authority": "E9",
                "blocked_by": result.engine_id,
                "engine_state": state,
                "wait_bars": wait_bars,
                "wait_max_bars": None,
                "trade_plan": context.get("E8_result", {}).get("trade_plan", {}),
            },
            (reason,),
        )
        engines.append(e9)
        return DecisionResult(
            symbol,
            timeframe,
            decision,
            False,
            result.score,
            tuple(engines),
            {
                "risk_gate": False,
                "trade_plan": context.get("E8_result", {}).get("trade_plan", {}),
                "engine_state": state,
                "blocked_by": result.engine_id,
                "wait_bars": wait_bars,
                "wait_max_bars": None,
            },
            (reason,),
        )

    def _run_from(
        self,
        market_data: dict[str, Any],
        *,
        start_engine: str,
        engines: list[EngineResult],
        wait_bars: int,
    ) -> DecisionResult:
        symbol = str(market_data.get("symbol") or "UNKNOWN")
        timeframe = str(market_data.get("timeframe") or "M5")
        context = dict(market_data)
        start_index = ENGINE_INDEX[start_engine]

        # Cached upstream results are trusted because the resume policy has
        # already decided that they are still valid for this candle.
        for cached in engines:
            context[f"{cached.engine_id}_result"] = cached.output

        for engine_id in ENGINE_ORDER[start_index:]:
            result = run_engine(engine_id, context)
            # Replace any stale cached copy of this engine.
            engines[:] = [e for e in engines if e.engine_id != engine_id]
            engines.append(result)
            context[f"{engine_id}_result"] = result.output
            if not result.gate_passed:
                return self._blocked_result(
                    symbol, timeframe, result, context, wait_bars, engines
                )

        e9 = run_e9_decision(context, engines)
        engines[:] = [e for e in engines if e.engine_id != "E9"]
        engines.append(e9)
        decision = e9.output.get("decision", "NO_TRADE")
        trade_plan = e9.output.get("trade_plan", {})
        return DecisionResult(
            symbol,
            timeframe,
            decision,
            e9.gate_passed,
            e9.score,
            tuple(engines),
            {
                "risk_gate": next(e.gate_passed for e in engines if e.engine_id == "E8"),
                "trade_plan": trade_plan,
                "engine_state": "PASS" if e9.gate_passed else "FAIL",
                "wait_bars": 0,
                "wait_max_bars": None,
            },
            tuple(e9.reason_codes),
        )

    def run(
        self,
        market_data: dict[str, Any],
        *,
        wait_bars: int = 0,
        resume_state: dict[str, Any] | None = None,
    ) -> DecisionResult:
        if not resume_state:
            return self._run_from(
                market_data,
                start_engine="E1",
                engines=[],
                wait_bars=wait_bars,
            )

        cached = list(resume_state.get("engines") or [])
        waiting_engine = str(resume_state.get("waiting_engine") or "E1")
        structure_changed = False

        if ENGINE_INDEX.get(waiting_engine, 0) >= ENGINE_INDEX["E4"]:
            cached_e3 = next((e for e in cached if e.engine_id == "E3"), None)
            current_e3 = run_engine("E3", dict(market_data))
            structure_changed = _structure_signature(current_e3) != _structure_signature(cached_e3)
            if not current_e3.gate_passed:
                structure_changed = True
            if structure_changed:
                cached = [e for e in cached if e.engine_id in {"E1", "E2"}]
                cached.append(current_e3)
            else:
                cached = [e for e in cached if e.engine_id != "E9"]

        start_engine = resume_from_wait(
            waiting_engine,
            structure_changed=structure_changed,
        )
        cached = [
            e for e in cached
            if e.engine_id in ENGINE_ORDER[: ENGINE_INDEX[start_engine]]
        ]
        return self._run_from(
            market_data,
            start_engine=start_engine,
            engines=cached,
            wait_bars=wait_bars,
        )
