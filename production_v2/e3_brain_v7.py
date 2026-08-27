from __future__ import annotations

"""E3 V7 — professional market-structure authority layer.

E3 is a single analysis brain.  It reads closed candles only and never
consumes E1/E2 direction, score, gate, or trade decisions.  External
structure is the market authority; internal structure is tactical evidence.
A wick is not a structural break, and an internal break cannot flip the
external thesis.
"""

from . import e3_brain_v6 as _v6

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_SINGLE_PROFESSIONAL_BRAIN_V7"
UP, DOWN, NEUTRAL, MIXED = _v6.UP, _v6.DOWN, _v6.NEUTRAL, _v6.MIXED
MIN_CANDLES = _v6.MIN_CANDLES

# V7 deliberately uses stricter confirmation than the legacy V6 primitive.
BREAK_CLOSE_ATR = 0.12
BREAK_BODY_ATR = 0.20
BREAK_CLOSE_LOCATION = 0.60


def _strict_break(bar, level, direction, atr):
    if not bar or level is None or atr <= 0:
        return {"confirmed": False, "direction": NEUTRAL}
    rng = max(bar["high"] - bar["low"], 1e-12)
    body_atr = abs(bar["close"] - bar["open"]) / atr
    close_location = (bar["close"] - bar["low"]) / rng
    if direction == UP:
        close_distance = (bar["close"] - level) / atr
        wick_distance = (bar["high"] - level) / atr
        location_ok = close_location >= BREAK_CLOSE_LOCATION
    else:
        close_distance = (level - bar["close"]) / atr
        wick_distance = (level - bar["low"]) / atr
        location_ok = close_location <= 1.0 - BREAK_CLOSE_LOCATION
    close_beyond = close_distance >= BREAK_CLOSE_ATR
    confirmed = bool(close_beyond and (body_atr >= BREAK_BODY_ATR or location_ok))
    return {
        "confirmed": confirmed,
        "direction": direction if confirmed else NEUTRAL,
        "level": level,
        "close_distance_atr": round(max(0.0, close_distance), 4),
        "wick_distance_atr": round(max(0.0, wick_distance), 4),
        "body_atr": round(body_atr, 4),
        "close_location": round(close_location, 4),
        "close_beyond_level": bool(close_beyond),
        "displacement_ok": bool(body_atr >= BREAK_BODY_ATR),
        "break_candle_index": None,
    }


def _protected_levels(external, highs, lows):
    if external == UP:
        protected_low = _v6._latest(lows, {"HL"})
        continuation_high = _v6._latest(highs, {"HH", "EQH"})
        return {"protected_high": continuation_high, "protected_low": protected_low}
    if external == DOWN:
        protected_high = _v6._latest(highs, {"LH"})
        continuation_low = _v6._latest(lows, {"LL", "EQL"})
        return {"protected_high": protected_high, "protected_low": continuation_low}
    return {
        "protected_high": _v6._latest(highs, {"HH", "LH", "EQH"}),
        "protected_low": _v6._latest(lows, {"HL", "LL", "EQL"}),
    }


def _sequence_quality(highs, lows):
    points = sorted(list(highs or []) + list(lows or []), key=lambda x: x["index"])[-10:]
    if len(points) < 4:
        return 0.0, "INSUFFICIENT_SEQUENCE"
    side_changes = 0
    previous = None
    for point in points:
        side = "H" if point["label"] in {"SWING_HIGH", "HH", "LH", "EQH"} else "L"
        if previous is not None and side != previous:
            side_changes += 1
        previous = side
    quality = round(min(1.0, side_changes / max(1, len(points) - 1)), 4)
    return quality, "SEQUENCE_VALID" if quality >= 0.50 else "SEQUENCE_MIXED"


