from __future__ import annotations

"""E3 V7 — professional market-structure authority layer.

This layer deliberately leaves E1/E2/E4-E9 untouched.  It builds on the
closed-candle structural primitives of V6, then applies a stricter hierarchy:
EXTERNAL structure is market authority; INTERNAL structure is tactical
information; counts and slope are corroboration only.  An internal BOS/CHOCH
cannot change the external market state.  A structural change requires a
protected-level break on a closed candle and must be distinguishable from a
liquidity sweep/failure.
"""

from typing import Any
from . import e3_brain_v6 as _v6

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_SINGLE_PROFESSIONAL_BRAIN_V7"
UP, DOWN, NEUTRAL, MIXED = _v6.UP, _v6.DOWN, _v6.NEUTRAL, _v6.MIXED
MIN_CANDLES = _v6.MIN_CANDLES


def _last_closed_break(bars, level, direction, atr):
    if not bars or level is None or atr <= 0:
        return {"confirmed": False, "direction": NEUTRAL}
    b = bars[-1]
    if direction == UP:
        distance = (b["close"] - level) / atr
        wick = (b["high"] - level) / atr
    else:
        distance = (level - b["close"]) / atr
        wick = (level - b["low"]) / atr
    q = _v6._quality(b, level, direction, atr)
    return {
        "confirmed": bool(q.get("confirmed")),
        "direction": direction if q.get("confirmed") else NEUTRAL,
        "level": level,
        "close_distance_atr": round(max(0.0, distance), 4),
        "wick_distance_atr": round(max(0.0, wick), 4),
        "body_atr": q.get("body_atr", 0.0),
        "close_location": q.get("close_location", 0.0),
        "break_candle_index": len(bars) - 1,
    }


def _protected_levels(external, external_highs, external_lows):
    # The level that invalidates the current external thesis is the protected
    # opposite-side swing: HL for UP, LH for DOWN.  This is more important
    # than a raw count or the nearest internal pivot.
    if external == UP:
        low = _v6._latest(external_lows, {"HL"})
        high = _v6._latest(external_highs, {"HH", "EQH"})
    elif external == DOWN:
        high = _v6._latest(external_highs, {"LH"})
        low = _v6._latest(external_lows, {"LL", "EQL"})
    else:
        high = _v6._latest(external_highs, {"HH", "LH", "EQH"})
        low = _v6._latest(external_lows, {"HL", "LL", "EQL"})
    return {"protected_high": high, "protected_low": low}


def _sequence_quality(highs, lows):
    points = sorted(list(highs or []) + list(lows or []), key=lambda x: x["index"])
    recent = points[-10:]
    if len(recent) < 4:
        return 0.0, "INSUFFICIENT_SEQUENCE"
    alternations = sum(1 for a, b in zip(recent, recent[1:]) if (a["index"] != b["index"]))
    # Repeated same-side pivots are allowed, but a clean alternating swing
    # sequence receives higher structural quality.
    side_changes = 0
    previous = None
    for p in recent:
        side = "H" if "HIGH" in p["label"] or p["label"] in {"HH", "LH", "EQH"} else "L"
        if previous is not None and side != previous:
            side_changes += 1
        previous = side
    quality = min(1.0, side_changes / max(1, len(recent) - 1))
    return round(quality, 4), "SEQUENCE_VALID" if quality >= 0.50 else "SEQUENCE_MIXED"


def _professional_state(external, internal, ext_bos, int_bos, failure, protected_break):
    if failure.get("confirmed"):
        return "STRUCTURE_FAILURE"
    # External BOS is the only event that may establish a market-level change.
    if ext_bos.get("confirmed"):
        if ext_bos.get("event") == "CONFIRMED_CHOCH":
            return "CHANGE_OF_CHARACTER"
        return "BREAKOUT_CONFIRMED"
    if external in {UP, DOWN}:
        if internal == external:
            return "CONTINUATION"
        if internal in {UP, DOWN, MIXED}:
            return "INTERNAL_COUNTER_STRUCTURE"
    if protected_break.get("confirmed"):
        return "PROTECTED_LEVEL_BREAK_UNRESOLVED"
    if external == MIXED:
        return "STRUCTURE_UNRESOLVED"
    return "RANGE_OR_UNCLEAR"


