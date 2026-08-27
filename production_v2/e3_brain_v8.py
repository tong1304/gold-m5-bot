from __future__ import annotations

"""E3 V8 — professional market-structure authority brain.

External structure is authoritative. Internal structure, counts and slope are
corroboration only. BOS/CHOCH are confirmed from the correct structural
levels using closed candles. For UP structure, continuation breaks the latest
protected HH and invalidation breaks protected HL. For DOWN structure,
continuation breaks the latest protected LL and invalidation breaks protected
LH. A protected-level break invalidates the current thesis but does not
magically create a new trend. Liquidity sweep/reclaim remains separate.
E3 is analysis-only and never authorizes execution.
"""

from . import e3_brain_v6 as _v6

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_SINGLE_PROFESSIONAL_BRAIN_V8"
UP, DOWN, NEUTRAL, MIXED = _v6.UP, _v6.DOWN, _v6.NEUTRAL, _v6.MIXED
MIN_CANDLES = _v6.MIN_CANDLES
BREAK_CLOSE_ATR = 0.12
BREAK_BODY_ATR = 0.20
BREAK_CLOSE_LOCATION = 0.60


def _break(bar, level, direction, atr):
    if not bar or level is None or atr <= 0:
        return {"confirmed": False, "direction": NEUTRAL}
    rng = max(float(bar["high"]) - float(bar["low"]), 1e-12)
    body_atr = abs(float(bar["close"]) - float(bar["open"])) / atr
    close_location = (float(bar["close"]) - float(bar["low"])) / rng
    distance = ((float(bar["close"]) - float(level)) if direction == UP else (float(level) - float(bar["close"]))) / atr
    close_beyond = distance >= BREAK_CLOSE_ATR
    location_ok = close_location >= BREAK_CLOSE_LOCATION if direction == UP else close_location <= 1.0 - BREAK_CLOSE_LOCATION
    displacement_ok = body_atr >= BREAK_BODY_ATR
    confirmed = bool(close_beyond and (displacement_ok or location_ok))
    return {
        "confirmed": confirmed,
        "direction": direction if confirmed else NEUTRAL,
        "level": float(level),
        "close_distance_atr": round(max(0.0, distance), 4),
        "body_atr": round(body_atr, 4),
        "close_location": round(close_location, 4),
        "close_beyond_level": bool(close_beyond),
        "displacement_ok": bool(displacement_ok),
    }


def _last(xs, labels):
    return next((x for x in reversed(xs or []) if x.get("label") in labels), None)


def _authority_levels(external, highs, lows):
    """Return (continuation_level, invalidation_level) in price-structure terms."""
    if external == UP:
        return _last(highs, {"HH", "EQH"}), _last(lows, {"HL"})
    if external == DOWN:
        return _last(lows, {"LL", "EQL"}), _last(highs, {"LH", "EQH"})
    return None, None


def _protected(external, highs, lows):
    """Return (protected_high, protected_low) for compatibility/output."""
    if external == UP:
        return _last(highs, {"HH", "EQH"}), _last(lows, {"HL"})
    if external == DOWN:
        return _last(highs, {"LH", "EQH"}), _last(lows, {"LL", "EQL"})
    return _last(highs, {"HH", "LH", "EQH"}), _last(lows, {"HL", "LL", "EQL"})


def _sequence_quality(highs, lows):
    points = sorted(list(highs or []) + list(lows or []), key=lambda x: x.get("index", -1))[-12:]
    if len(points) < 4:
        return 0.0, "INSUFFICIENT_SEQUENCE"
    changes = 0
    previous = None
    for point in points:
        side = "H" if point.get("label") in {"SWING_HIGH", "HH", "LH", "EQH"} else "L"
        if previous is not None and side != previous:
            changes += 1
        previous = side
    quality = round(min(1.0, changes / max(1, len(points) - 1)), 4)
    return quality, "SEQUENCE_VALID" if quality >= 0.50 else "SEQUENCE_MIXED"


def _external_event(bar, external, highs, lows, atr, index):
    if not bar or external not in {UP, DOWN} or atr <= 0:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": "EXTERNAL"}

    continuation, invalidation = _authority_levels(external, highs, lows)
    candidates = []

    # Continuation BOS: UP breaks HH; DOWN breaks LL.
    if continuation:
        direction = external
        q = _break(bar, continuation.get("price"), direction, atr)
        if q["confirmed"]:
            candidates.append({**q, "event": "CONFIRMED_BOS", "scope": "EXTERNAL", "swing_index": continuation["index"], "swing_label": continuation["label"], "break_candle_index": index, "structural_role": "CONTINUATION"})

    # Structural invalidation / CHOCH: UP breaks HL; DOWN breaks LH.
    if invalidation:
        direction = DOWN if external == UP else UP
        q = _break(bar, invalidation.get("price"), direction, atr)
        if q["confirmed"]:
            candidates.append({**q, "event": "CONFIRMED_CHOCH", "scope": "EXTERNAL", "swing_index": invalidation["index"], "swing_label": invalidation["label"], "break_candle_index": index, "structural_role": "INVALIDATION"})

    if not candidates:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": "EXTERNAL"}
    if len(candidates) > 1:
        return {"event": "STRUCTURE_CONFLICT", "direction": NEUTRAL, "confirmed": False, "scope": "EXTERNAL", "conflict": "BOTH_EXTERNAL_LEVELS_BROKEN_ON_SAME_CLOSED_CANDLE", "candidates": candidates}
    return candidates[0]


