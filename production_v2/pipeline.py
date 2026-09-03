from __future__ import annotations

from typing import Any

from .contracts import DecisionResult, EngineResult
from .e1_brain import analyze_e1
from .e2_brain import analyze_e2
from .e3_brain import analyze_e3
from .e4_brain import analyze_e4
from .e5_brain import analyze_e5
from .e6_brain import analyze_e6
from .e7_brain import analyze_e7
from .e8_brain import analyze_e8
from .e9_brain import analyze_e9
from .e6_runtime_authority import _normalize_watch_semantics
from .nine_brain_surgery import harden_engine
from .opportunity_layer import enrich_opportunity, recover_e9
from .professional_governance import audit_engines, enforce_final_authority
from .professional_opportunity import consolidate, enrich_engine
from .professional_brain_audit import audit_all
from .shared_market_picture import attach_brain_view, audit_shared_market_picture_contract, build_shared_market_picture
from .conflict_resolution import build_conflict_ledger
from .profit_edge import evaluate_profit_edge

ENGINE_ORDER = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9")
EVIDENCE_INPUTS = {"E1": (), "E2": ("E1",), "E3": (), "E4": ("E1", "E3"), "E5": ("E1", "E3", "E4"), "E6": ("E1", "E2", "E3", "E4", "E5"), "E7": ("E4", "E6"), "E8": ("E5", "E6", "E7"), "E9": ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8")}
NAMES = {"E1": "Market State Brain", "E2": "Opportunity / Regime Brain", "E3": "Market Structure Brain", "E4": "Liquidity Brain", "E5": "Location / Value Brain", "E6": "Setup Brain", "E7": "Confirmation Brain", "E8": "Trade Economics Brain", "E9": "Master Decision Brain"}


def _dict_result(engine_id: str, output: dict[str, Any]) -> EngineResult:
    confidence = output.get("confidence", output.get("evidence_strength", 0.0))
    try: score = float(confidence) * 100.0
    except (TypeError, ValueError): score = 0.0
    reasons = output.get("reason_codes", output.get("reasons", output.get("conflicts", ())))
    if isinstance(reasons, dict): reasons = tuple(str(k) for k, v in reasons.items() if v)
    elif isinstance(reasons, str): reasons = (reasons,)
    else: reasons = tuple(str(x) for x in (reasons or ()))
    return EngineResult(engine_id, NAMES[engine_id], output.get("gate_passed"), score, output, reasons)


def finalize_e6_output(output: dict[str, Any]) -> dict[str, Any]:
    """Final E6 semantic membrane after all generic enrichment layers.

    Generic enrichment may decorate E6 but must never re-expose a legacy
    NO_SETUP finding while structured opportunity-watch state is still alive.
    This membrane changes presentation semantics only; it does not create a
    thesis, alter direction, loosen gates, or authorize execution.
    """
    return _normalize_watch_semantics(dict(output or {}))


def _enrich(engine_id: str, result: EngineResult, snapshot: dict[str, Any]) -> EngineResult:
    output = enrich_opportunity(engine_id, result.output, snapshot)
    output = enrich_engine(engine_id, output)
    output = harden_engine(engine_id, output)
    shared = snapshot.get("shared_market_picture")
    if isinstance(shared, dict): output = attach_brain_view(engine_id, output, shared)
    if engine_id == "E6": output = finalize_e6_output(output)
    return EngineResult(result.engine_id, result.name, result.gate_passed, result.score, output, result.reason_codes)


def _scalarize(value: Any) -> str:
    if isinstance(value, dict): return " ".join(f"{key}={_scalarize(child)}" for key, child in sorted(value.items(), key=lambda item: str(item[0])))
    if isinstance(value, (list, tuple, set)): return " ".join(_scalarize(child) for child in value)
    return str(value if value is not None else "").upper().strip()


def _prepare_e9_boundary(results: dict[str, EngineResult]) -> None:
    for engine_id, engine in tuple(results.items()):
        if not engine or not isinstance(engine.output, dict): continue
        output = harden_engine(engine_id, dict(engine.output))
        output["invalidations"] = list(output.get("active_invalidations") or [])
        if engine_id == "E4":
            for key in ("event", "auction_event", "liquidity_event"):
                value = output.get(key)
                if isinstance(value, (dict, list, tuple, set)):
                    output.setdefault("event_detail", value); output[key] = _scalarize(value)
        results[engine_id] = EngineResult(engine.engine_id, engine.name, engine.gate_passed, engine.score, output, engine.reason_codes)


def _attach_conflict_ledger(results: dict[str, EngineResult], ledger: dict[str, Any]) -> None:
    for engine_id in tuple(results):
        engine = results[engine_id]; output = dict(engine.output)
        output["cross_brain_conflicts"] = ledger
        output["conflict_awareness"] = {"role": engine_id, "authority": "NON_AUTHORITATIVE_UNTIL_E9", "must_not_rewrite_upstream_evidence": True}
        results[engine_id] = EngineResult(engine.engine_id, engine.name, engine.gate_passed, engine.score, output, engine.reason_codes)


def _direction(value: Any) -> str:
    text = str(value or "").upper().strip()
    if text in {"UP", "BULLISH", "TREND_UP", "BUY"} or text.startswith("BUY ") or text.startswith("BUY_"): return "BUY"
    if text in {"DOWN", "BEARISH", "TREND_DOWN", "SELL"} or text.startswith("SELL ") or text.startswith("SELL_"): return "SELL"
    return "NEUTRAL"


def _ensure_cross_brain_conflict_visibility(results: dict[str, EngineResult], ledger: dict[str, Any]) -> dict[str, Any]:
    e2, e6 = results.get("E2"), results.get("E6")
    if not e2 or not e6: return ledger
    d2 = _direction(e2.output.get("direction") or e2.output.get("opportunity_direction") or e2.output.get("finding"))
    d6 = _direction(e6.output.get("direction") or e6.output.get("direction_thesis") or e6.output.get("thesis_direction") or e6.output.get("finding"))
    if d2 not in {"BUY", "SELL"} or d6 not in {"BUY", "SELL"} or d2 == d6: return ledger
    conflicts = list(ledger.get("conflicts") or [])
    if not any(item.get("code") == "DIRECTION_EVIDENCE_CONFLICT" and "E2" in (item.get("brains") or []) for item in conflicts):
        conflicts.append({"code":"DIRECTION_EVIDENCE_CONFLICT","severity":"HIGH","brains":["E2","E6"],"authority":"E2/E6_ROLE_BOUNDARIES","explanation":"E2 opportunity direction conflicts with E6 setup direction; preserve both specialist views and let E9 reconcile.","evidence":{"E2":d2,"E6":d6},"resolution":"E9_RECONCILE_WITHOUT_REWRITING_UPSTREAM_FACTS"})
    ledger = dict(ledger); ledger["conflicts"] = conflicts
    summary = dict(ledger.get("summary") or {})
    summary.update(total=len(conflicts), blocking_conflicts=sum(1 for x in conflicts if x.get("severity")=="HIGH"), tensions=sum(1 for x in conflicts if x.get("severity")=="MEDIUM"), supportive_relations=sum(1 for x in conflicts if x.get("severity")=="LOW"), has_conflict=bool(conflicts))
    ledger["summary"] = summary
    return ledger


def _historical_records(calibration: Any) -> Any:
    if isinstance(calibration, list): return calibration
    if isinstance(calibration, dict):
        for key in ("records", "outcomes", "trades", "historical_outcomes", "setup_history"):
            if isinstance(calibration.get(key), list): return calibration[key]
    return None


def _attach_profit_edge(results: dict[str, EngineResult], snapshot: dict[str, Any]) -> None:
    e1 = results.get("E1").output if results.get("E1") else {}
    e5 = results.get("E5").output if results.get("E5") else {}
    e6 = results.get("E6").output if results.get("E6") else {}
    e7 = results.get("E7").output if results.get("E7") else {}
    e8 = results.get("E8")
    if not e8: return
    out = dict(e8.output)
    if str(out.get("applicability") or "").upper().strip() == "NOT_APPLICABLE_WITHOUT_SURVIVING_E6_THESIS" or str(out.get("finding") or "").upper().strip() == "NOT_APPLICABLE":
        return
    direction = _direction(e6.get("direction") or e6.get("direction_thesis") or e6.get("thesis_direction") or e6.get("finding"))
    setup = str(e6.get("setup") or e6.get("setup_family") or e6.get("setup_type") or "UNKNOWN").upper().strip()
    if setup == "UNKNOWN":
        parts = str(e6.get("finding") or "").split()
        if len(parts) >= 2 and parts[0].upper() in {"BUY","SELL"}: setup = parts[1].upper()
    regime = str(e1.get("market_state") or e1.get("trend_state") or "UNKNOWN").upper().strip()
    location = str(e5.get("value_state") or e5.get("location_state") or e5.get("finding") or "UNKNOWN").upper().strip()
    confirmation = str(e7.get("confirmation_state") or e7.get("confirmation") or "UNKNOWN").upper().strip()
    plan = out.get("trade_plan") if isinstance(out.get("trade_plan"), dict) else {}
    execution = out.get("execution_cost") if isinstance(out.get("execution_cost"), dict) else {}
    try: rr = float(plan.get("rr_tp2", plan.get("rr", 0.0)) or 0.0)
    except (TypeError, ValueError): rr = 0.0
    try: cost_atr = float(execution.get("cost_atr", out.get("execution_cost_atr", 0.0)) or 0.0)
    except (TypeError, ValueError): cost_atr = 0.0
    try:
        atr = float(out.get("atr", 0.0) or 0.0); risk_price = abs(float(plan.get("entry", 0.0)) - float(plan.get("stop_loss", 0.0))); risk_atr = risk_price / max(atr, 1e-9)
    except (TypeError, ValueError): risk_atr = 0.0
    cost_r = cost_atr / max(risk_atr, 1e-9) if cost_atr > 0 and risk_atr > 0 else 0.0
    edge = evaluate_profit_edge(symbol=str(snapshot.get("symbol") or "UNKNOWN"), regime=regime, direction=direction, setup=setup, location=location, confirmation=confirmation, historical_outcomes=snapshot.get("historical_outcomes"), realized_rr=rr, cost_r=cost_r)
    out["profit_edge"] = edge
    out["economic_evidence"] = {"entry":plan.get("entry"),"stop":plan.get("stop_loss"),"target":plan.get("take_profit_2",plan.get("take_profit",plan.get("tp2"))),"rr":plan.get("rr_tp2",plan.get("rr")),"profit_edge_state":edge["state"],"expected_value_r":edge["expected_value_r"],"stress_expected_value_r":edge["stress_expected_value_r"],"sample":edge["sample"],"win_probability":edge["win_probability"],"probability_quality":edge["probability_quality"],"blockers":edge["blockers"]}
    reasons = list(e8.reason_codes)
    if edge.get("blockers"):
        reasons.extend(edge["blockers"]); reasons.append("PROBABILITY_EDGE_NOT_TRUSTWORTHY")
    results["E8"] = EngineResult("E8", e8.name, False if edge.get("blockers") else e8.gate_passed, e8.score, out, tuple(dict.fromkeys(reasons)))


def _attach_state_semantics(results: dict[str, EngineResult]) -> None:
    e1 = results.get("E1").output if results.get("E1") else {}; e6 = results.get("E6").output if results.get("E6") else {}; e7 = results.get("E7").output if results.get("E7") else {}; e8 = results.get("E8").output if results.get("E8") else {}; e9 = results.get("E9")
    if not e9: return
    out = dict(e9.output)
    out["state_semantics"] = {"market_state":str(e1.get("market_state") or e1.get("trend_state") or "UNKNOWN").upper(),"setup_state":str(e6.get("setup_state") or e6.get("opportunity_stage") or "UNKNOWN").upper(),"confirmation_state":str(e7.get("confirmation_state") or e7.get("confirmation") or "PENDING").upper(),"economic_state":str(e8.get("economic_state") or e8.get("risk_state") or (e8.get("profit_edge") or {}).get("state") or "UNKNOWN").upper(),"execution_state":str(out.get("execution") or "BLOCKED").upper()}
    results["E9"] = EngineResult(e9.engine_id,e9.name,e9.gate_passed,out,e9.reason_codes) if False else EngineResult(e9.engine_id,e9.name,e9.gate_passed,e9.score,out,e9.reason_codes)


class ProductionPipeline:
    ENGINE_ORDER = ENGINE_ORDER

    def run(self, market_data: dict[str, Any], *, wait_bars=0, resume_state=None, historical_calibration=None):
        del resume_state
        snapshot = dict(market_data)
        calibration_records = _historical_records(historical_calibration)
        if calibration_records is not None: snapshot["historical_outcomes"] = calibration_records
        shared_picture = build_shared_market_picture(snapshot)
        snapshot["shared_market_picture"] = shared_picture
        bars = list(snapshot.get("bars") or [])
        results: dict[str, EngineResult] = {}
        results["E1"] = _enrich("E1", _dict_result("E1", analyze_e1(bars)), snapshot)
        e2_snapshot = dict(snapshot); e2_snapshot["E1_result"] = results["E1"].output
        results["E2"] = _enrich("E2", _dict_result("E2", analyze_e2(e2_snapshot)), snapshot)
        results["E3"] = _enrich("E3", _dict_result("E3", analyze_e3(bars)), snapshot)
        results["E4"] = _enrich("E4", _dict_result("E4", analyze_e4(snapshot, results)), snapshot)
        results["E5"] = _enrich("E5", _dict_result("E5", analyze_e5(snapshot, results)), snapshot)
        results["E6"] = _enrich("E6", analyze_e6(snapshot, results), snapshot)
        results["E7"] = _enrich("E7", analyze_e7(snapshot, results), snapshot)
        results["E8"] = _enrich("E8", analyze_e8(snapshot, results), snapshot)
        _attach_profit_edge(results, snapshot)
        conflict_ledger = _ensure_cross_brain_conflict_visibility(results, build_conflict_ledger(results)); snapshot["cross_brain_conflicts"] = conflict_ledger; _attach_conflict_ledger(results, conflict_ledger); _prepare_e9_boundary(results)
        try:
            e9 = _enrich("E9", analyze_e9(snapshot, results), snapshot)
        except Exception as exc:
            recovery = recover_e9(results); recovery["e9_exception_type"] = type(exc).__name__; recovery["e9_exception"] = str(exc)
            recovered = _dict_result("E9", enrich_opportunity("E9", recovery, snapshot)); recovered_output = harden_engine("E9", enrich_engine("E9", recovered.output)); recovered_output = attach_brain_view("E9", recovered_output, shared_picture)
            e9 = EngineResult(recovered.engine_id,recovered.name,recovered.gate_passed,recovered.score,recovered_output,recovered.reason_codes)
        results["E9"] = e9; _attach_state_semantics(results)
        shared_picture_audit = audit_shared_market_picture_contract({engine_id: results[engine_id].output for engine_id in ENGINE_ORDER})
        if not shared_picture_audit["passed"]:
            e9 = results["E9"]
            blocked_output = dict(e9.output)
            blocked_output["decision"] = "NO_TRADE"
            blocked_output["decision_reason"] = ["SHARED_MARKET_PICTURE_CONTRACT_FAILED"]
            blocked_output["shared_market_picture_audit"] = shared_picture_audit
            results["E9"] = EngineResult("E9", e9.name, False, e9.score, blocked_output, tuple(dict.fromkeys(list(e9.reason_codes) + ["SHARED_MARKET_PICTURE_CONTRACT_FAILED"])))
        audit = audit_engines(results); results["E9"] = enforce_final_authority(results["E9"], results); results["E9"] = EngineResult("E9", results["E9"].name, results["E9"].gate_passed, results["E9"].score, dict(results["E9"].output, architecture_audit=audit), results["E9"].reason_codes)
        audit_all(results)
        decision = results["E9"].output.get("decision", "NO_TRADE")
        trade_ready = bool(results["E9"].output.get("trade_ready", False))
        gate_passed = bool(results["E9"].gate_passed)
        if decision == "TRADE" and not trade_ready: decision = "NO_TRADE"
        if decision == "TRADE" and not gate_passed: decision = "NO_TRADE"
        if decision not in {"TRADE", "NO_TRADE"}: decision = "NO_TRADE"
        state = "SIGNAL_READY" if decision == "TRADE" and trade_ready and gate_passed else "ANALYSIS_COMPLETE_NO_TRADE"
        return DecisionResult(decision=decision, state=state, engines=results, blocked_by=None, wait_bars=wait_bars)