def _external_break(bars, external, highs, lows, atr):
    """Return a market-level break only when a closed candle breaks a relevant external swing."""
    if not bars or atr <= 0 or external not in {UP, DOWN}:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": "EXTERNAL"}
    bar = bars[-1]
    protected = _protected_levels(external, highs, lows)
    candidates = []

    # Continuation BOS: break the latest same-direction external extreme.
    if external == UP:
        point = protected.get("protected_high")
        q = _strict_break(bar, point.get("price") if point else None, UP, atr)
        if q.get("confirmed"):
            q.update({"event": "CONFIRMED_BOS", "scope": "EXTERNAL", "swing_index": point["index"], "swing_label": point["label"]})
            candidates.append(q)
        # Thesis invalidation: break the protected HL. This is CHOCH candidate.
        point = protected.get("protected_low")
        q = _strict_break(bar, point.get("price") if point else None, DOWN, atr)
        if q.get("confirmed"):
            q.update({"event": "CONFIRMED_CHOCH", "scope": "EXTERNAL", "swing_index": point["index"], "swing_label": point["label"]})
            candidates.append(q)
    else:
        point = protected.get("protected_low")
        q = _strict_break(bar, point.get("price") if point else None, DOWN, atr)
        if q.get("confirmed"):
            q.update({"event": "CONFIRMED_BOS", "scope": "EXTERNAL", "swing_index": point["index"], "swing_label": point["label"]})
            candidates.append(q)
        point = protected.get("protected_high")
        q = _strict_break(bar, point.get("price") if point else None, UP, atr)
        if q.get("confirmed"):
            q.update({"event": "CONFIRMED_CHOCH", "scope": "EXTERNAL", "swing_index": point["index"], "swing_label": point["label"]})
            candidates.append(q)

    if not candidates:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": "EXTERNAL"}
    if len(candidates) > 1:
        return {
            "event": "STRUCTURE_CONFLICT",
            "direction": NEUTRAL,
            "confirmed": False,
            "scope": "EXTERNAL",
            "conflict": "BOTH_SIDES_BROKEN_ON_SAME_CANDLE",
            "candidates": candidates,
        }
    chosen = candidates[0]
    chosen["break_candle_index"] = len(bars) - 1
    return chosen


def _internal_break(bars, internal, highs, lows, atr):
    if not bars or atr <= 0 or internal not in {UP, DOWN}:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": "INTERNAL"}
    # Use V6's mature pivot selection for the tactical layer, but the same
    # strict closed-candle confirmation rule as external structure.
    bar = bars[-1]
    point = _v6._latest(highs, {"HH", "LH", "EQH"}) if internal == UP else _v6._latest(lows, {"HL", "LL", "EQL"})
    q = _strict_break(bar, point.get("price") if point else None, internal, atr)
    if not q.get("confirmed"):
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": "INTERNAL"}
    q.update({
        "event": "CONFIRMED_BOS",
        "scope": "INTERNAL",
        "swing_index": point["index"],
        "swing_label": point["label"],
        "break_candle_index": len(bars) - 1,
    })
    return q


def _structure_failure(bars, external, highs, lows, atr):
    """Separate liquidity failure from a genuine structural invalidation."""
    base = _v6._sweep_failure(bars, highs, lows, atr, external)
    if base.get("confirmed"):
        base["type"] = "LIQUIDITY_SWEEP_RECLAIM"
        base["structural_invalidation"] = False
    else:
        base["type"] = "NONE"
        base["structural_invalidation"] = False
    return base


def _state(external, internal, ext_bos, failure, protected_break):
    if protected_break.get("confirmed") and ext_bos.get("event") == "CONFIRMED_CHOCH":
        return "STRUCTURE_INVALIDATED_PENDING_REBUILD"
    if failure.get("confirmed"):
        return "LIQUIDITY_SWEEP_FAILURE"
    if ext_bos.get("confirmed"):
        return "BREAKOUT_CONFIRMED" if ext_bos.get("event") == "CONFIRMED_BOS" else "CHANGE_OF_CHARACTER"
    if external == UP and internal == UP:
        return "BULLISH_CONTINUATION"
    if external == DOWN and internal == DOWN:
        return "BEARISH_CONTINUATION"
    if external == UP:
        return "BULLISH_INTERNAL_COUNTER_STRUCTURE"
    if external == DOWN:
        return "BEARISH_INTERNAL_COUNTER_STRUCTURE"
    if external == MIXED:
        return "STRUCTURE_UNRESOLVED"
    return "RANGE_OR_UNCLEAR"


