from __future__ import annotations

import hashlib
import json
from math import isfinite
from statistics import mean
from typing import Any

"""Shared market picture for the nine brains.

One cycle = one immutable closed-candle evidence boundary.  The shared
picture owns FACTS only.  Each brain owns only its role-specific
INTERPRETATION and local DECISION.  E9 alone owns the final decision.
"""

ENGINE_ORDER = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9")


def _num(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _bar_is_closed(bar: dict[str, Any]) -> bool:
    """Accept explicit closure metadata when supplied; never accept an explicit open flag."""
    for key in ("is_closed", "closed", "complete", "is_complete", "closed_candle", "candle_closed"):
        if key in bar:
            return bool(bar.get(key))
    # Runtime/replay invokes the pipeline only on a new closed candle.  In the
    # absence of a per-bar flag, the snapshot is therefore treated as the
    # already-frozen closed-candle dataset supplied by the caller.
    return True


def _bar_identity(bar: dict[str, Any]) -> str | None:
    value = bar.get("id") or bar.get("candle_id") or bar.get("timestamp") or bar.get("time")
    return str(value) if value is not None else None


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
    """Freeze the exact evidence cutoff and remove any candle beyond it."""
    if market_data.get("closed_candle_only") is False:
        raise ValueError("SHARED_MARKET_PICTURE_REQUIRES_CLOSED_CANDLE_ONLY")
    if market_data.get("lookahead_allowed") is True:
        raise ValueError("SHARED_MARKET_PICTURE_REJECTS_LOOKAHEAD")

    cutoff_id = market_data.get("data_cutoff_candle_id")
    cutoff_ts = market_data.get("data_cutoff_timestamp")
    if cutoff_id is not None:
        cutoff_id = str(cutoff_id)
        indexed = {(_bar_identity(bar)): i for i, bar in enumerate(bars)}
        if cutoff_id not in indexed:
            raise ValueError("DATA_CUTOFF_CANDLE_NOT_FOUND")
        bars = bars[: indexed[cutoff_id] + 1]
    elif cutoff_ts is not None:
        cutoff_ts = str(cutoff_ts)
        selected = []
        for bar in bars:
            ts = bar.get("timestamp") or bar.get("time")
            if ts is None or str(ts) <= cutoff_ts:
                selected.append(bar)
        bars = selected

    if not bars:
        raise ValueError("NO_CLOSED_CANDLE_EVIDENCE")
    if not _bar_is_closed(bars[-1]):
        raise ValueError("CLOSED_CANDLE_BOUNDARY_VIOLATION")

    # Mutate the caller's list in-place so every downstream consumer of the
    # same snapshot receives exactly this frozen closed-candle view.
    source_bars = market_data.get("bars")
    if isinstance(source_bars, list):
        source_bars[:] = bars
    market_data["bars"] = bars
    market_data["data_cutoff_candle_id"] = _bar_identity(bars[-1])
    market_data["data_cutoff_timestamp"] = bars[-1].get("timestamp") or bars[-1].get("time")
    market_data["closed_candle_only"] = True
    market_data["lookahead_allowed"] = False
    return bars


def _atr(bars: list[dict[str, Any]], n: int = 14) -> float:
    if len(bars) < n:
        return 0.0
    values = []
    previous = None
    for bar in bars[-n:]:
        h, l, c = bar["high"], bar["low"], bar["close"]
        values.append(max(h - l, abs(h - previous), abs(l - previous)) if previous is not None else h - l)
        previous = c
    return mean(values) if values else 0.0


def _ema(values: list[float], n: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (n + 1.0)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def _range(bars: list[dict[str, Any]], n: int) -> tuple[float | None, float | None]:
    if len(bars) < n:
        return None, None
    window = bars[-n:]
    return max(b["high"] for b in window), min(b["low"] for b in window)


def _fact_payload(picture: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": picture.get("symbol"),
        "timeframe": picture.get("timeframe"),
        "candle_identity": picture.get("candle_identity"),
        "data_cutoff_candle_id": picture.get("data_cutoff_candle_id"),
        "data_cutoff_timestamp": picture.get("data_cutoff_timestamp"),
        "bar_count": picture.get("bar_count"),
        "current": picture.get("current"),
        "volatility": picture.get("volatility"),
        "trend_context": picture.get("trend_context"),
        "reference_levels": picture.get("reference_levels"),
        "data_integrity": picture.get("data_integrity"),
    }


def _picture_id(picture: dict[str, Any]) -> str:
    payload = json.dumps(_fact_payload(picture), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _fact_fields(picture: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": picture["symbol"],
        "timeframe": picture["timeframe"],
        "candle_identity": picture["candle_identity"],
        "data_cutoff_candle_id": picture["data_cutoff_candle_id"],
        "data_cutoff_timestamp": picture["data_cutoff_timestamp"],
        "bar_count": picture["bar_count"],
        "current": picture["current"],
        "volatility.atr14": picture["volatility"]["atr14"],
        "trend_context.ema20": picture["trend_context"]["ema20"],
        "trend_context.ema50": picture["trend_context"]["ema50"],
        "trend_context.ema20_vs_ema50": picture["trend_context"]["ema20_vs_ema50"],
        "trend_context.ema_gap_atr": picture["trend_context"]["ema_gap_atr"],
        "reference_levels": picture["reference_levels"],
        "data_integrity": picture["data_integrity"],
    }


def build_shared_market_picture(market_data: dict[str, Any]) -> dict[str, Any]:
    """Build one frozen factual picture from closed candles only."""
    source_bars = list(market_data.get("bars") or [])
    bars = _clean_bars(source_bars)
    bars = _freeze_closed_candle_boundary(market_data, bars)
    closes = [b["close"] for b in bars]
    last = bars[-1]
    atr14 = _atr(bars, 14)
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    range20_high, range20_low = _range(bars, 20)
    range50_high, range50_low = _range(bars, 50)
    candle_id = _bar_identity(last)

    picture = {
        "schema": "SHARED_MARKET_PICTURE_V3",
        "scope": "ONE_CLOSED_M5_CYCLE",
        "symbol": str(market_data.get("symbol") or "UNKNOWN"),
        "timeframe": str(market_data.get("timeframe") or "M5"),
        "data_cutoff_candle_id": str(_bar_identity(last)),
        "data_cutoff_timestamp": last.get("timestamp") or last.get("time"),
        "closed_candle_only": True,
        "lookahead_allowed": False,
        "lookahead_detected": False,
        "candle_identity": str(candle_id) if candle_id is not None else None,
        "bar_count": len(bars),
        "current": {"open": last.get("open"), "high": last.get("high"), "low": last.get("low"), "close": last.get("close")},
        "volatility": {"atr14": atr14},
        "trend_context": {"ema20": ema20, "ema50": ema50, "ema20_vs_ema50": "UP" if ema20 > ema50 else "DOWN" if ema20 < ema50 else "FLAT", "ema_gap_atr": ((ema20 - ema50) / atr14) if atr14 > 0 else 0.0},
        "reference_levels": {"range20_high": range20_high, "range20_low": range20_low, "range50_high": range50_high, "range50_low": range50_low},
        "data_integrity": {"valid_ohlc_bars": len(bars), "source_bars": len(source_bars), "sufficient_for_context": len(bars) >= 50, "all_visible_bars_closed": all(_bar_is_closed(bar) for bar in bars)},
        "shared_truth": ["ALL_BRAINS_USE_THIS_CYCLE_SNAPSHOT", "CLOSED_CANDLE_ONLY", "NO_LOOKAHEAD", "FACTS_ARE_SHARED;_INTERPRETATIONS_REMAIN_BRAIN_SPECIFIC"],
    }
    picture["picture_id"] = _picture_id(picture)
    picture["fact_ledger"] = {"classification": "FACT_ONLY", "authority": "SHARED_MARKET_PICTURE", "interpretation_allowed": False, "fields": _fact_fields(picture), "derivation": "DETERMINISTIC_FROM_FROZEN_CLOSED_OHLC_SNAPSHOT", "fingerprint": picture["picture_id"], "source_ids": [f"CANDLE:{picture['data_cutoff_candle_id']}" ]}
    picture["contract"] = {"schema": "SHARED_MARKET_PICTURE_CONTRACT_V2", "picture_id": picture["picture_id"], "data_cutoff_candle_id": picture["data_cutoff_candle_id"], "data_cutoff_timestamp": picture["data_cutoff_timestamp"], "closed_candle_only": True, "lookahead_detected": False, "fact_source_ids": list(picture["fact_ledger"]["source_ids"]), "interpretation_source_ids": [], "decision_source_ids": [], "fact_mutation": "FORBIDDEN", "interpretation_location": "BRAIN_OUTPUT_ONLY", "decision_authority": "E9_ONLY"}
    return picture


FIELD_OF_VIEW = {
    "E1": {"role":"MARKET_STATE","sees":["data_integrity","volatility","market_structure_context","directional_pressure","persistence","regime","transition","state_stability","counter_evidence"],"does_not_own":["setup","entry","target","stop","trade_economics","execution","final_decision"]},
    "E2": {"role":"OPPORTUNITY_REGIME","sees":["shared_market_picture","E1_evidence","regime","auction_context","candidate_opportunity_paths","opportunity_maturity"],"does_not_own":["final_entry","risk_authority","final_decision"]},
    "E3": {"role":"MARKET_STRUCTURE","sees":["shared_market_picture","confirmed_pivots","protected_levels","BOS","CHOCH","structure_lifecycle","structure_invalidation"],"does_not_own":["opportunity_selection","entry","RR","risk","final_decision"]},
    "E4": {"role":"LIQUIDITY_AUCTION","sees":["shared_market_picture","structure_context","liquidity_zones","sweeps","failed_breaks","auction_taker","response_actor","acceptance_rejection"],"does_not_own":["setup_creation","final_direction","trade_economics","final_decision"]},
    "E5": {"role":"LOCATION_VALUE","sees":["shared_market_picture","value","premium_discount","structural_location","support_resistance","available_space","extension","counter_evidence"],"does_not_own":["entry_confirmation","risk_authority","final_decision"]},
    "E6": {"role":"SETUP_FORMATION","sees":["shared_market_picture","E1_to_E5_evidence","candidate_setup","directional_conflict","setup_lifecycle","required_proof"],"does_not_own":["confirmation_authority","trade_economics","final_decision"]},
    "E7": {"role":"CONFIRMATION","sees":["shared_market_picture","E4_evidence","E6_thesis","closed_candle_trigger","follow_through","invalidation","missing_proof"],"does_not_own":["creating_the_thesis","risk_authority","final_decision"]},
    "E8": {"role":"TRADE_ECONOMICS_RISK","sees":["shared_market_picture","E5_location","E6_setup","E7_confirmation","entry","stop","target","RR","structural_survival","execution_uncertainty","probability_quality"],"does_not_own":["creating_market_thesis","overriding_structure","final_decision"]},
    "E9": {"role":"MASTER_MARKET_CONTROL","sees":["shared_market_picture","E1_to_E8_evidence","cross_brain_conflicts","active_invalidations","opportunity_maturity","trade_economics","governance"],"does_not_own":["inventing_missing_evidence","rewriting_upstream_facts","bypassing_risk","lookahead"]},
}


def _interpretation_payload(output: dict[str, Any]) -> dict[str, Any]:
    keys = ("finding","observations","reasons","reason_codes","counter_evidence","missing_evidence","conflicts","invalidations")
    return {key: output[key] for key in keys if key in output}


def _local_decision(output: dict[str, Any]) -> Any:
    for key in ("decision", "finding", "gate_passed", "confirmation", "state"):
        if key in output:
            return output[key]
    return None


def attach_brain_view(engine_id: str, output: dict[str, Any], shared: dict[str, Any]) -> dict[str, Any]:
    if engine_id not in FIELD_OF_VIEW:
        raise ValueError(f"Unknown engine_id: {engine_id}")
    view = FIELD_OF_VIEW[engine_id]
    result = dict(output or {})
    picture_id = shared.get("picture_id")
    result["shared_market_picture"] = shared
    result["field_of_view"] = {"role":view["role"],"sees":list(view["sees"]),"does_not_own":list(view["does_not_own"]),"boundary_rule":"DESCRIBE_ONLY_WHAT_THIS_BRAIN_HAS_EVIDENCE_AND_AUTHORITY_TO_SEE"}
    result["market_picture_contract"] = {"schema":"SHARED_MARKET_PICTURE_CONTRACT_V2","picture_id":picture_id,"data_cutoff_candle_id":shared.get("data_cutoff_candle_id"),"data_cutoff_timestamp":shared.get("data_cutoff_timestamp"),"closed_candle_only":shared.get("closed_candle_only") is True,"lookahead_allowed":shared.get("lookahead_allowed") is True,"lookahead_detected":shared.get("lookahead_detected") is True,"fact_source_ids":list((shared.get("contract") or {}).get("fact_source_ids") or []),"interpretation_source_ids":[engine_id],"decision_source_ids":[engine_id],"fact_authority":"SHARED_MARKET_PICTURE","fact_mutation":"FORBIDDEN","interpretation_authority":"BRAIN_ROLE_ONLY","decision_authority":"E9_ONLY"}
    result["evidence_audit"] = {"facts":{"source":"SHARED_MARKET_PICTURE","picture_id":picture_id,"classification":"FACT","source_ids":list((shared.get("contract") or {}).get("fact_source_ids") or []),"fields":dict((shared.get("fact_ledger") or {}).get("fields") or {})},"interpretation":{"source":engine_id,"classification":"INTERPRETATION","source_ids":[engine_id],"role":view["role"],**_interpretation_payload(result)},"decision":{"source":engine_id,"classification":"DECISION","source_ids":[engine_id],"scope":view["role"],"value":_local_decision(result),"final_authority":engine_id == "E9"}}
    result["view_contract"] = "SHARED_FACTS + BRAIN_SPECIFIC_INTERPRETATION + BRAIN_LOCAL_DECISION + EXPLICIT_BOUNDARY"
    return result


def audit_shared_market_picture_contract(outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Hard contract audit across E1-E9. Any violation is a governance blocker."""
    covered = [eid for eid in ENGINE_ORDER if isinstance(outputs.get(eid), dict)]
    missing: list[str] = []
    violations: list[str] = []
    violating_brains: list[str] = []
    picture_ids: dict[str, str] = {}
    cutoff_ids: dict[str, str] = {}
    cutoff_timestamps: dict[str, str] = {}
    for engine_id in covered:
        output = outputs[engine_id]
        shared = output.get("shared_market_picture")
        contract = output.get("market_picture_contract")
        audit = output.get("evidence_audit")
        if not isinstance(shared, dict) or not isinstance(contract, dict) or not isinstance(audit, dict):
            missing.append(engine_id); continue
        declared_id = contract.get("picture_id")
        actual_id = _picture_id(shared)
        picture_ids[engine_id] = str(declared_id)
        cutoff_ids[engine_id] = str(contract.get("data_cutoff_candle_id"))
        cutoff_timestamps[engine_id] = str(contract.get("data_cutoff_timestamp"))
        brain_violations = []
        if contract.get("closed_candle_only") is not True: brain_violations.append("CLOSED_CANDLE_CONTRACT_VIOLATION")
        if contract.get("lookahead_allowed") is True or contract.get("lookahead_detected") is True: brain_violations.append("LOOKAHEAD_CONTRACT_VIOLATION")
        if shared.get("closed_candle_only") is not True or shared.get("lookahead_detected") is not False: brain_violations.append("SHARED_BOUNDARY_VIOLATION")
        if declared_id != shared.get("picture_id") or actual_id != shared.get("picture_id"): brain_violations.append("FACT_PICTURE_TAMPERED")
        if shared.get("data_cutoff_candle_id") != contract.get("data_cutoff_candle_id"): brain_violations.append("CUTOFF_CANDLE_MISMATCH")
        if shared.get("data_cutoff_timestamp") != contract.get("data_cutoff_timestamp"): brain_violations.append("CUTOFF_TIMESTAMP_MISMATCH")
        if (audit.get("facts") or {}).get("classification") != "FACT": brain_violations.append("FACT_CLASSIFICATION_MISSING")
        if (audit.get("interpretation") or {}).get("classification") != "INTERPRETATION": brain_violations.append("INTERPRETATION_CLASSIFICATION_MISSING")
        if (audit.get("decision") or {}).get("classification") != "DECISION": brain_violations.append("DECISION_CLASSIFICATION_MISSING")
        if brain_violations:
            violating_brains.append(engine_id); violations.extend(f"{engine_id}:{item}" for item in brain_violations)
    issues: list[str] = []
    if missing: issues.append("SHARED_PICTURE_CONTRACT_MISSING")
    if len(set(picture_ids.values())) > 1: issues.append("MULTIPLE_SHARED_PICTURES")
    if len(set(cutoff_ids.values())) > 1: issues.append("MULTIPLE_DATA_CUTOFF_CANDLES")
    if len(set(cutoff_timestamps.values())) > 1: issues.append("MULTIPLE_DATA_CUTOFF_TIMESTAMPS")
    if violations: issues.extend(sorted(set(violations)))
    if covered and len(covered) != len(ENGINE_ORDER): issues.append("INCOMPLETE_BRAIN_COVERAGE")
    return {"schema":"SHARED_MARKET_PICTURE_AUDIT_V2","passed":not issues,"covered_brains":covered,"expected_brains":list(ENGINE_ORDER),"unique_picture_ids":sorted(set(picture_ids.values())),"unique_cutoff_candle_ids":sorted(set(cutoff_ids.values())),"unique_cutoff_timestamps":sorted(set(cutoff_timestamps.values())),"violating_brains":sorted(set(violating_brains)),"missing_contract_brains":missing,"issues":sorted(set(issues)),"authority":"HARD_GOVERNANCE_INPUT","decision_authority":"E9_ONLY","rule":"NO_BRAIN_MAY_USE_OPEN_CANDLE_OR_LOOKAHEAD_FOR_FACT_INTERPRETATION_EVIDENCE_THESIS_OR_DECISION"}