def analyze_e3(bars):
    # V6 performs OHLC sanitation, pivot discovery and the base structural map.
    base = _v6.analyze_e3(bars)
    if base.get("analysis_status") != "COMPLETE":
        base["architecture"] = ARCHITECTURE
        return base

    clean, data_reasons = _v6._clean_bars(bars)
    atr = float(base.get("atr14") or 0.0)
    ext = base.get("external_structure", {})
    inte = base.get("internal_structure", {})
    external = ext.get("state", NEUTRAL)
    internal = inte.get("state", NEUTRAL)
    ext_highs = list((base.get("swing_map") or {}).get("external_highs") or [])
    ext_lows = list((base.get("swing_map") or {}).get("external_lows") or [])
    int_highs = list((base.get("swing_map") or {}).get("internal_highs") or [])
    int_lows = list((base.get("swing_map") or {}).get("internal_lows") or [])

    protected = _protected_levels(external, ext_highs, ext_lows)
    protected_high = protected.get("protected_high")
    protected_low = protected.get("protected_low")

    # Re-evaluate BOS strictly against the latest external structural level.
    # V6 remains the regression-compatible primitive, while V7 makes the
    # authority explicit and prevents an internal break from becoming a market
    # break.
    ext_bos = dict(base.get("external_bos_detail") or base.get("bos") or {})
    int_bos = dict(base.get("internal_bos_detail") or {})
    protected_up = _last_closed_break(clean, protected_high["price"] if protected_high else None, UP, atr)
    protected_down = _last_closed_break(clean, protected_low["price"] if protected_low else None, DOWN, atr)

    # A protected-level break is an invalidation/change candidate, not an
    # automatic reversal.  The external sequence must also be coherent.
    sequence_quality, sequence_state = _sequence_quality(ext_highs, ext_lows)
    protected_break = {"confirmed": False, "direction": NEUTRAL}
    if external == DOWN and protected_up.get("confirmed"):
        protected_break = {**protected_up, "direction": UP, "event": "PROTECTED_HIGH_BREAK"}
    elif external == UP and protected_down.get("confirmed"):
        protected_break = {**protected_down, "direction": DOWN, "event": "PROTECTED_LOW_BREAK"}

    reasons = list(base.get("reason_codes") or [])
    conflicts = list(base.get("conflicts") or [])

    if ext_bos.get("confirmed"):
        # External BOS/CHOCH is accepted only when it is actually on the
        # external map.  This is the market-level event.
        reasons.append("EXTERNAL_BREAK_HAS_AUTHORITY")
    else:
        reasons.append("NO_CONFIRMED_EXTERNAL_BOS")

    if int_bos.get("confirmed") and not ext_bos.get("confirmed"):
        reasons.append("INTERNAL_BREAK_IS_TACTICAL_ONLY")
        conflicts.append("INTERNAL_BOS_CANNOT_OVERRIDE_EXTERNAL_STRUCTURE")

    if external in {UP, DOWN} and internal != external:
        reasons.append("INTERNAL_EXTERNAL_STRUCTURE_DIVERGENCE")
        conflicts.append("INTERNAL_STRUCTURE_VS_EXTERNAL_AUTHORITY")

    if protected_break.get("confirmed") and not ext_bos.get("confirmed"):
        reasons.append("PROTECTED_LEVEL_BREAK_REQUIRES_EXTERNAL_REBUILD")
        conflicts.append("PROTECTED_BREAK_WITHOUT_EXTERNAL_SEQUENCE_CONFIRMATION")

    if sequence_quality < 0.50:
        reasons.append("STRUCTURAL_SEQUENCE_WEAK")

    # Authority is hierarchical, not an average of signals.
    if external in {UP, DOWN}:
        authority = 0.78
        if internal == external:
            authority += 0.12
        if ext.get("count_state") == external:
            authority += 0.05
        if sequence_quality >= 0.50:
            authority += 0.05
        if int_bos.get("confirmed") and not ext_bos.get("confirmed"):
            authority -= 0.10
        if protected_break.get("confirmed") and not ext_bos.get("confirmed"):
            authority -= 0.15
        authority = max(0.25, min(1.0, authority))
    elif external == MIXED:
        authority = 0.40 + 0.15 * sequence_quality
    else:
        authority = 0.25 + 0.15 * sequence_quality

    state = _professional_state(external, internal, ext_bos, int_bos, base.get("failure") or {}, protected_break)
    # Direction follows the external market thesis whenever one exists. An
    # internal counter-move is never promoted to a trade-direction change.
    direction = external if external in {UP, DOWN} else NEUTRAL
    if external == MIXED and not ext_bos.get("confirmed"):
        direction = NEUTRAL

    if state == "CHANGE_OF_CHARACTER" and ext_bos.get("confirmed"):
        direction = ext_bos.get("direction", direction)

    finding = (
        "EXTERNAL_" + external + "_INTERNAL_" + internal
        if external in {UP, DOWN} else "STRUCTURE_" + state
    )

    confidence = 0.48 + 0.30 * authority
    if sequence_quality >= 0.50:
        confidence += 0.05
    if ext_bos.get("confirmed"):
        confidence += 0.10
    if protected_break.get("confirmed") and not ext_bos.get("confirmed"):
        confidence -= 0.15
    confidence = max(0.0, min(1.0, confidence))

    observations = [
        f"closed_candles={len(clean)}",
        f"atr14={round(atr, 8)}",
        f"external_structure={external}",
        f"internal_structure={internal}",
        f"external_count_state={ext.get('count_state', NEUTRAL)}",
        f"internal_count_state={inte.get('count_state', NEUTRAL)}",
        f"external_bos={ext_bos.get('event', 'NO_BOS')}",
        f"internal_bos={int_bos.get('event', 'NO_BOS')}",
        f"protected_high={protected_high.get('price') if protected_high else None}",
        f"protected_low={protected_low.get('price') if protected_low else None}",
        f"protected_break={protected_break.get('event', 'NONE')}",
        f"sequence_quality={sequence_quality}",
        f"sequence_state={sequence_state}",
        f"structure_authority={round(authority, 4)}",
    ]

    trace = dict(base.get("reasoning_trace") or {})
    trace.update({
        "external_state": external,
        "internal_state": internal,
        "external_is_authority": True,
        "internal_is_tactical_only": True,
        "counts_are_corroboration_only": True,
        "slope_is_structural_authority": False,
        "protected_level_break_is_not_automatic_reversal": True,
        "external_bos_has_market_authority": bool(ext_bos.get("confirmed")),
        "internal_bos_has_market_authority": False,
        "closed_candle_only": True,
        "sequence_quality": sequence_quality,
        "sequence_state": sequence_state,
    })

    out = dict(base)
    out.update({
        "architecture": ARCHITECTURE,
        "finding": finding,
        "direction": direction,
        "structure_state": state,
        "bos": ext_bos,
        "external_bos": ext_bos.get("event", "NO_BOS"),
        "internal_bos": int_bos.get("event", "NO_BOS"),
        "external_bos_detail": ext_bos,
        "internal_bos_detail": int_bos,
        "protected_high": protected_high.get("price") if protected_high else None,
        "protected_low": protected_low.get("price") if protected_low else None,
        "protected_levels": {
            "high": protected_high,
            "low": protected_low,
            "invalidation_rule": "UP_BREAKS_PROTECTED_LOW; DOWN_BREAKS_PROTECTED_HIGH",
        },
        "protected_level_break": protected_break,
        "structural_sequence": {
            "quality": sequence_quality,
            "state": sequence_state,
            "external_recent": sorted(ext_highs + ext_lows, key=lambda x: x["index"])[-10:],
        },
        "structure_strength": round(authority, 4),
        "structure_authority": round(authority, 4),
        "confidence": round(confidence, 4),
        "reason_codes": list(dict.fromkeys(reasons)),
        "conflicts": list(dict.fromkeys(conflicts)),
        "observations": observations,
        "reasoning_trace": trace,
        "upstream_direction_used": False,
        "upstream_decisions_used": False,
        "upstream_gates_used": False,
        "score_used": False,
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
        "decision": None,
        "gate": None,
    })
    if data_reasons:
        out["data_quality_notes"] = data_reasons[:8]
    return out


__all__ = ["analyze_e3"]
