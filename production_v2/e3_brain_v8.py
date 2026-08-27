from __future__ import annotations

"""E3 professional market-structure authority brain.

Analysis only: never consumes upstream decisions and never authorizes execution.
External structure is authoritative; internal structure/counts/slope are evidence.
All break decisions use the latest closed candle.
"""

from . import e3_brain_v6 as _v6

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_SINGLE_PROFESSIONAL_BRAIN_V8"
UP, DOWN, NEUTRAL, MIXED = _v6.UP, _v6.DOWN, _v6.NEUTRAL, _v6.MIXED
MIN_CANDLES = _v6.MIN_CANDLES
BREAK_CLOSE_ATR = 0.12
BREAK_BODY_ATR = 0.20
BREAK_CLOSE_LOCATION = 0.60
MIN_SEQUENCE_QUALITY = 0.50


def _break(bar, level, direction, atr):
    if not bar or level is None or atr <= 0 or direction not in {UP, DOWN}:
        return {"confirmed": False, "direction": NEUTRAL, "reason": "INVALID_BREAK_INPUT"}
    h, l, c, o = map(float, (bar["high"], bar["low"], bar["close"], bar["open"]))
    rng = max(h - l, 1e-12)
    body_atr = abs(c - o) / atr
    location = (c - l) / rng
    distance = ((c - float(level)) if direction == UP else (float(level) - c)) / atr
    beyond = distance >= BREAK_CLOSE_ATR
    location_ok = location >= BREAK_CLOSE_LOCATION if direction == UP else location <= 1.0 - BREAK_CLOSE_LOCATION
    displacement = body_atr >= BREAK_BODY_ATR
    confirmed = bool(beyond and (displacement or location_ok))
    return {"confirmed": confirmed, "direction": direction if confirmed else NEUTRAL,
            "level": float(level), "close_distance_atr": round(max(0.0, distance), 4),
            "body_atr": round(body_atr, 4), "close_location": round(location, 4),
            "close_beyond_level": bool(beyond), "displacement_ok": bool(displacement),
            "close_location_ok": bool(location_ok), "wick_only": not beyond}


def _last(points, labels):
    return next((x for x in reversed(points or []) if x.get("label") in labels), None)


def _authority_levels(external, highs, lows):
    if external == UP:
        return _last(highs, {"HH", "EQH"}), _last(lows, {"HL"})
    if external == DOWN:
        return _last(lows, {"LL", "EQL"}), _last(highs, {"LH", "EQH"})
    return None, None


def _protected(external, highs, lows):
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
    prev = None
    for p in points:
        side = "H" if p.get("label") in {"SWING_HIGH", "HH", "LH", "EQH"} else "L"
        changes += int(prev is not None and side != prev)
        prev = side
    q = round(min(1.0, changes / max(1, len(points) - 1)), 4)
    return q, "SEQUENCE_VALID" if q >= MIN_SEQUENCE_QUALITY else "SEQUENCE_MIXED"


