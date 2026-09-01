from __future__ import annotations

import copy
import hashlib
import json
from math import isfinite
from statistics import mean
from typing import Any

"""Single immutable closed-candle evidence boundary for E1-E9.

Shared picture = FACT only. Brain output = INTERPRETATION + local DECISION.
E9 owns the final decision. A contract violation is a governance blocker.
"""

ENGINE_ORDER = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9")
CONTRACT_SCHEMA = "SHARED_MARKET_PICTURE_CONTRACT_V3"


def _num(v: Any) -> float | None:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if isfinite(v) else None


def _bar_is_closed(bar: dict[str, Any]) -> bool:
    for key in ("is_closed", "closed", "complete", "is_complete", "closed_candle", "candle_closed"):
        if key in bar:
            return bool(bar[key])
    return True


def _bar_identity(bar: dict[str, Any]) -> str | None:
    v = bar.get("id") or bar.get("candle_id") or bar.get("timestamp") or bar.get("time")
    return str(v) if v is not None else None


def _clean_bars(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for raw in bars or []:
        if not isinstance(raw, dict) or not _bar_is_closed(raw):
            continue
        vals = {k: _num(raw.get(k)) for k in ("open", "high", "low", "close")}
        if any(v is None for v in vals.values()):
            continue
        o, h, l, c = vals.values()
        if h < l or h < max(o, c) or l > min(o, c):
            continue
        out.append({**raw, **vals})
    return out


def _freeze_closed_candle_boundary(market_data: dict[str, Any], bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if market_data.get("closed_candle_only") is False:
        raise ValueError("SHARED_MARKET_PICTURE_REQUIRES_CLOSED_CANDLE_ONLY")
    if market_data.get("lookahead_allowed") is True:
        raise ValueError("SHARED_MARKET_PICTURE_REJECTS_LOOKAHEAD")
    cutoff_id = market_data.get("data_cutoff_candle_id")
    cutoff_ts = market_data.get("data_cutoff_timestamp")
    if cutoff_id is not None:
        cutoff_id = str(cutoff_id)
        idx = {_bar_identity(b): i for i, b in enumerate(bars)}
        if cutoff_id not in idx:
            raise ValueError("DATA_CUTOFF_CANDLE_NOT_FOUND")
        bars = bars[: idx[cutoff_id] + 1]
    elif cutoff_ts is not None:
        cutoff_ts = str(cutoff_ts)
        bars = [b for b in bars if (b.get("timestamp") or b.get("time")) is None or str(b.get("timestamp") or b.get("time")) <= cutoff_ts]
    if not bars:
        raise ValueError("NO_CLOSED_CANDLE_EVIDENCE")
    if not _bar_is_closed(bars[-1]):
        raise ValueError("CLOSED_CANDLE_BOUNDARY_VIOLATION")
    market_data["bars"] = list(bars)
    market_data["data_cutoff_candle_id"] = _bar_identity(bars[-1])
    market_data["data_cutoff_timestamp"] = bars[-1].get("timestamp") or bars[-1].get("time")
    market_data["closed_candle_only"] = True
    market_data["lookahead_allowed"] = False
    return bars


def _atr(bars: list[dict[str, Any]], n: int = 14) -> float:
    if len(bars) < n:
        return 0.0
    tr, prev = [], None
    for b in bars[-n:]:
        h, l, c = b["high"], b["low"], b["close"]
        tr.append(max(h-l, abs(h-prev), abs(l-prev)) if prev is not None else h-l)
        prev = c
    return mean(tr) if tr else 0.0


def _ema(values: list[float], n: int) -> float:
    if not values:
        return 0.0
    a, r = 2.0/(n+1.0), values[0]
    for v in values[1:]:
        r = a*v + (1-a)*r
    return r


def _range(bars: list[dict[str, Any]], n: int):
    if len(bars) < n:
        return None, None
    w = bars[-n:]
    return max(b["high"] for b in w), min(b["low"] for b in w)


def _fact_payload(p: dict[str, Any]) -> dict[str, Any]:
    return {k: p.get(k) for k in ("symbol","timeframe","candle_identity","data_cutoff_candle_id","data_cutoff_timestamp","bar_count","current","volatility","trend_context","reference_levels","data_integrity")}


def _picture_id(p: dict[str, Any]) -> str:
    raw = json.dumps(_fact_payload(p), sort_keys=True, separators=(",",":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _fact_fields(p: dict[str, Any]) -> dict[str, Any]:
    return {"symbol":p["symbol"],"timeframe":p["timeframe"],"candle_identity":p["candle_identity"],"data_cutoff_candle_id":p["data_cutoff_candle_id"],"data_cutoff_timestamp":p["data_cutoff_timestamp"],"bar_count":p["bar_count"],"current":p["current"],"volatility.atr14":p["volatility"]["atr14"],"trend_context.ema20":p["trend_context"]["ema20"],"trend_context.ema50":p["trend_context"]["ema50"],"trend_context.ema20_vs_ema50":p["trend_context"]["ema20_vs_ema50"],"trend_context.ema_gap_atr":p["trend_context"]["ema_gap_atr"],"reference_levels":p["reference_levels"],"data_integrity":p["data_integrity"]}


def build_shared_market_picture(market_data: dict[str, Any]) -> dict[str, Any]:
    source = list(market_data.get("bars") or [])
    bars = _freeze_closed_candle_boundary(market_data, _clean_bars(source))
    closes = [b["close"] for b in bars]
    last = bars[-1]
    atr = _atr(bars)
    e20, e50 = _ema(closes,20), _ema(closes,50)
    r20h,r20l = _range(bars,20); r50h,r50l = _range(bars,50)
    explicit = any(any(k in b for k in ("is_closed","closed","complete","is_complete","closed_candle","candle_closed")) for b in bars)
    p = {"schema":"SHARED_MARKET_PICTURE_V2","scope":"ONE_CLOSED_M5_CYCLE","symbol":str(market_data.get("symbol") or "UNKNOWN"),"timeframe":str(market_data.get("timeframe") or "M5"),"data_cutoff_candle_id":_bar_identity(last),"data_cutoff_timestamp":last.get("timestamp") or last.get("time"),"closed_candle_only":True,"lookahead_allowed":False,"lookahead_detected":False,"candle_identity":_bar_identity(last),"bar_count":len(bars),"current":{k:last.get(k) for k in ("open","high","low","close")},"volatility":{"atr14":atr},"trend_context":{"ema20":e20,"ema50":e50,"ema20_vs_ema50":"UP" if e20>e50 else "DOWN" if e20<e50 else "FLAT","ema_gap_atr":(e20-e50)/atr if atr>0 else 0.0},"reference_levels":{"range20_high":r20h,"range20_low":r20l,"range50_high":r50h,"range50_low":r50l},"data_integrity":{"valid_ohlc_bars":len(bars),"source_bars":len(source),"sufficient_for_context":len(bars)>=50,"all_visible_bars_closed":all(_bar_is_closed(b) for b in bars),"closure_boundary":"EXPLICIT_BAR_METADATA" if explicit else "FROZEN_CLOSED_CYCLE"},"shared_truth":["ALL_BRAINS_USE_THIS_CYCLE_SNAPSHOT","CLOSED_CANDLE_ONLY","NO_LOOKAHEAD","FACTS_ARE_SHARED;_INTERPRETATIONS_REMAIN_BRAIN_SPECIFIC"]}
    p["picture_id"] = _picture_id(p)
    p["fact_ledger"] = {"classification":"FACT_ONLY","authority":"SHARED_MARKET_PICTURE","interpretation_allowed":False,"fields":_fact_fields(p),"derivation":"DETERMINISTIC_FROM_FROZEN_CLOSED_OHLC_SNAPSHOT","fingerprint":p["picture_id"],"source_ids":[f"CANDLE:{p['data_cutoff_candle_id']}"]}
    p["contract"] = {"schema":CONTRACT_SCHEMA,"picture_id":p["picture_id"],"data_cutoff_candle_id":p["data_cutoff_candle_id"],"data_cutoff_timestamp":p["data_cutoff_timestamp"],"closed_candle_only":True,"lookahead_detected":False,"fact_source_ids":list(p["fact_ledger"]["source_ids"]),"interpretation_source_ids":[],"decision_source_ids":[],"fact_mutation":"FORBIDDEN","interpretation_location":"BRAIN_OUTPUT_ONLY","decision_authority":"E9_ONLY"}
    return p

FIELD_OF_VIEW = {"E1":{"role":"MARKET_STATE","sees":["data_integrity","volatility","market_structure_context","directional_pressure","persistence","regime","transition","state_stability","counter_evidence"],"does_not_own":["setup","entry","target","stop","trade_economics","execution","final_decision"]},"E2":{"role":"OPPORTUNITY_REGIME","sees":["shared_market_picture","E1_evidence","regime","auction_context","candidate_opportunity_paths","opportunity_maturity"],"does_not_own":["final_entry","risk_authority","final_decision"]},"E3":{"role":"MARKET_STRUCTURE","sees":["shared_market_picture","confirmed_pivots","protected_levels","BOS","CHOCH","structure_lifecycle","structure_invalidation"],"does_not_own":["opportunity_selection","entry","RR","risk","final_decision"]},"E4":{"role":"LIQUIDITY_AUCTION","sees":["shared_market_picture","structure_context","liquidity_zones","sweeps","failed_breaks","auction_taker","response_actor","acceptance_rejection"],"does_not_own":["setup_creation","final_direction","trade_economics","final_decision"]},"E5":{"role":"LOCATION_VALUE","sees":["shared_market_picture","value","premium_discount","structural_location","support_resistance","available_space","extension","counter_evidence"],"does_not_own":["entry_confirmation","risk_authority","final_decision"]},"E6":{"role":"SETUP_FORMATION","sees":["shared_market_picture","E1_to_E5_evidence","candidate_setup","directional_conflict","setup_lifecycle","required_proof"],"does_not_own":["confirmation_authority","trade_economics","final_decision"]},"E7":{"role":"CONFIRMATION","sees":["shared_market_picture","E4_evidence","E6_thesis","closed_candle_trigger","follow_through","invalidation","missing_proof"],"does_not_own":["creating_the_thesis","risk_authority","final_decision"]},"E8":{"role":"TRADE_ECONOMICS_RISK","sees":["shared_market_picture","E5_location","E6_setup","E7_confirmation","entry","stop","target","RR","structural_survival","execution_uncertainty","probability_quality"],"does_not_own":["creating_market_thesis","overriding_structure","final_decision"]},"E9":{"role":"MASTER_MARKET_CONTROL","sees":["shared_market_picture","E1_to_E8_evidence","cross_brain_conflicts","active_invalidations","opportunity_maturity","trade_economics","governance"],"does_not_own":["inventing_missing_evidence","rewriting_upstream_facts","bypassing_risk","lookahead"]}}


def _interpretation_payload(o: dict[str, Any]) -> dict[str, Any]:
    return {k:o[k] for k in ("finding","observations","reasons","reason_codes","counter_evidence","missing_evidence","conflicts","invalidations") if k in o}


def _local_decision(o: dict[str, Any]) -> Any:
    for k in ("decision","gate_passed","confirmation","state","finding"):
        if k in o: return o[k]
    return None


def attach_brain_view(engine_id: str, output: dict[str, Any], shared: dict[str, Any]) -> dict[str, Any]:
    if engine_id not in FIELD_OF_VIEW: raise ValueError(f"Unknown engine_id: {engine_id}")
    shared_copy = copy.deepcopy(shared)
    pid = shared_copy.get("picture_id")
    view = FIELD_OF_VIEW[engine_id]
    result = dict(output or {})
    result["shared_market_picture"] = shared_copy
    result["field_of_view"] = {"role":view["role"],"sees":list(view["sees"]),"does_not_own":list(view["does_not_own"]),"boundary_rule":"DESCRIBE_ONLY_WHAT_THIS_BRAIN_HAS_EVIDENCE_AND_AUTHORITY_TO_SEE"}
    result["market_picture_contract"] = {"schema":CONTRACT_SCHEMA,"picture_id":pid,"data_cutoff_candle_id":shared_copy.get("data_cutoff_candle_id"),"data_cutoff_timestamp":shared_copy.get("data_cutoff_timestamp"),"closed_candle_only":shared_copy.get("closed_candle_only") is True,"lookahead_allowed":False,"lookahead_detected":False,"fact_source_ids":list((shared_copy.get("contract") or {}).get("fact_source_ids") or []),"interpretation_source_ids":[engine_id],"decision_source_ids":[engine_id],"fact_authority":"SHARED_MARKET_PICTURE","fact_mutation":"FORBIDDEN","interpretation_authority":"BRAIN_ROLE_ONLY","decision_authority":"E9_ONLY"}
    result["evidence_audit"] = {"facts":{"source":"SHARED_MARKET_PICTURE","picture_id":pid,"classification":"FACT","source_ids":list((shared_copy.get("contract") or {}).get("fact_source_ids") or []),"fields":dict((shared_copy.get("fact_ledger") or {}).get("fields") or {})},"interpretation":{"source":engine_id,"classification":"INTERPRETATION","source_ids":[engine_id],"role":view["role"],**_interpretation_payload(result)},"decision":{"source":engine_id,"classification":"DECISION","source_ids":[engine_id],"scope":view["role"],"value":_local_decision(result),"final_authority":engine_id=="E9"}}
    result["view_contract"] = "SHARED_FACTS + BRAIN_SPECIFIC_INTERPRETATION + BRAIN_LOCAL_DECISION + EXPLICIT_BOUNDARY"
    return result


def audit_shared_market_picture_contract(outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    covered=[e for e in ENGINE_ORDER if isinstance(outputs.get(e),dict)]
    missing=[]; violations=[]; violating=[]; mismatched=[]; pids={}; cuts={}; times={}
    for e in covered:
        o=outputs[e]; s=o.get("shared_market_picture"); c=o.get("market_picture_contract"); a=o.get("evidence_audit")
        if not isinstance(s,dict) or not isinstance(c,dict) or not isinstance(a,dict): missing.append(e); continue
        declared=c.get("picture_id"); actual=_picture_id(s); pids[e]=str(declared); cuts[e]=str(c.get("data_cutoff_candle_id")); times[e]=str(c.get("data_cutoff_timestamp")); bv=[]
        if c.get("closed_candle_only") is not True: bv.append("CLOSED_CANDLE_CONTRACT_VIOLATION")
        if c.get("lookahead_allowed") is True or c.get("lookahead_detected") is True: bv.append("LOOKAHEAD_CONTRACT_VIOLATION")
        if s.get("closed_candle_only") is not True or s.get("lookahead_detected") is not False: bv.append("SHARED_BOUNDARY_VIOLATION")
        if declared!=s.get("picture_id") or actual!=s.get("picture_id"): bv.append("SHARED_PICTURE_ID_MISMATCH")
        if s.get("data_cutoff_candle_id")!=c.get("data_cutoff_candle_id"): bv.append("CUTOFF_CANDLE_MISMATCH")
        if s.get("data_cutoff_timestamp")!=c.get("data_cutoff_timestamp"): bv.append("CUTOFF_TIMESTAMP_MISMATCH")
        if (a.get("facts") or {}).get("classification")!="FACT": bv.append("FACT_CLASSIFICATION_MISSING")
        if (a.get("interpretation") or {}).get("classification")!="INTERPRETATION": bv.append("INTERPRETATION_CLASSIFICATION_MISSING")
        if (a.get("decision") or {}).get("classification")!="DECISION": bv.append("DECISION_CLASSIFICATION_MISSING")
        if bv: violating.append(e); mismatched.append(e); violations.extend(f"{e}:{x}" for x in bv)
    issues=[]
    if missing: issues.append("SHARED_PICTURE_CONTRACT_MISSING")
    if len(set(pids.values()))>1: issues.append("MULTIPLE_SHARED_PICTURES")
    if len(set(cuts.values()))>1: issues.append("MULTIPLE_DATA_CUTOFF_CANDLES")
    if len(set(times.values()))>1: issues.append("MULTIPLE_DATA_CUTOFF_TIMESTAMPS")
    issues.extend(sorted(set(violations)))
    if covered and len(covered)!=len(ENGINE_ORDER): issues.append("INCOMPLETE_BRAIN_COVERAGE")
    return {"schema":"SHARED_MARKET_PICTURE_AUDIT_V2","passed":not issues,"covered_brains":covered,"expected_brains":list(ENGINE_ORDER),"unique_picture_ids":sorted(set(pids.values())),"unique_cutoff_candle_ids":sorted(set(cuts.values())),"unique_cutoff_timestamps":sorted(set(times.values())),"violating_brains":sorted(set(violating)),"mismatched_brains":sorted(set(mismatched)),"missing_contract_brains":missing,"issues":sorted(set(issues)),"authority":"HARD_GOVERNANCE_INPUT","decision_authority":"E9_ONLY","rule":"NO_BRAIN_MAY_USE_OPEN_CANDLE_OR_LOOKAHEAD_FOR_FACT_INTERPRETATION_EVIDENCE_THESIS_OR_DECISION"}
