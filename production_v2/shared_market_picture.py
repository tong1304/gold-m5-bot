from __future__ import annotations

import hashlib
import json
from math import isfinite
from statistics import mean
from typing import Any

"""Shared market picture for the nine brains.

This module creates one cycle-level factual snapshot.  The snapshot is the
single source of shared market facts; every brain may interpret those facts
only inside its own role boundary.  The contract is deliberately auditable:
all brains carry the same picture_id, facts are separated from interpretation,
and tampering/mismatches can be detected before E9 governance.
"""

ENGINE_ORDER = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9")


def _num(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _clean_bars(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for raw in bars or []:
        if not isinstance(raw, dict):
            continue
        vals = {k: _num(raw.get(k)) for k in ("open", "high", "low", "close")}
        if any(v is None for v in vals.values()):
            continue
        o, h, l, c = vals.values()
        if h < l or h < max(o, c) or l > min(o, c):
            continue
        out.append({**raw, **vals})
    return out


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
    """Return only objective cycle facts used to fingerprint the picture."""
    return {
        "symbol": picture.get("symbol"),
        "timeframe": picture.get("timeframe"),
        "candle_identity": picture.get("candle_identity"),
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
    """Build one cycle-level factual picture. No setup, trade or direction is invented."""
    bars = _clean_bars(list(market_data.get("bars") or []))
    closes = [b["close"] for b in bars]
    last = bars[-1] if bars else {}
    atr14 = _atr(bars, 14)
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    range20_high, range20_low = _range(bars, 20)
    range50_high, range50_low = _range(bars, 50)

    candle_id = last.get("id") or last.get("timestamp") or last.get("time")
    picture = {
        "schema": "SHARED_MARKET_PICTURE_V2",
        "scope": "ONE_CLOSED_M5_CYCLE",
        "symbol": str(market_data.get("symbol") or "UNKNOWN"),
        "timeframe": str(market_data.get("timeframe") or "M5"),
        "closed_candle_only": True,
        "lookahead_allowed": False,
        "candle_identity": str(candle_id) if candle_id is not None else None,
        "bar_count": len(bars),
        "current": {
            "open": last.get("open"),
            "high": last.get("high"),
            "low": last.get("low"),
            "close": last.get("close"),
        },
        "volatility": {"atr14": atr14},
        "trend_context": {
            "ema20": ema20,
            "ema50": ema50,
            "ema20_vs_ema50": "UP" if ema20 > ema50 else "DOWN" if ema20 < ema50 else "FLAT",
            "ema_gap_atr": ((ema20 - ema50) / atr14) if atr14 > 0 else 0.0,
        },
        "reference_levels": {
            "range20_high": range20_high,
            "range20_low": range20_low,
            "range50_high": range50_high,
            "range50_low": range50_low,
        },
        "data_integrity": {
            "valid_ohlc_bars": len(bars),
            "source_bars": len(market_data.get("bars") or []),
            "sufficient_for_context": len(bars) >= 50,
        },
        "shared_truth": [
            "ALL_BRAINS_USE_THIS_CYCLE_SNAPSHOT",
            "CLOSED_CANDLE_ONLY",
            "NO_LOOKAHEAD",
            "FACTS_ARE_SHARED;_INTERPRETATIONS_REMAIN_BRAIN_SPECIFIC",
        ],
    }
    picture["picture_id"] = _picture_id(picture)
    picture["fact_ledger"] = {
        "classification": "FACT_ONLY",
        "authority": "SHARED_MARKET_PICTURE",
        "interpretation_allowed": False,
        "fields": _fact_fields(picture),
        "derivation": "DETERMINISTIC_FROM_CLOSED_OHLC_SNAPSHOT",
        "fingerprint": picture["picture_id"],
    }
    picture["contract"] = {
        "schema": "SHARED_MARKET_PICTURE_CONTRACT_V1",
        "picture_id": picture["picture_id"],
        "fact_source": "SHARED_MARKET_PICTURE",
        "fact_mutation": "FORBIDDEN",
        "interpretation_location": "BRAIN_OUTPUT_ONLY",
        "decision_authority": "E9_ONLY",
    }
    return picture


FIELD_OF_VIEW = {
    "E1": {
        "role": "MARKET_STATE",
        "sees": ["data_integrity", "volatility", "market_structure_context", "directional_pressure", "persistence", "regime", "transition", "state_stability", "counter_evidence"],
        "does_not_own": ["setup", "entry", "target", "stop", "trade_economics", "execution", "final_decision"],
    },
    "E2": {
        "role": "OPPORTUNITY_REGIME",
        "sees": ["shared_market_picture", "E1_evidence", "regime", "auction_context", "candidate_opportunity_paths", "opportunity_maturity"],
        "does_not_own": ["final_entry", "risk_authority", "final_decision"],
    },
    "E3": {
        "role": "MARKET_STRUCTURE",
        "sees": ["shared_market_picture", "confirmed_pivots", "protected_levels", "BOS", "CHOCH", "structure_lifecycle", "structure_invalidation"],
        "does_not_own": ["opportunity_selection", "entry", "RR", "risk", "final_decision"],
    },
    "E4": {
        "role": "LIQUIDITY_AUCTION",
        "sees": ["shared_market_picture", "structure_context", "liquidity_zones", "sweeps", "failed_breaks", "auction_taker", "response_actor", "acceptance_rejection"],
        "does_not_own": ["setup_creation", "final_direction", "trade_economics", "final_decision"],
    },
    "E5": {
        "role": "LOCATION_VALUE",
        "sees": ["shared_market_picture", "value", "premium_discount", "structural_location", "support_resistance", "available_space", "extension", "counter_evidence"],
        "does_not_own": ["entry_confirmation", "risk_authority", "final_decision"],
    },
    "E6": {
        "role": "SETUP_FORMATION",
        "sees": ["shared_market_picture", "E1_to_E5_evidence", "candidate_setup", "directional_conflict", "setup_lifecycle", "required_proof"],
        "does_not_own": ["confirmation_authority", "trade_economics", "final_decision"],
    },
    "E7": {
        "role": "CONFIRMATION",
        "sees": ["shared_market_picture", "E4_evidence", "E6_thesis", "closed_candle_trigger", "follow_through", "invalidation", "missing_proof"],
        "does_not_own": ["creating_the_thesis", "risk_authority", "final_decision"],
    },
    "E8": {
        "role": "TRADE_ECONOMICS_RISK",
        "sees": ["shared_market_picture", "E5_location", "E6_setup", "E7_confirmation", "entry", "stop", "target", "RR", "structural_survival", "execution_uncertainty", "probability_quality"],
        "does_not_own": ["creating_market_thesis", "overriding_structure", "final_decision"],
    },
    "E9": {
        "role": "MASTER_MARKET_CONTROL",
        "sees": ["shared_market_picture", "E1_to_E8_evidence", "cross_brain_conflicts", "active_invalidations", "opportunity_maturity", "trade_economics", "governance"],
        "does_not_own": ["inventing_missing_evidence", "rewriting_upstream_facts", "bypassing_risk", "lookahead"],
    },
}


def _interpretation_payload(output: dict[str, Any]) -> dict[str, Any]:
    keys = ("finding", "observations", "reasons", "reason_codes", "counter_evidence", "missing_evidence", "conflicts", "invalidations")
    return {key: output[key] for key in keys if key in output}


def attach_brain_view(engine_id: str, output: dict[str, Any], shared: dict[str, Any]) -> dict[str, Any]:
    if engine_id not in FIELD_OF_VIEW:
        raise ValueError(f"Unknown engine_id: {engine_id}")
    view = FIELD_OF_VIEW[engine_id]
    result = dict(output or {})
    picture_id = shared.get("picture_id")
    result["shared_market_picture"] = shared
    result["field_of_view"] = {
        "role": view["role"],
        "sees": list(view["sees"]),
        "does_not_own": list(view["does_not_own"]),
        "boundary_rule": "DESCRIBE_ONLY_WHAT_THIS_BRAIN_HAS_EVIDENCE_AND_AUTHORITY_TO_SEE",
    }
    result["market_picture_contract"] = {
        "schema": "SHARED_MARKET_PICTURE_CONTRACT_V1",
        "picture_id": picture_id,
        "fact_authority": "SHARED_MARKET_PICTURE",
        "fact_mutation": "FORBIDDEN",
        "interpretation_authority": "BRAIN_ROLE_ONLY",
        "decision_authority": "E9_ONLY",
        "closed_candle_only": shared.get("closed_candle_only") is True,
        "lookahead_allowed": shared.get("lookahead_allowed") is True,
    }
    result["evidence_audit"] = {
        "facts": {
            "source": "SHARED_MARKET_PICTURE",
            "picture_id": picture_id,
            "classification": "FACT",
            "fields": dict((shared.get("fact_ledger") or {}).get("fields") or {}),
        },
        "interpretation": {
            "source": engine_id,
            "classification": "INTERPRETATION",
            "role": view["role"],
            **_interpretation_payload(result),
        },
    }
    result["view_contract"] = "SHARED_FACTS + BRAIN_SPECIFIC_INTERPRETATION + EXPLICIT_BOUNDARY"
    return result


def audit_shared_market_picture_contract(outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Contract-level audit: all brains must reference one untampered picture."""
    covered = [eid for eid in ENGINE_ORDER if isinstance(outputs.get(eid), dict)]
    picture_ids: dict[str, str] = {}
    mismatched: list[str] = []
    missing: list[str] = []
    mutated: list[str] = []

    for engine_id in covered:
        output = outputs[engine_id]
        shared = output.get("shared_market_picture")
        contract = output.get("market_picture_contract")
        if not isinstance(shared, dict) or not isinstance(contract, dict):
            missing.append(engine_id)
            continue
        actual_id = _picture_id(shared)
        declared_id = contract.get("picture_id")
        shared_id = shared.get("picture_id")
        if isinstance(declared_id, str):
            picture_ids[engine_id] = declared_id
        if declared_id != shared_id:
            mismatched.append(engine_id)
        if actual_id != shared_id:
            mutated.append(engine_id)

    unique_ids = sorted(set(picture_ids.values()))
    issues: list[str] = []
    if missing:
        issues.append("SHARED_PICTURE_CONTRACT_MISSING")
    if mismatched:
        issues.append("SHARED_PICTURE_ID_MISMATCH")
    if mutated:
        issues.append("SHARED_PICTURE_FACT_TAMPERED")
    if len(unique_ids) > 1:
        issues.append("MULTIPLE_SHARED_PICTURES")
    if covered and len(covered) != len(ENGINE_ORDER):
        issues.append("INCOMPLETE_BRAIN_COVERAGE")

    return {
        "schema": "SHARED_MARKET_PICTURE_AUDIT_V1",
        "passed": not issues,
        "covered_brains": covered,
        "expected_brains": list(ENGINE_ORDER),
        "unique_picture_ids": unique_ids,
        "mismatched_brains": sorted(set(mismatched + mutated)),
        "missing_contract_brains": missing,
        "tampered_brains": mutated,
        "issues": issues,
        "authority": "NON_AUTHORITATIVE_CONTRACT_AUDIT",
        "decision_authority": "E9_ONLY",
    }
