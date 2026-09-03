from __future__ import annotations
from typing import Any
from .contracts import EngineResult


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _direction(value: Any) -> str:
    text = _text(value)
    if text in {"BUY", "BULLISH", "UP", "LONG", "BUYERS", "TREND_UP"}:
        return "BUY"
    if text in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS", "TREND_DOWN"}:
        return "SELL"
    return "NEUTRAL"


def _out(result: Any) -> dict[str, Any]:
    return dict(getattr(result, "output", {}) or {})


def _infer_e4_direction(e4: dict[str, Any]) -> str:
    """Infer pending auction response direction from explicit actor fields when direction is absent."""
    direction = _direction(e4.get("direction"))
    if direction != "NEUTRAL":
        return direction

    actor = _direction(e4.get("response_actor"))
    if actor != "NEUTRAL":
        return actor

    taker = _direction(e4.get("liquidity_taker"))
    event = _text(e4.get("event", e4.get("finding")))
    if taker != "NEUTRAL" and "LIQUIDITY_INTERACTION" in event:
        return taker

    if "LOW_SWEEP_REJECTION" in event or "LOW_REJECTION" in event:
        return "BUY"
    if "HIGH_SWEEP_REJECTION" in event or "HIGH_REJECTION" in event:
        return "SELL"
    if "LOW_ACCEPTANCE" in event or "LOW_BREAK" in event:
        return "SELL"
    if "HIGH_ACCEPTANCE" in event or "HIGH_BREAK" in event:
        return "BUY"
    return "NEUTRAL"


def _pending_counterflow(upstream: dict[str, EngineResult]) -> bool:
    e1, e3, e4 = _out(upstream.get("E1")), _out(upstream.get("E3")), _out(upstream.get("E4"))
    pressure = _direction(e1.get("directional_pressure", e1.get("pressure", e1.get("direction"))))
    external = _direction(e3.get("external_state", e3.get("direction")))
    auction = _text(e4.get("auction_state", e4.get("state")))
    event = _text(e4.get("event", e4.get("finding")))
    auction_direction = _infer_e4_direction(e4)
    if auction not in {"PENDING", "DEVELOPING", "FORMING"}:
        return False
    if pressure not in {"BUY", "SELL"}:
        return False
    if external in {"BUY", "SELL"} and external != pressure:
        return False
    if auction_direction not in {"BUY", "SELL"} or auction_direction == pressure:
        return False
    return any(token in event for token in ("SWEEP", "REJECTION", "FAILED_BREAK", "LIQUIDITY_INTERACTION"))


def install(e6_module) -> None:
    if getattr(e6_module, "_E6_PENDING_COUNTERFLOW_RUNTIME_INSTALLED", False):
        return
    original_causal = e6_module._causal_opportunity

    def causal_with_pending_counterflow(upstream):
        if not _pending_counterflow(upstream):
            return original_causal(upstream)
        adjusted = dict(upstream)
        e4 = adjusted.get("E4")
        if e4 is None:
            return original_causal(upstream)
        e4_output = dict(_out(e4))
        e4_output["direction"] = "NEUTRAL"
        adjusted["E4"] = EngineResult(
            e4.engine_id, e4.name, e4.gate_passed, e4.score, e4_output, e4.reasons
        )
        opportunity = original_causal(adjusted)
        if opportunity is not None:
            opportunity = dict(opportunity)
            opportunity["counter_evidence"] = list(dict.fromkeys([
                *(opportunity.get("counter_evidence") or []),
                "E4_PENDING_COUNTERFLOW_NOT_TERMINAL",
            ]))
        return opportunity

    e6_module._causal_opportunity = causal_with_pending_counterflow
    e6_module._E6_PENDING_COUNTERFLOW_RUNTIME_INSTALLED = True
