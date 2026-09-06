from __future__ import annotations

from typing import Any

from .contracts import EngineResult

VERSION = "E6_EVIDENCE_AUTHORITY_V2"
WATCH_SETUPS = {"OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS"}
PENDING_AUCTION_STATES = {"PENDING", "DEVELOPING", "FORMING", "AWAITING_CONFIRMATION", "CONFIRMATION_PENDING"}
DIRECTIONS = {"BUY", "SELL"}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _direction(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text in {"BUY", "BULLISH", "UP", "LONG", "BUYERS", "BUYER", "TREND_UP"} or text.startswith(("BUY ", "BUY_", "BUY:")):
            return "BUY"
        if text in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS", "SELLER", "TREND_DOWN"} or text.startswith(("SELL ", "SELL_", "SELL:")):
            return "SELL"
    return "NEUTRAL"


def _event_direction(e4: dict[str, Any]) -> str:
    event = _text(e4.get("event") or e4.get("finding"))
    if "HIGH_SWEEP_REJECTION" in event or "HIGH_REJECTION" in event:
        return "SELL"
    if "LOW_SWEEP_REJECTION" in event or "LOW_REJECTION" in event:
        return "BUY"
    if "HIGH_ACCEPTANCE" in event or "HIGH_BREAK" in event:
        return "BUY"
    if "LOW_ACCEPTANCE" in event or "LOW_BREAK" in event:
        return "SELL"
    return _direction(e4.get("directional_implication"), e4.get("direction"), e4.get("response_actor"))


def _out(result: Any) -> dict[str, Any]:
    value = getattr(result, "output", {})
    return dict(value) if isinstance(value, dict) else {}


def _payload(upstream: dict[str, EngineResult], key: str) -> dict[str, Any]:
    result = upstream.get(key)
    return _out(result) if result else {}


def _is_watch(out: dict[str, Any]) -> bool:
    setup = _text(out.get("setup") or out.get("setup_family"))
    return setup in WATCH_SETUPS or _text(out.get("candidate_type")) == "OPPORTUNITY_CANDIDATE" or out.get("watch_only") is True


def _structure_evidence(e3: dict[str, Any], direction: str) -> list[str]:
    external = _direction(e3.get("external_state"), e3.get("structure_direction"), e3.get("direction"))
    internal = _direction(e3.get("internal_state"))
    evidence: list[str] = []
    protected = _text(e3.get("protected_completeness"))
    if external == direction and protected not in {"NO_DIRECTIONAL_REGIME", "INCOMPLETE", "MIXED"}:
        evidence.append("E3_EXTERNAL_STRUCTURE_SUPPORT")
    elif _text(e3.get("external_state")) == "MIXED" or _text(e3.get("protected_active_regime")) == "MIXED":
        evidence.append("E3_MIXED_CONTEXT")
    elif external in DIRECTIONS and external != direction:
        evidence.append("E3_EXTERNAL_COUNTERFLOW")
    if internal == direction:
        evidence.append("E3_INTERNAL_STRUCTURE_ALIGNMENT")
    elif _text(e3.get("internal_state")) == "MIXED":
        evidence.append("E3_INTERNAL_MIXED_CONTEXT")
    elif internal in DIRECTIONS and internal != direction:
        evidence.append("E3_INTERNAL_COUNTERFLOW")
    return evidence


def normalize_e6_evidence(result: EngineResult, upstream: dict[str, EngineResult]) -> EngineResult:
    out = _out(result)
    if not _is_watch(out):
        return result
    direction = _direction(out.get("direction"), out.get("direction_thesis"), out.get("thesis_direction"))
    if direction not in DIRECTIONS:
        return result
    e3 = _payload(upstream, "E3")
    e4 = _payload(upstream, "E4")
    existing = [str(x).strip().upper() for x in (out.get("supporting_evidence") or []) if str(x).strip()]
    legacy = {"E4_DIRECTIONAL_AUCTION_EVIDENCE", "E4_DIRECTIONAL_EVENT_EVIDENCE", "E4_DIRECTIONAL_AUCTION_SUPPORT", "E3_EXTERNAL_STRUCTURE_SUPPORT", "E3_INTERNAL_STRUCTURE_ALIGNMENT", "E3_INTERNAL_MIXED_CONTEXT", "E3_MIXED_CONTEXT", "E3_EXTERNAL_COUNTERFLOW", "E3_INTERNAL_COUNTERFLOW", "E4_CONFIRMED_RESPONSE", "E4_AUCTION_UNCONFIRMED", "E4_DIRECTIONAL_EVENT_OBSERVATION"}
    preserved = [x for x in existing if x not in legacy]
    event = _text(e4.get("event") or e4.get("finding"))
    auction_state = _text(e4.get("auction_state") or e4.get("auction_phase") or e4.get("state"))
    event_direction = _event_direction(e4)
    event_is_directional = event_direction == direction
    if event and event_is_directional:
        preserved.append("E4_DIRECTIONAL_EVENT_OBSERVATION")
    if auction_state not in PENDING_AUCTION_STATES and event_is_directional:
        preserved.append("E4_CONFIRMED_RESPONSE")
    preserved.extend(_structure_evidence(e3, direction))
    out["supporting_evidence"] = list(dict.fromkeys(preserved))
    out["evidence_attribution_authority"] = "E3_E4_FACTS"
    out["evidence_attribution_version"] = VERSION
    out["evidence_attribution_boundary"] = "E6_MAY_CLASSIFY_BUT_MUST_NOT_UPGRADE_MIXED_OR_PENDING_UPSTREAM_FACTS"
    return EngineResult(result.engine_id, result.name, result.gate_passed, result.score, out, result.reason_codes)


def install(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_E6_EVIDENCE_AUTHORITY_INSTALLED", False):
        return
    original = pipeline_module.analyze_e6

    def guarded_analyze_e6(market_data: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
        result = original(market_data, upstream)
        if not isinstance(result, EngineResult):
            return result
        return normalize_e6_evidence(result, upstream)

    pipeline_module.analyze_e6 = guarded_analyze_e6
    pipeline_module._E6_EVIDENCE_AUTHORITY_INSTALLED = True
    module_name = getattr(pipeline_module, "__name__", type(pipeline_module).__name__)
    analyze_name = getattr(guarded_analyze_e6, "__name__", type(guarded_analyze_e6).__name__)
    analyze_module = getattr(guarded_analyze_e6, "__module__", type(guarded_analyze_e6).__module__)
    print(f"[PRODUCTION V2] E6_EVIDENCE_AUTHORITY_BINDING version={VERSION} module={module_name} analyze={analyze_module}.{analyze_name}", flush=True)
