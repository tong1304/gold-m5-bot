from __future__ import annotations

"""Professional opportunity synthesis for production-v2.

This layer is deliberately non-authoritative: it makes conditional profit
opportunities visible without manufacturing a BUY/SELL decision. E9 remains
the sole execution authority.
"""

from typing import Any

from .contracts import DecisionResult, EngineResult
from .opportunity_timing import classify_opportunity_timing

DIRECTIONS = {"BUY", "SELL"}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _direction(output: dict[str, Any]) -> str:
    for key in ("direction", "opportunity_direction", "direction_thesis", "thesis_direction"):
        value = _text(output.get(key))
        if value in DIRECTIONS: return value
        if value in {"UP", "BULLISH", "TREND_UP"}: return "BUY"
        if value in {"DOWN", "BEARISH", "TREND_DOWN"}: return "SELL"
    finding = _text(output.get("finding"))
    if finding.startswith(("BUY ", "BUY_")): return "BUY"
    if finding.startswith(("SELL ", "SELL_")): return "SELL"
    return "NEUTRAL"


def _codes(output: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("reason_codes", "reasons", "counter_evidence", "missing_evidence", "blockers", "conflicts", "invalidations"):
        value = output.get(key)
        if isinstance(value, str): values.append(_text(value))
        elif isinstance(value, (list, tuple, set)): values.extend(_text(x) for x in value if x)
        elif isinstance(value, dict): values.extend(_text(k) for k, v in value.items() if v)
    return list(dict.fromkeys(x for x in values if x))


def _has(output: dict[str, Any], *needles: str) -> bool:
    haystack = " ".join([_text(output.get("finding")), _text(output.get("state")), *_codes(output)])
    return any(n in haystack for n in needles)


def _space(output: dict[str, Any], direction: str) -> float | None:
    key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short" if direction == "SELL" else "effective_space_atr"
    try:
        value = float(output.get(key)); return value if value == value else None
    except (TypeError, ValueError): return None


def _brain(results: dict[str, Any] | tuple[EngineResult, ...], engine_id: str) -> dict[str, Any]:
    if isinstance(results, dict):
        result = results.get(engine_id)
        return dict(getattr(result, "output", result) or {})
    for result in results:
        if result.engine_id == engine_id: return dict(result.output or {})
    return {}


def _directional_book_view(output: dict[str, Any]) -> dict[str, Any]:
    book = output.get("opportunity_book")
    if not isinstance(book, dict): return {}
    candidates = book.get("candidates") if isinstance(book.get("candidates"), list) else []
    radar: dict[str, Any] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict): continue
        direction = _text(candidate.get("direction"))
        if direction not in DIRECTIONS: continue
        quality = candidate.get("quality", candidate.get("score", 0.0))
        try:
            quality = float(quality)
            if quality <= 1.0: quality *= 100.0
        except (TypeError, ValueError): quality = 0.0
        radar[direction] = {"state": candidate.get("state", "DEVELOPING"), "quality": round(max(0.0, min(100.0, quality)), 2), "wait_for": candidate.get("wait_for") or ["NEXT_CLOSED_M5_CANDLE"], "conditional": True}
    return {"radar": radar, "leader": _text(book.get("leader") or "NEUTRAL"), "competition": _text(book.get("competition") or "UNCONTESTED")}


def _combined_timing(results: dict[str, Any] | tuple[EngineResult, ...]) -> dict[str, Any]:
    """Build timing from the causal event plus E5 geometry, never from E9's decision."""
    e4, e5, e6 = (_brain(results, x) for x in ("E4", "E5", "E6"))
    direction = _direction(e6) if _direction(e6) in DIRECTIONS else _direction(e4)
    merged = dict(e4)
    merged.update({k: v for k, v in e5.items() if v is not None})
    merged.update({k: v for k, v in e6.items() if k not in {"direction"} and v is not None})
    merged["direction"] = direction
    event = e4.get("event") or e4.get("auction_event") or e4.get("liquidity_event")
    if event: merged["event"] = event
    for source_key, target_key in (("quality","confidence"),("event_quality","confidence"),("auction_quality","auction_quality")):
        if target_key not in merged and e4.get(source_key) is not None: merged[target_key] = e4[source_key]
    if e4.get("event_age_bars") is not None: merged["event_age_bars"] = e4.get("event_age_bars")
    if e4.get("causal_event_anchor") and "event_age_bars" not in merged:
        merged["event_age_bars"] = e4["causal_event_anchor"].get("age_bars")
    space_key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short" if direction == "SELL" else None
    if space_key and e5.get(space_key) is not None: merged["available_space_atr"] = e5.get(space_key)
    return classify_opportunity_timing(merged)