def _external_event(bar, external, highs, lows, atr, index):
    if not bar or external not in {UP, DOWN} or atr <= 0:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": "EXTERNAL"}
    continuation, invalidation = _authority_levels(external, highs, lows)
    candidates = []
    if continuation:
        q = _break(bar, continuation["price"], external, atr)
        if q["confirmed"]:
            candidates.append({**q, "event": "CONFIRMED_BOS", "scope": "EXTERNAL", "structural_role": "CONTINUATION", "swing_index": continuation["index"], "swing_label": continuation["label"], "break_candle_index": index})
    if invalidation:
        opposite = DOWN if external == UP else UP
        q = _break(bar, invalidation["price"], opposite, atr)
        if q["confirmed"]:
            candidates.append({**q, "event": "CONFIRMED_CHOCH", "scope": "EXTERNAL", "structural_role": "INVALIDATION", "swing_index": invalidation["index"], "swing_label": invalidation["label"], "break_candle_index": index})
    if len(candidates) == 2:
        return {"event": "STRUCTURE_CONFLICT", "direction": NEUTRAL, "confirmed": False, "scope": "EXTERNAL", "conflict": "BOTH_EXTERNAL_LEVELS_BROKEN_ON_SAME_CLOSED_CANDLE", "candidates": candidates}
    return candidates[0] if candidates else {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": "EXTERNAL"}


def _internal_event(bar, internal, highs, lows, atr, index):
    if not bar or internal not in {UP, DOWN} or atr <= 0:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": "INTERNAL"}
    point = _last(highs, {"HH", "LH", "EQH"}) if internal == UP else _last(lows, {"HL", "LL", "EQL"})
    q = _break(bar, point["price"] if point else None, internal, atr)
    if not q["confirmed"]:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": "INTERNAL"}
    return {**q, "event": "CONFIRMED_BOS", "scope": "INTERNAL", "structural_role": "TACTICAL", "swing_index": point["index"], "swing_label": point["label"], "break_candle_index": index}


def analyze_e3(bars):
    base = _v6.analyze_e3(bars)
    base["architecture"] = ARCHITECTURE
    if base.get("analysis_status") != "COMPLETE":
        return base
    clean, _ = _v6._clean_bars(bars)
    atr = float(base.get("atr14") or 0.0)
    ext_info, int_info = base.get("external_structure") or {}, base.get("internal_structure") or {}
    external, internal = ext_info.get("state", NEUTRAL), int_info.get("state", NEUTRAL)
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
    elif ext_event["event"] == "STRUCTURE_CONFLICT":
        state, direction = "STRUCTURE_CONFLICT", NEUTRAL
    elif ext_event.get("event") == "CONFIRMED_CHOCH":
        state, direction = "CHANGE_OF_CHARACTER", ext_event["direction"]
    elif ext_event.get("event") == "CONFIRMED_BOS":
        state, direction = "BREAKOUT_CONFIRMED", external
    elif external in {UP, DOWN}:
        direction = external
        if internal == external:
            state = "BULLISH_CONTINUATION" if external == UP else "BEARISH_CONTINUATION"
        elif internal in {UP, DOWN}:
            state = "INTERNAL_COUNTER_STRUCTURE"
        else:
            state = "EXTERNAL_DIRECTION_INTERNAL_MIXED"
    elif internal in {UP, DOWN}:
        state, direction = "INTERNAL_DIRECTION_EXTERNAL_UNRESOLVED", NEUTRAL
    else:
        state, direction = "RANGE_OR_UNCLEAR", NEUTRAL

    ext_count, int_count = ext_info.get("count_state", NEUTRAL), int_info.get("count_state", NEUTRAL)
    reasons = list(base.get("reason_codes") or [])
    conflicts = list(base.get("conflicts") or [])
    if external in {UP, DOWN} and ext_count != external:
        reasons.append("EXTERNAL_COUNT_IS_CORROBORATION_ONLY"); conflicts.append("EXTERNAL_COUNT_VS_STRUCTURE_DIVERGENCE")
    if internal in {UP, DOWN} and int_count != internal:
        reasons.append("INTERNAL_COUNT_IS_CORROBORATION_ONLY"); conflicts.append("INTERNAL_COUNT_VS_STRUCTURE_DIVERGENCE")
    if external in {UP, DOWN} and internal != external:
        reasons.append("INTERNAL_EXTERNAL_STRUCTURE_DIVERGENCE"); conflicts.append("INTERNAL_CANNOT_OVERRIDE_EXTERNAL_AUTHORITY")
    if ext_event.get("event") == "STRUCTURE_CONFLICT":
        reasons += ["SAME_CANDLE_STRUCTURAL_CONFLICT", "NO_STRUCTURAL_AUTHORITY"]; conflicts.append("BOTH_EXTERNAL_LEVELS_BROKEN")
    elif not ext_event.get("confirmed"):
        reasons.append("NO_CONFIRMED_EXTERNAL_BOS")
    else:
        reasons.append("EXTERNAL_BREAK_HAS_MARKET_AUTHORITY")
    if int_event.get("confirmed") and not ext_event.get("confirmed"):
        reasons.append("INTERNAL_BREAK_IS_TACTICAL_ONLY")
    if protected_break["confirmed"]:
        reasons += ["PROTECTED_LEVEL_BROKEN", "EXTERNAL_THESIS_INVALIDATED_PENDING_REBUILD"]
    if sweep.get("confirmed"):
        reasons.append("LIQUIDITY_SWEEP_RECLAIM_DETECTED")
    if seq_q < MIN_SEQUENCE_QUALITY:
        reasons.append("STRUCTURAL_SEQUENCE_WEAK")
    reasons, conflicts = list(dict.fromkeys(reasons)), list(dict.fromkeys(conflicts))

    authority = 0.35 + 0.20 * seq_q if external not in {UP, DOWN} else 0.78 + 0.07 * (seq_q >= MIN_SEQUENCE_QUALITY) + 0.03 * (ext_count == external) + 0.08 * (internal == external) - 0.10 * (internal in {UP, DOWN} and internal != external)
    authority -= 0.05 * (int_event.get("confirmed") and not ext_event.get("confirmed"))
    authority += 0.04 * (ext_event.get("event") == "CONFIRMED_BOS")
    authority -= 0.20 * (ext_event.get("event") == "CONFIRMED_CHOCH")
    authority = round(max(0.20, min(1.0, authority)), 4)
    if protected_break["confirmed"] or ext_event.get("event") == "STRUCTURE_CONFLICT": authority = min(authority, 0.35)
    confidence = 0.48 + 0.30 * authority + 0.05 * (seq_q >= MIN_SEQUENCE_QUALITY) + 0.10 * bool(ext_event.get("confirmed")) - 0.05 * bool(int_event.get("confirmed") and not ext_event.get("confirmed"))
    if protected_break["confirmed"] or ext_event.get("event") == "STRUCTURE_CONFLICT": confidence -= 0.15
    confidence = round(max(0.0, min(1.0, confidence)), 4)

    ext_seq = "→".join(x["label"] for x in sorted(eh + el, key=lambda x: x["index"])[-12:])
    int_seq = "→".join(x["label"] for x in sorted(ih + il, key=lambda x: x["index"])[-12:])
    trace = dict(base.get("reasoning_trace") or {})
    trace.update({"external_is_authority": True, "internal_is_tactical_only": True, "counts_are_corroboration_only": True, "slope_is_corroboration_only": True, "closed_candle_only": True, "sequence_quality": seq_q, "sequence_state": seq_state, "protected_level_break_invalidates_current_thesis": bool(protected_break["confirmed"]), "protected_level_break_does_not_create_new_trend": True, "liquidity_sweep_is_not_structural_invalidation": True, "internal_break_requires_external_confirmation_for_authority": True, "bos_confirmation_rule": "CLOSE_BEYOND_LEVEL_AND_(BODY_DISPLACEMENT_OR_CLOSE_LOCATION)", "external_authority_levels": "UP=HH_CONTINUATION/HL_INVALIDATION;DOWN=LL_CONTINUATION/LH_INVALIDATION", "external_sequence": ext_seq, "internal_sequence": int_seq})

    base.update({"finding": f"EXTERNAL_{external}_INTERNAL_{internal}" if external in {UP, DOWN} else f"STRUCTURE_{state}", "direction": direction, "directional_bias": direction, "structural_bias": external if external in {UP, DOWN} else NEUTRAL, "structure_state": state, "structure": state, "bos": ext_event, "BOS": ext_event.get("event", "NO_BOS"), "BOS_type": ext_event.get("event", "NO_BOS"), "BOS_level": ext_event.get("level"), "BOS_candle_index": ext_event.get("break_candle_index"), "external_bos": ext_event.get("event", "NO_BOS"), "internal_bos": int_event.get("event", "NO_BOS"), "external_bos_detail": ext_event, "internal_bos_detail": int_event, "failure": sweep, "liquidity_sweep": sweep, "protected_high": protected_high.get("price") if protected_high else None, "protected_low": protected_low.get("price") if protected_low else None, "protected_high_detail": protected_high, "protected_low_detail": protected_low, "protected_break": protected_break, "sequence_quality": seq_q, "sequence_state": seq_state, "external_sequence": ext_seq, "internal_sequence": int_seq, "structure_authority": authority, "structure_strength": authority, "confidence": confidence, "conflicts": conflicts, "reason_codes": reasons, "observations": [f"closed_candles={len(clean)}", f"atr14={round(atr, 8)}", f"external_structure={external}", f"internal_structure={internal}", f"external_count_state={ext_count}", f"internal_count_state={int_count}", f"external_bos={ext_event.get('event', 'NO_BOS')}", f"internal_bos={int_event.get('event', 'NO_BOS')}", f"protected_high={protected_high.get('price') if protected_high else None}", f"protected_low={protected_low.get('price') if protected_low else None}", f"protected_break={protected_break.get('event', 'NONE')}", f"sequence_quality={seq_q}", f"sequence_state={seq_state}", f"structure_authority={authority}", f"structure_state={state}"], "reasoning_trace": trace, "upstream_direction_used": False, "upstream_decisions_used": False, "upstream_gates_used": False, "score_used": False, "trade_decision_authority": False, "decision_authority": "E9_ONLY", "decision": None, "gate": None})
    return base


__all__ = ["analyze_e3", "_break", "_authority_levels", "_external_event", "_sequence_quality"]