def _direction(external, ext_bos, protected_break):
    if protected_break.get("confirmed"):
        return NEUTRAL
    if ext_bos.get("confirmed") and ext_bos.get("event") == "CONFIRMED_CHOCH":
        return ext_bos.get("direction", NEUTRAL)
    return external if external in {UP, DOWN} else NEUTRAL


def analyze_e3(bars):
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
    swing_map = base.get("swing_map") or {}
    ext_highs = list(swing_map.get("external_highs") or [])
    ext_lows = list(swing_map.get("external_lows") or [])
    int_highs = list(swing_map.get("internal_highs") or [])
    int_lows = list(swing_map.get("internal_lows") or [])

    protected = _protected_levels(external, ext_highs, ext_lows)
    protected_high = protected.get("protected_high")
    protected_low = protected.get("protected_low")
    ext_bos = _external_break(clean, external, ext_highs, ext_lows, atr)
    int_bos = _internal_break(clean, internal, int_highs, int_lows, atr)
    failure = _structure_failure(clean, external, ext_highs, ext_lows, atr)

    protected_break = {"confirmed": False, "direction": NEUTRAL, "event": "NONE"}
    if external == UP and protected_low:
        q = _strict_break(clean[-1], protected_low["price"], DOWN, atr)
        if q.get("confirmed"):
            protected_break = {**q, "confirmed": True, "direction": DOWN, "event": "PROTECTED_LOW_BREAK", "structural_invalidation": True}
    elif external == DOWN and protected_high:
        q = _strict_break(clean[-1], protected_high["price"], UP, atr)
        if q.get("confirmed"):
            protected_break = {**q, "confirmed": True, "direction": UP, "event": "PROTECTED_HIGH_BREAK", "structural_invalidation": True}

    # A sweep/reclaim has precedence over a raw wick. A true protected close
    # invalidation is still reported separately so E9 can distinguish failure
    # from a market-structure change.
    sequence_quality, sequence_state = _sequence_quality(ext_highs, ext_lows)
    state = _state(external, internal, ext_bos, failure, protected_break)
    direction = _direction(external, ext_bos, protected_break)

    authority = 0.25
    if external in {UP, DOWN}:
        authority = 0.78
        if ext.get("count_state") == external:
            authority += 0.05
        if sequence_quality >= 0.50:
            authority += 0.05
        if internal == external:
            authority += 0.12
        elif int_bos.get("confirmed"):
            authority -= 0.10
    elif external == MIXED:
        authority = 0.40 + 0.15 * sequence_quality
    if protected_break.get("confirmed"):
        authority = min(authority, 0.35)
    authority = round(max(0.20, min(1.0, authority)), 4)

    confidence = 0.48 + 0.30 * authority
    if sequence_quality >= 0.50:
        confidence += 0.05
    if ext_bos.get("confirmed"):
        confidence += 0.10
    if int_bos.get("confirmed") and not ext_bos.get("confirmed"):
        confidence -= 0.05
    if protected_break.get("confirmed"):
        confidence -= 0.15
    confidence = round(max(0.0, min(1.0, confidence)), 4)

    reasons = list(base.get("reason_codes") or [])
    conflicts = list(base.get("conflicts") or [])
    if ext_bos.get("event") == "STRUCTURE_CONFLICT":
        reasons.append("SAME_CANDLE_STRUCTURAL_CONFLICT")
        conflicts.append("BOTH_EXTERNAL_SIDES_BROKEN")
    elif ext_bos.get("confirmed"):
        reasons.append("EXTERNAL_BREAK_HAS_MARKET_AUTHORITY")
    else:
        reasons.append("NO_CONFIRMED_EXTERNAL_BOS")
    if int_bos.get("confirmed") and not ext_bos.get("confirmed"):
        reasons.append("INTERNAL_BREAK_IS_TACTICAL_ONLY")
        conflicts.append("INTERNAL_BOS_CANNOT_OVERRIDE_EXTERNAL_STRUCTURE")
    if external in {UP, DOWN} and internal != external:
        reasons.append("INTERNAL_EXTERNAL_STRUCTURE_DIVERGENCE")
        conflicts.append("INTERNAL_STRUCTURE_VS_EXTERNAL_AUTHORITY")
    if protected_break.get("confirmed"):
        reasons.append("PROTECTED_LEVEL_BROKEN")
        reasons.append("EXTERNAL_THESIS_INVALIDATED_PENDING_REBUILD")
    if failure.get("confirmed"):
        reasons.append("LIQUIDITY_SWEEP_RECLAIM_DETECTED")
    if sequence_quality < 0.50:
        reasons.append("STRUCTURAL_SEQUENCE_WEAK")
    reasons = list(dict.fromkeys(reasons))
    conflicts = list(dict.fromkeys(conflicts))

    all_ext = sorted(ext_highs + ext_lows, key=lambda x: x["index"])
    recent_highs = ext_highs[-2:]
    recent_lows = ext_lows[-2:]
    recent_high = recent_highs[-1] if recent_highs else None
    prior_high = recent_highs[-2] if len(recent_highs) >= 2 else None
    recent_low = recent_lows[-1] if recent_lows else None
    prior_low = recent_lows[-2] if len(recent_lows) >= 2 else None

    finding = f"EXTERNAL_{external}_INTERNAL_{internal}" if external in {UP, DOWN} else f"STRUCTURE_{state}"
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
        f"structure_authority={authority}",
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
        "protected_level_break_invalidates_current_external_thesis": bool(protected_break.get("confirmed")),
        "external_bos_has_market_authority": bool(ext_bos.get("confirmed")),
        "internal_bos_has_market_authority": False,
        "closed_candle_only": True,
        "sequence_quality": sequence_quality,
        "sequence_state": sequence_state,
        "bos_confirmation_rule": "CLOSE_BEYOND_LEVEL_AND_(BODY_DISPLACEMENT_OR_CLOSE_LOCATION)",
    })

    out = dict(base)
    out.update({
        "architecture": ARCHITECTURE,
        "finding": finding,
        "direction": direction,
        "directional_bias": direction,
        "structural_bias": external if external in {UP, DOWN} else NEUTRAL,
        "structure_state": state,
        "structure": state,
        "bos": ext_bos,
        "BOS": ext_bos.get("event", "NO_BOS"),
        "BOS_type": ext_bos.get("event", "NO_BOS"),
        "BOS_level": ext_bos.get("level"),
        "BOS_candle_index": ext_bos.get("break_candle_index"),
        "external_bos": ext_bos.get("event", "NO_BOS"),
        "internal_bos": int_bos.get("event", "NO_BOS"),
        "external_bos_detail": ext_bos,
        "internal_bos_detail": int_bos,
        "structural_failure": failure,
        "failure_type": failure.get("type", "NONE"),
        "failure_level": failure.get("level"),
        "protected_high": protected_high.get("price") if protected_high else None,
        "protected_low": protected_low.get("price") if protected_low else None,
        "protected_levels": {"high": protected_high, "low": protected_low, "invalidation_rule": "UP_BREAKS_PROTECTED_LOW; DOWN_BREAKS_PROTECTED_HIGH"},
        "protected_level_break": protected_break,
        "recent_high": recent_high,
        "prior_high": prior_high,
        "recent_low": recent_low,
        "prior_low": prior_low,
        "structural_sequence": {"quality": sequence_quality, "state": sequence_state, "external_recent": all_ext[-10:]},
        "structure_strength": authority,
        "strength": authority,
        "atr": round(atr, 8),
        "confidence": confidence,
        "reason_codes": reasons,
        "conflicts": conflicts,
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
        "specialists_active": False,
        "specialists_status": "PAUSED",
    })
    if data_reasons:
        out["data_quality_notes"] = data_reasons[:8]
    return out


__all__ = ["analyze_e3"]
