from __future__ import annotations

from typing import Any

from .contracts import DecisionResult, EngineResult
from .engines import run_e9_decision, run_engine


WAIT_MAX_BARS = 3

# A WAIT is appropriate only when evidence is incomplete but still recoverable.
# Structural invalidation, bad risk, or failed execution conditions are hard FAILs.
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


def resolve_engine_state(
    gate_passed: bool,
    reason_codes: tuple[str, ...] = (),
    *,
    wait_bars: int = 0,
    score: float | None = None,
) -> str:
    """Resolve PASS / WAIT / FAIL without using score as a decision override."""
    if gate_passed:
        return "PASS"
    if wait_bars >= WAIT_MAX_BARS:
        return "FAIL"
    if any(reason in HARD_FAIL_REASONS for reason in reason_codes):
        return "FAIL"
    return "WAIT" if reason_codes else "FAIL"


class ProductionPipeline:
    """Professional decision path: E1 -> E2 -> ... -> E9.

    PASS means evidence is sufficient. WAIT means the setup is incomplete but
    still actionable if the next closed M5 candles confirm it. FAIL means the
    thesis is invalid or risk/execution is unacceptable. No score can turn a
    WAIT/FAIL into a PASS.
    """

    ENGINE_ORDER = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8")

    def run(self, market_data: dict[str, Any], *, wait_bars: int = 0) -> DecisionResult:
        symbol = str(market_data.get("symbol") or "UNKNOWN")
        timeframe = str(market_data.get("timeframe") or "M5")
        context = dict(market_data)
        engines: list[EngineResult] = []

        for engine_id in self.ENGINE_ORDER:
            result = run_engine(engine_id, context)
            engines.append(result)
            context[f"{engine_id}_result"] = result.output
            if not result.gate_passed:
                state = resolve_engine_state(result.gate_passed, result.reason_codes, wait_bars=wait_bars, score=result.score)
                decision = "WAIT" if state == "WAIT" else "NO_TRADE"
                reason = f"{engine_id}_WAITING_FOR_CONFIRMATION" if state == "WAIT" else f"{engine_id}_GATE_FAILED"
                e9 = EngineResult(
                    "E9", "Execution Decision Engine", False, result.score,
                    {
                        "decision": decision,
                        "decision_authority": "E9",
                        "blocked_by": engine_id,
                        "engine_state": state,
                        "wait_bars": wait_bars,
                        "wait_max_bars": WAIT_MAX_BARS,
                        "trade_plan": context.get("E8_result", {}).get("trade_plan", {}),
                    },
                    (reason,),
                )
                engines.append(e9)
                return DecisionResult(
                    symbol, timeframe, decision, False, result.score,
                    tuple(engines),
                    {
                        "risk_gate": False,
                        "trade_plan": context.get("E8_result", {}).get("trade_plan", {}),
                        "engine_state": state,
                        "wait_bars": wait_bars,
                        "wait_max_bars": WAIT_MAX_BARS,
                    },
                    (reason,),
                )

        e9 = run_e9_decision(context, engines)
        engines.append(e9)
        decision = e9.output.get("decision", "NO_TRADE")
        trade_plan = e9.output.get("trade_plan", {})
        return DecisionResult(
            symbol, timeframe, decision, e9.gate_passed,
            e9.score,
            tuple(engines),
            {
                "risk_gate": next(e.gate_passed for e in engines if e.engine_id == "E8"),
                "trade_plan": trade_plan,
                "engine_state": "PASS" if e9.gate_passed else "FAIL",
                "wait_bars": 0,
                "wait_max_bars": WAIT_MAX_BARS,
            },
            tuple(e9.reason_codes),
        )
