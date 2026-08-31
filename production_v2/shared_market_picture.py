from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

"""Shared market picture for the nine brains.

This module does not make trade decisions. It creates one immutable-at-cycle
market snapshot so every brain reasons from the same closed-candle reality,
while each brain explicitly declares what it owns and does not own.
"""


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
    return {
        "schema": "SHARED_MARKET_PICTURE_V1",
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


def attach_brain_view(engine_id: str, output: dict[str, Any], shared: dict[str, Any]) -> dict[str, Any]:
    view = FIELD_OF_VIEW[engine_id]
    result = dict(output or {})
    result["shared_market_picture"] = shared
    result["field_of_view"] = {
        "role": view["role"],
        "sees": list(view["sees"]),
        "does_not_own": list(view["does_not_own"]),
        "boundary_rule": "DESCRIBE_ONLY_WHAT_THIS_BRAIN_HAS_EVIDENCE_AND_AUTHORITY_TO_SEE",
    }
    result["view_contract"] = "SHARED_FACTS + BRAIN_SPECIFIC_INTERPRETATION + EXPLICIT_BOUNDARY"
    return result