def synthesize(engines: tuple[EngineResult, ...]) -> dict[str, Any]:
    """Build a conditional opportunity map from the already completed brains."""
    e1, e2, e3, e4, e5, e6, e7, e8, e9 = (_brain(engines, x) for x in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"))
    directions = [_direction(x) for x in (e1, e2, e3, e4, e5, e6)]
    counts = {d: directions.count(d) for d in DIRECTIONS}; dominant = max(counts, key=counts.get) if max(counts.values(), default=0) else "NEUTRAL"; agreement = counts.get(dominant, 0) / 6.0 if dominant in DIRECTIONS else 0.0
    setup = _text(e6.get("setup") or e6.get("setup_family") or e6.get("setup_type")); setup_state = _text(e6.get("setup_state") or e6.get("opportunity_stage") or e6.get("state")); confirmation = _text(e7.get("confirmation_state") or e7.get("confirmation") or e7.get("state")); economics = _text(e8.get("economic_state") or e8.get("risk_state") or (e8.get("profit_edge") or {}).get("state"))
    support: list[str] = []; counter: list[str] = []; missing: list[str] = []
    if dominant in DIRECTIONS: support.append(f"DIRECTIONAL_CONSENSUS={counts[dominant]}/6")
    if _has(e3, "BOS_UP", "BULLISH_STRUCTURE") and dominant == "BUY": support.append("BULLISH_STRUCTURE_SUPPORT")
    if _has(e3, "BOS_DOWN", "BEARISH_STRUCTURE") and dominant == "SELL": support.append("BEARISH_STRUCTURE_SUPPORT")
    if _has(e4, "SWEEP_REJECTION", "FAILED_BREAK_RECLAIM", "ACCEPTANCE"): support.append("LIQUIDITY_OR_AUCTION_EVENT_PRESENT")
    if _has(e5, "FAVORABLE_LOCATION", "LOCATION_ACTIONABLE"): support.append("LOCATION_SUPPORT")
    for output in (e2, e4, e5, e7, e8):
        for code in _codes(output):
            if any(x in code for x in ("CONFLICT", "PENDING", "INSUFFICIENT", "NOT_PROVEN", "NOT_TRUSTWORTHY", "CONSTRAINED", "INVALID", "BELOW_MINIMUM")): counter.append(code)
    if not _has(e4, "CONFIRMED", "ACCEPTED", "RECLAIMED", "TERMINAL"): missing.append("setup_specific_closed_candle_auction_or_liquidity_proof")
    if confirmation not in {"CONFIRMED", "PROVEN", "VALIDATED", "TRADE_READY", "PASS"}: missing.append("valid_closed_candle_trigger_confirmation")
    if economics not in {"VALID", "VALIDATED", "TRADE_READY", "PASS", "POSITIVE"}: missing.append("survivable_trade_geometry_and_positive_profit_edge")
    space = _space(e5, dominant)
    if space is not None and space < 0.75: counter.append("STRUCTURAL_SPACE_CONSTRAINED"); missing.append("adequate_opposing_space")
    hard_blockers = []
    for output in (e6, e7, e8, e9):
        for code in _codes(output):
            if any(x in code for x in ("INVALID_TRADE_GEOMETRY", "NO_USABLE_STRUCTURAL_TARGET", "REAL_RR_BELOW_MINIMUM", "STRUCTURAL_SURVIVAL_NOT_PROVEN", "HARD_VETO")): hard_blockers.append(code)
    timing = _combined_timing(engines)
    if dominant not in DIRECTIONS: state = "NO_DIRECTIONAL_EDGE"
    elif hard_blockers: state = "OPPORTUNITY_BLOCKED"
    elif timing["phase"] == "LATE_OPPORTUNITY": state = "OPPORTUNITY_DECAYING"
    elif timing["phase"] in {"EARLY_OPPORTUNITY", "CONFIRMED_OPPORTUNITY"}: state = "OPPORTUNITY_EXISTS_NOT_READY" if missing else "OPPORTUNITY_READY_FOR_FINAL_AUTHORITY"
    elif setup and setup not in {"NONE", "UNKNOWN", "NO_SETUP"}: state = "OPPORTUNITY_FORMING" if missing else "OPPORTUNITY_READY_FOR_FINAL_AUTHORITY"
    else: state = "OPPORTUNITY_WATCH"
    if agreement < 0.50: state = "DIRECTIONAL_CONFLICT" if dominant in DIRECTIONS else state
    directional = _directional_book_view(e2)
    return {"architecture":"PROFESSIONAL_OPPORTUNITY_SYNTHESIS_V2","authority":"OBSERVATIONAL_ONLY","execution_authority":"E9_ONLY","state":state,"direction":dominant,"directional_consensus":round(agreement,3),"supporting_evidence":list(dict.fromkeys(support)),"counter_evidence":list(dict.fromkeys(counter)),"missing_evidence":list(dict.fromkeys(missing)),"hard_blockers":list(dict.fromkeys(hard_blockers)),"setup":setup or "UNKNOWN","setup_state":setup_state or "UNKNOWN","confirmation_state":confirmation or "UNKNOWN","economic_state":economics or "UNKNOWN","space_atr":space,"directional_opportunities":directional.get("radar",{}),"competition":directional.get("competition","UNCONTESTED"),"leader":directional.get("leader","NEUTRAL"),"opportunity_timing":timing,"next_required_event":missing[0] if missing else "E9_FINAL_AUTHORITY_CHECK","professional_rule":"SEE_OPPORTUNITY_FIRST_PROVE_IT_SECOND_EXECUTE_LAST","trade_authorized":False}


def enrich_decision(result: DecisionResult) -> DecisionResult:
    radar = synthesize(result.engines); engines: list[EngineResult] = []
    for engine in result.engines:
        output = dict(engine.output or {}); output["opportunity_radar"] = radar; engines.append(EngineResult(engine.engine_id, engine.name, engine.gate_passed, engine.score, output, engine.reason_codes))
    risk = dict(result.risk or {}); risk["opportunity_radar"] = radar; risk["opportunity_authority"] = "E9_ONLY"
    return DecisionResult(symbol=result.symbol,timeframe=result.timeframe,decision=result.decision,gate_passed=result.gate_passed,score=result.score,engines=tuple(engines),risk=risk,reason_codes=result.reason_codes)


def install(module: Any, pipeline: Any = None) -> None:
    """Patch consolidation and pipeline consolidation without changing E9 authority."""
    if not getattr(module, "_DIRECTIONAL_CONSOLIDATOR_BOUND", False):
        original = module.consolidate
        def consolidate(results: dict[str, Any]) -> dict[str, Any]:
            result = dict(original(results) or {})
            e2_result = results.get("E2") if isinstance(results, dict) else None
            e2 = e2_result.output if hasattr(e2_result, "output") else e2_result
            view = _directional_book_view(e2 if isinstance(e2, dict) else {})
            result["directional_radar"] = view.get("radar", {})
            result["leader"] = view.get("leader", "NEUTRAL")
            result["competition"] = view.get("competition", "UNCONTESTED")
            result["counter_direction"] = "SELL" if result["leader"] == "BUY" and "SELL" in result["directional_radar"] else "BUY" if result["leader"] == "SELL" and "BUY" in result["directional_radar"] else None
            result["opportunity_timing"] = _combined_timing(results)
            result["opportunity_lifecycle_state"] = "DECAYING" if result["opportunity_timing"]["phase"] == "LATE_OPPORTUNITY" else "EARLY" if result["opportunity_timing"]["phase"] == "EARLY_OPPORTUNITY" else "CONFIRMED" if result["opportunity_timing"]["phase"] == "CONFIRMED_OPPORTUNITY" else "IDLE"
            result["trade_authorized"] = False
            return result
        module.consolidate = consolidate
        module._DIRECTIONAL_CONSOLIDATOR_BOUND = True

    if pipeline is not None and not getattr(pipeline, "_OPPORTUNITY_TIMING_BOUND", False):
        original_pipeline_consolidate = getattr(pipeline, "consolidate", None)
        if callable(original_pipeline_consolidate):
            def pipeline_consolidate(results):
                result = dict(original_pipeline_consolidate(results) or {})
                result["opportunity_timing"] = _combined_timing(results)
                result["trade_authorized"] = False
                return result
            pipeline.consolidate = pipeline_consolidate
            pipeline._OPPORTUNITY_TIMING_BOUND = True