def _internal_event(bar, internal, highs, lows, atr, index):
    if not bar or internal not in {UP, DOWN} or atr <= 0:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": "INTERNAL"}
    point = _last(highs, {"HH", "LH", "EQH"}) if internal == UP else _last(lows, {"HL", "LL", "EQL"})
    q = _break(bar, point.get("price") if point else None, internal, atr)
    if not q["confirmed"]:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": "INTERNAL"}
    return {**q, "event": "CONFIRMED_BOS", "scope": "INTERNAL", "swing_index": point["index"], "swing_label": point["label"], "break_candle_index": index}


def analyze_e3(bars):
    base = _v6.analyze_e3(bars)
    if base.get("analysis_status") != "COMPLETE":
        base["architecture"] = ARCHITECTURE
        return base
    clean, data_reasons = _v6._clean_bars(bars)
    if not clean:
        base["architecture"] = ARCHITECTURE
        return base

    atr = float(base.get("atr14") or 0.0)
    ext = base.get("external_structure") or {}
    internal_info = base.get("internal_structure") or {}
    external = ext.get("state", NEUTRAL)
    internal = internal_info.get("state", NEUTRAL)
    sm = base.get("swing_map") or {}
    eh, el = list(sm.get("external_highs") or []), list(sm.get("external_lows") or [])
    ih, il = list(sm.get("internal_highs") or []), list(sm.get("internal_lows") or [])

    seq_q, seq_state = _sequence_quality(eh, el)
    ext_event = _external_event(clean[-1], external, eh, el, atr, len(clean) - 1)
    int_event = _internal_event(clean[-1], internal, ih, il, atr, len(clean) - 1)
    protected_high, protected_low = _protected(external, eh, el)

    protected_break = {"confirmed": False, "event": "NONE", "direction": NEUTRAL, "structural_invalidation": False}
    if external == UP and protected_low:
        q = _break(clean[-1], protected_low["price"], DOWN, atr)
        if q["confirmed"]:
            protected_break = {**q, "event": "PROTECTED_LOW_BREAK", "direction": DOWN, "structural_invalidation": True}
    elif external == DOWN and protected_high:
        q = _break(clean[-1], protected_high["price"], UP, atr)
        if q["confirmed"]:
            protected_break = {**q, "event": "PROTECTED_HIGH_BREAK", "direction": UP, "structural_invalidation": True}

    sweep = _v6._sweep_failure(clean, eh, el, atr, external)
    sweep = {**sweep, "type": "LIQUIDITY_SWEEP_RECLAIM" if sweep.get("confirmed") else "NONE", "structural_invalidation": False}

    if protected_break["confirmed"]:
        state, direction = "STRUCTURE_INVALIDATED_PENDING_REBUILD", NEUTRAL
    elif sweep.get("confirmed"):
        state, direction = "LIQUIDITY_SWEEP_FAILURE", external if external in {UP, DOWN} else NEUTRAL
    elif ext_event.get("event") == "CONFIRMED_CHOCH":
        state, direction = "CHANGE_OF_CHARACTER", ext_event.get("direction", NEUTRAL)
    elif ext_event.get("event") == "CONFIRMED_BOS":
        state, direction = "BREAKOUT_CONFIRMED", external
    elif ext_event.get("event") == "STRUCTURE_CONFLICT":
        state, direction = "STRUCTURE_CONFLICT", NEUTRAL
    elif external in {UP, DOWN} and internal == external:
        state, direction = ("BULLISH_CONTINUATION", UP) if external == UP else ("BEARISH_CONTINUATION", DOWN)
    elif external in {UP, DOWN}:
        state, direction = ("BULLISH_INTERNAL_COUNTER_STRUCTURE", UP) if external == UP else ("BEARISH_INTERNAL_COUNTER_STRUCTURE", DOWN)
    elif external == MIXED:
        state, direction = "STRUCTURE_UNRESOLVED", NEUTRAL
    else:
        state, direction = "RANGE_OR_UNCLEAR", NEUTRAL

    count_ext = ext.get("count_state", NEUTRAL)
    count_int = internal_info.get("count_state", NEUTRAL)
    reasons = list(base.get("reason_codes") or [])
    conflicts = list(base.get("conflicts") or [])

    if external in {UP, DOWN} and count_ext != external:
        reasons.append("EXTERNAL_COUNT_IS_CORROBORATION_ONLY")
        conflicts.append("COUNT_STRUCTURE_DIVERGENCE_REQUIRES_REVIEW")
    if internal in {UP, DOWN} and count_int != internal:
        reasons.append("INTERNAL_COUNT_IS_CORROBORATION_ONLY")
    if external in {UP, DOWN} and internal != external:
        reasons.append("INTERNAL_EXTERNAL_STRUCTURE_DIVERGENCE")
        conflicts.append("INTERNAL_CANNOT_OVERRIDE_EXTERNAL_AUTHORITY")
    if ext_event.get("event") == "STRUCTURE_CONFLICT":
        reasons.append("SAME_CANDLE_STRUCTURAL_CONFLICT")
        conflicts.append("BOTH_EXTERNAL_LEVELS_BROKEN")
    elif ext_event.get("confirmed"):
        reasons.append("EXTERNAL_BREAK_HAS_MARKET_AUTHORITY")
    else:
        reasons.append("NO_CONFIRMED_EXTERNAL_BOS")
    if int_event.get("confirmed") and not ext_event.get("confirmed"):
        reasons.append("INTERNAL_BREAK_IS_TACTICAL_ONLY")
    if protected_break["confirmed"]:
        reasons.extend(["PROTECTED_LEVEL_BROKEN", "EXTERNAL_THESIS_INVALIDATED_PENDING_REBUILD"])
    if sweep.get("confirmed"):
        reasons.append("LIQUIDITY_SWEEP_RECLAIM_DETECTED")
    if seq_q < 0.50:
        reasons.append("STRUCTURAL_SEQUENCE_WEAK")
    reasons = list(dict.fromkeys(reasons))
    conflicts = list(dict.fromkeys(conflicts))

    authority = 0.25
    if external in {UP, DOWN}:
        authority = 0.78 + (0.07 if seq_q >= 0.50 else 0.0) + (0.03 if count_ext == external else 0.0)
        authority += 0.10 if internal == external else (-0.10 if int_event.get("confirmed") else 0.0)
    elif external == MIXED:
        authority = 0.40 + 0.15 * seq_q
    if protected_break["confirmed"]:
        authority = min(authority, 0.35)
    authority = round(max(0.20, min(1.0, authority)), 4)

    confidence = 0.48 + 0.30 * authority
    if seq_q >= 0.50:
        confidence += 0.05
    if ext_event.get("confirmed"):
        confidence += 0.10
    if int_event.get("confirmed") and not ext_event.get("confirmed"):
        confidence -= 0.05
    if protected_break["confirmed"]:
        confidence -= 0.15
    confidence = round(max(0.0, min(1.0, confidence)), 4)

    finding = f"EXTERNAL_{external}_INTERNAL_{internal}" if external in {UP, DOWN} else f"STRUCTURE_{state}"
    observations = [
        f"closed_candles={len(clean)}", f"atr14={round(atr, 8)}",
        f"external_structure={external}", f"internal_structure={internal}",
        f"external_count_state={count_ext}", f"internal_count_state={count_int}",
        f"external_bos={ext_event.get('event', 'NO_BOS')}", f"internal_bos={int_event.get('event', 'NO_BOS')}",
        f"protected_high={protected_high.get('price') if protected_high else None}",
        f"protected_low={protected_low.get('price') if protected_low else None}",
        f"protected_break={protected_break.get('event', 'NONE')}",
        f"sequence_quality={seq_q}", f"sequence_state={seq_state}", f"structure_authority={authority}",
    ]
    trace = dict(base.get("reasoning_trace") or {})
    trace.update({
        "external_is_authority": True,
        "internal_is_tactical_only": True,
        "counts_are_corroboration_only": True,
        "slope_is_corroboration_only": True,
        "closed_candle_only": True,
        "protected_level_break_invalidates_current_thesis": bool(protected_break["confirmed"]),
        "protected_level_break_does_not_create_new_trend": True,
        "liquidity_sweep_is_not_structural_invalidation": True,
        "sequence_quality": seq_q,
        "sequence_state": seq_state,
        "bos_confirmation_rule": "CLOSE_BEYOND_LEVEL_AND_(BODY_DISPLACEMENT_OR_CLOSE_LOCATION)",
        "external_bos_authority_levels": "UP=HH_CONTINUATION/HL_INVALIDATION; DOWN=LL_CONTINUATION/LH_INVALIDATION",
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
        "bos": ext_event,
        "BOS": ext_event.get("event", "NO_BOS"),
        "BOS_type": ext_event.get("event", "NO_BOS"),
        "BOS_level": ext_event.get("level"),
        "BOS_candle_index": ext_event.get("break_candle_index"),
        "external_bos": ext_event.get("event", "NO_BOS"),
        "internal_bos": int_event.get("event", "NO_BOS"),
        "external_bos_detail": ext_event,
        "internal_bos_detail": int_event,
        "structural_failure": sweep,
        "failure_type": sweep.get("type", "NONE"),
        "failure_level": sweep.get("level"),
        "protected_high": protected_high.get("price") if protected_high else None,
        "protected_low": protected_low.get("price") if protected_low else None,
        "protected_levels": {"high": protected_high, "low": protected_low, "invalidation_rule": "UP_BREAKS_PROTECTED_LOW; DOWN_BREAKS_PROTECTED_HIGH"},
        "protected_level_break": protected_break,
        "structural_sequence": {"quality": seq_q, "state": seq_state, "external_recent": sorted(eh + el, key=lambda x: x.get("index", -1))[-10:]},
        "structure_strength": authority,
        "strength": authority,
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
