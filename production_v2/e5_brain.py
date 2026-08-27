from __future__ import annotations

"""E5 — Professional Location / Value Brain v3.0.

E5 answers one question only: "Is current location advantageous?"
It evaluates both long and short location independently, then reports the
preferred side (if any). E1-E4 are qualitative context, never authority.
E5 never emits an entry, BUY/SELL decision, gate, or execution instruction.
"""

from math import isfinite
from statistics import mean
from typing import Any

ARCHITECTURE = "E5_SINGLE_PROFESSIONAL_LOCATION_BRAIN_V3"
VERSION = "3.0"
QUESTION = "Is current location advantageous?"
MIN_BARS = 80
ATR_PERIOD = 14
VALUE_LOOKBACK = 20
STRUCTURE_LOOKBACK = 60
LIQUIDITY_LOOKBACK = 30
EXTENSION_LOOKBACK = 20

_FORBIDDEN = {"decision", "trade_decision", "score", "decision_score", "gate",
              "gate_passed", "specialist_gate", "execution", "order", "entry"}


def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if isfinite(x) else None


def _bars(snapshot: dict[str, Any]) -> tuple[list[dict[str, float]], list[str]]:
    valid, problems = [], []
    for i, raw in enumerate(snapshot.get("bars") or []):
        if not isinstance(raw, dict):
            problems.append(f"BAR_{i}_INVALID")
            continue
        o, h, l, c = (_num(raw.get(k)) for k in ("open", "high", "low", "close"))
        v = _num(raw.get("volume"))
        if None in (o, h, l, c) or h < max(o, c) or l > min(o, c) or h < l:
            problems.append(f"BAR_{i}_OHLC_INVALID")
            continue
        b = {"open": o, "high": h, "low": l, "close": c}
        if v is not None and v >= 0:
            b["volume"] = v
        valid.append(b)
    return valid, problems


def _atr(bars: list[dict[str, float]], period: int = ATR_PERIOD) -> float:
    if len(bars) < 2:
        return 0.0
    sample = bars[-(period + 1):]
    trs = []
    for i, b in enumerate(sample):
        prev = sample[i - 1]["close"] if i else None
        trs.append(b["high"] - b["low"] if prev is None else max(b["high"] - b["low"], abs(b["high"] - prev), abs(b["low"] - prev)))
    return mean(trs[-period:]) if trs else 0.0


def _value_price(bars: list[dict[str, float]]) -> tuple[float, str]:
    sample = bars[-VALUE_LOOKBACK:]
    has_volume = any(b.get("volume", 0) > 0 for b in sample)
    weighted = sum(((b["high"] + b["low"] + b["close"]) / 3) * (b.get("volume", 0) if has_volume else 1.0) for b in sample)
    weight = sum((b.get("volume", 0) if has_volume else 1.0) for b in sample)
    if weight <= 0:
        return mean((b["high"] + b["low"] + b["close"]) / 3 for b in sample), "EQUAL_WEIGHT_TYPICAL_PRICE"
    return weighted / weight, "VOLUME_WEIGHTED_TYPICAL_PRICE" if has_volume else "EQUAL_WEIGHT_TYPICAL_PRICE"


def _range(bars: list[dict[str, float]], lookback: int) -> tuple[float, float]:
    sample = bars[-lookback:]
    return min(b["low"] for b in sample), max(b["high"] for b in sample)


def _pivots(bars: list[dict[str, float]], wing: int = 2) -> tuple[list[float], list[float]]:
    highs, lows = [], []
    for i in range(wing, len(bars) - wing):
        w = bars[i - wing:i + wing + 1]
        if bars[i]["high"] >= max(x["high"] for x in w): highs.append(bars[i]["high"])
        if bars[i]["low"] <= min(x["low"] for x in w): lows.append(bars[i]["low"])
    return highs[-10:], lows[-10:]


def _nearest_above(price: float, levels: list[float], tolerance: float) -> float | None:
    x = [v for v in levels if v > price + tolerance]
    return min(x) if x else None


def _nearest_below(price: float, levels: list[float], tolerance: float) -> float | None:
    x = [v for v in levels if v < price - tolerance]
    return max(x) if x else None


def _dist(price: float, level: float | None, atr: float) -> float | None:
    return None if level is None or atr <= 0 else abs(price - level) / atr


def _upstream(permitted: dict[str, Any] | None) -> tuple[dict[str, Any], list[str], list[str]]:
    ctx, evidence, conflicts = {}, [], []
    for eid in ("E1", "E2", "E3", "E4"):
        package = (permitted or {}).get(eid)
        if not isinstance(package, dict):
            continue
        payload = package.get("evidence") or package.get("output") or {}
        if not isinstance(payload, dict):
            continue
        clean = {k: v for k, v in payload.items() if str(k).lower() not in _FORBIDDEN}
        ctx[eid] = clean
        evidence.append(f"{eid}_QUALITATIVE_CONTEXT_READ")
        text = str(clean).upper()
        if any(t in text for t in ("CONFLICT", "MIXED", "UNRESOLVED", "PENDING")):
            conflicts.append(f"{eid}_CONTEXT_CONFLICT")
    return ctx, evidence, conflicts


def _context_direction(ctx: dict[str, Any]) -> str:
    text = str(ctx).upper()
    up = any(t in text for t in ("TREND_UP", "BULLISH", "DIRECTION=UP", "PRESSURE=BULLISH"))
    down = any(t in text for t in ("TREND_DOWN", "BEARISH", "DIRECTION=DOWN", "PRESSURE=BEARISH"))
    return "UP" if up and not down else "DOWN" if down and not up else "NEUTRAL"


def _sweep_state(bars: list[dict[str, float]], ctx: dict[str, Any]) -> tuple[bool, bool]:
    prior = bars[-(LIQUIDITY_LOOKBACK + 1):-1]
    rh, rl = max(b["high"] for b in prior), min(b["low"] for b in prior)
    last = bars[-1]
    high = last["high"] > rh and last["close"] < rh
    low = last["low"] < rl and last["close"] > rl
    e4 = str(ctx.get("E4", {})).upper()
    return high or "SWEEP_HIGH" in e4 or "HIGH_SWEEP" in e4, low or "SWEEP_LOW" in e4 or "LOW_SWEEP" in e4


def _incomplete(reason: str, problems: list[str]) -> dict[str, Any]:
    ev = problems or ["NO_RELIABLE_EVIDENCE"]
    return {
        "architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION,
        "task": "ASSESS_PRICE_LOCATION_ONLY", "location_state": "UNRESOLVED", "location_quality": "UNRESOLVED",
        "direction": "NEUTRAL", "value_state": "UNKNOWN", "structural_location": "UNKNOWN",
        "liquidity_location": "UNKNOWN", "extension_state": "UNKNOWN", "available_space": "UNKNOWN",
        "long_location_quality": "UNKNOWN", "short_location_quality": "UNKNOWN", "preferred_location": "NONE",
        "confidence": 0.0, "evidence": ev, "observations": ev, "counter_evidence": [], "conflicts": problems,
        "reason_codes": ["E5_DATA_INCOMPLETE"], "reasoning_trace": [f"QUESTION -> {QUESTION}", f"DATA_QUALITY -> {reason}"],
        "professional_reasoning": {"question": QUESTION, "thesis": reason,
            "evidence_hierarchy": "VALUE -> STRUCTURE -> LIQUIDITY -> EXTENSION -> SPACE -> COUNTER_EVIDENCE",
            "upstream_decisions_used": False, "decision_authority": "E9_ONLY"},
        "trade_decision_authority": False, "decision_authority": "E9_ONLY", "gate": None, "specialist_gate": "NONE",
        "specialists": {}, "specialists_active": False, "specialists_status": "NOT_USED",
    }


def analyze_e5(snapshot: dict[str, Any], permitted: dict[str, Any] | None = None) -> dict[str, Any]:
    bars, problems = _bars(snapshot)
    if len(bars) < MIN_BARS:
        return _incomplete(f"reliable candles below minimum {MIN_BARS}", problems[:8])
    atr = _atr(bars)
    if atr <= 0:
        return _incomplete("ATR invalid; location cannot be normalized", ["ATR_INVALID"])

    price = bars[-1]["close"]
    value, value_method = _value_price(bars)
    value_lo, value_hi = _range(bars, VALUE_LOOKBACK)
    value_width = max(value_hi - value_lo, atr)
    value_position = max(0.0, min(1.0, (price - value_lo) / value_width))
    value_distance_atr = (price - value) / atr

    struct_low, struct_high = _range(bars, STRUCTURE_LOOKBACK)
    ph, pl = _pivots(bars)
    tol = 0.15 * atr
    next_high = _nearest_above(price, ph + [struct_high], tol)
    next_low = _nearest_below(price, pl + [struct_low], tol)
    up_space = _dist(price, next_high, atr)
    down_space = _dist(price, next_low, atr)
    near_high = _dist(price, struct_high, atr) is not None and _dist(price, struct_high, atr) <= 0.75
    near_low = _dist(price, struct_low, atr) is not None and _dist(price, struct_low, atr) <= 0.75

    ctx, upstream_evidence, conflicts = _upstream(permitted)
    context_direction = _context_direction(ctx)
    sweep_high, sweep_low = _sweep_state(bars, ctx)

    impulse_start = bars[-EXTENSION_LOOKBACK]["close"]
    impulse_atr = abs(price - impulse_start) / atr
    extension_atr = abs(value_distance_atr)
    extension_state = "NORMAL" if extension_atr < 0.75 else "STRETCHED" if extension_atr < 1.5 else "EXTENDED" if extension_atr < 2.5 else "EXCESSIVE"

    def side_quality(side: str) -> tuple[float, list[str]]:
        pos = value_position if side == "LONG" else 1.0 - value_position
        space = up_space if side == "LONG" else down_space
        near_opposite = near_high if side == "LONG" else near_low
        sweep = sweep_low if side == "LONG" else sweep_high
        score = 0.0
        reasons = []
        # Value: buying lower in the local auction / selling higher is favorable.
        value_component = 1.0 - min(1.0, pos / 0.75)
        score += 0.30 * value_component
        if value_component >= 0.60: reasons.append("VALUE_FAVORABLE")
        # Structure: avoid initiating directly into the opposing boundary.
        structure_component = 0.15 if near_opposite else 0.80
        score += 0.15 * structure_component
        if near_opposite: reasons.append("OPPOSING_STRUCTURE_NEARBY")
        # Liquidity: a sweep/reclaim location is stronger than an untested middle.
        liquidity_component = 1.0 if sweep else 0.55 if (near_low or near_high) else 0.35
        score += 0.20 * liquidity_component
        if sweep: reasons.append("LIQUIDITY_SWEEP_AT_LOCATION")
        # Extension: professional trader avoids paying after a large displacement.
        extension_component = max(0.0, 1.0 - extension_atr / 2.5)
        score += 0.20 * extension_component
        if extension_atr >= 1.5: reasons.append("EXTENSION_RISK")
        # Space: room to the next opposing reference matters for asymmetry.
        space_component = 1.0 if space is None or space >= 2.0 else 0.65 if space >= 1.0 else 0.10
        score += 0.15 * space_component
        if space is not None and space < 1.0: reasons.append("SPACE_CONSTRAINED")
        return round(score, 4), reasons

    long_q, long_reasons = side_quality("LONG")
    short_q, short_reasons = side_quality("SHORT")

    # Context is an orientation input, not a veto. Location must remain describable
    # even when E1-E4 disagree, matching the no-gate contract.
    if max(long_q, short_q) < 0.45:
        preferred = "NONE"
    elif abs(long_q - short_q) < 0.08:
        preferred = "BOTH_CONDITIONAL"
    else:
        preferred = "LONG" if long_q > short_q else "SHORT"

    def quality(q: float) -> str:
        return "HIGH" if q >= 0.72 else "ACCEPTABLE" if q >= 0.58 else "CONDITIONAL" if q >= 0.45 else "UNFAVORABLE"

    long_label, short_label = quality(long_q), quality(short_q)
    if preferred == "LONG":
        location_state = "ADVANTAGEOUS_LONG" if long_label == "HIGH" else "ACCEPTABLE_LONG"
    elif preferred == "SHORT":
        location_state = "ADVANTAGEOUS_SHORT" if short_label == "HIGH" else "ACCEPTABLE_SHORT"
    elif preferred == "BOTH_CONDITIONAL":
        location_state = "BOTH_CONDITIONAL"
    else:
        location_state = "UNFAVORABLE"

    if near_high and near_low:
        structural_location = "COMPRESSED_STRUCTURE"
    elif near_high:
        structural_location = "AT_RESISTANCE"
    elif near_low:
        structural_location = "AT_SUPPORT"
    else:
        structural_location = "INSIDE_STRUCTURE"
    liquidity_location = "SELL_SIDE_LIQUIDITY_SWEPT" if sweep_low else "BUY_SIDE_LIQUIDITY_SWEPT" if sweep_high else "NEAR_RESISTANCE" if near_high else "NEAR_SUPPORT" if near_low else "LIQUIDITY_UNCLEAR"
    space_long_state = "OPEN" if up_space is None or up_space >= 2 else "MODERATE" if up_space >= 1 else "TIGHT"
    space_short_state = "OPEN" if down_space is None or down_space >= 2 else "MODERATE" if down_space >= 1 else "TIGHT"

    counter = []
    if near_high: counter.append("LONG_NEAR_RESISTANCE")
    if near_low: counter.append("SHORT_NEAR_SUPPORT")
    if extension_atr >= 1.5: counter.append("PRICE_STRETCHED_FROM_VALUE")
    if up_space is not None and up_space < 1.0: counter.append("LONG_SPACE_CONSTRAINED")
    if down_space is not None and down_space < 1.0: counter.append("SHORT_SPACE_CONSTRAINED")
    counter.extend(conflicts)

    components = {
        "value": max(0.0, 1.0 - min(1.0, abs(value_distance_atr) / 2.0)),
        "structure": 0.85 if not (near_high or near_low) else 0.45,
        "liquidity": 0.95 if (sweep_high or sweep_low) else 0.55,
        "extension": max(0.05, 1.0 - min(1.0, extension_atr / 3.0)),
        "space": max((up_space or 3.0), (down_space or 3.0)) / 3.0,
    }
    components["space"] = min(1.0, components["space"])
    data_quality = max(0.0, 1.0 - len(problems) / max(1, len(bars)))
    confidence = round(max(0.0, min(0.99, 0.20 + 0.65 * mean(components.values()) + 0.15 * data_quality - min(0.10, 0.02 * len(conflicts)))), 3)

    reasons = []
    if preferred in {"LONG", "SHORT"}: reasons.append(f"PREFERRED_{preferred}_LOCATION")
    if preferred == "NONE": reasons.append("NO_ASYMMETRIC_LOCATION")
    if sweep_high or sweep_low: reasons.append("LIQUIDITY_EVENT_AT_LOCATION")
    if extension_atr >= 1.5: reasons.append("EXTENSION_RISK")
    if (up_space is not None and up_space < 1.0) or (down_space is not None and down_space < 1.0): reasons.append("SPACE_CONSTRAINED")
    if conflicts: reasons.append("UPSTREAM_CONTEXT_CONFLICT_IS_COUNTER_EVIDENCE")

    thesis = (f"Location={location_state}; preferred={preferred}; long_quality={long_q:.2f}; short_quality={short_q:.2f}; "
              f"value_position={value_position:.2f}; extension={extension_state}; "
              f"space_long={space_long_state}; space_short={space_short_state}. E5 describes location only; E9 owns execution.")

    evidence = [
        f"price={price:.6f}", f"atr14={atr:.6f}", f"value={value:.6f}", f"value_method={value_method}",
        f"value_distance_atr={value_distance_atr:.3f}", f"value_position={value_position:.3f}",
        f"structural_location={structural_location}", f"structural_high={struct_high:.6f}", f"structural_low={struct_low:.6f}",
        f"distance_to_next_high_atr={up_space if up_space is not None else 'OPEN'}", f"distance_to_next_low_atr={down_space if down_space is not None else 'OPEN'}",
        f"liquidity_location={liquidity_location}", f"sweep_high={sweep_high}", f"sweep_low={sweep_low}",
        f"extension_atr={extension_atr:.3f}", f"extension_state={extension_state}", f"impulse_displacement_atr={impulse_atr:.3f}",
        f"long_quality={long_q:.3f}", f"short_quality={short_q:.3f}", f"preferred_location={preferred}",
        f"context_direction={context_direction}",
    ] + upstream_evidence

    return {
        "architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION,
        "task": "ASSESS_PRICE_LOCATION_ONLY", "location_state": location_state,
        "location_quality": quality(max(long_q, short_q)), "direction": context_direction,
        "value_state": "DISCOUNT" if value_position <= 0.35 else "PREMIUM" if value_position >= 0.65 else "EQUILIBRIUM",
        "value": round(value, 6), "value_method": value_method, "value_distance_atr": round(value_distance_atr, 4), "value_position": round(value_position, 4),
        "structural_location": structural_location, "structural_high": struct_high, "structural_low": struct_low,
        "distance_to_next_high_atr": None if up_space is None else round(up_space, 4), "distance_to_next_low_atr": None if down_space is None else round(down_space, 4),
        "liquidity_location": liquidity_location, "sweep_high": sweep_high, "sweep_low": sweep_low,
        "extension_state": extension_state, "extension_atr": round(extension_atr, 4), "impulse_displacement_atr": round(impulse_atr, 4),
        "available_space": {"LONG": space_long_state, "SHORT": space_short_state},
        "available_space_atr": {"LONG": None if up_space is None else round(up_space, 4), "SHORT": None if down_space is None else round(down_space, 4)},
        "up_space_atr": None if up_space is None else round(up_space, 4), "down_space_atr": None if down_space is None else round(down_space, 4),
        "long_location_quality": long_label, "short_location_quality": short_label,
        "long_location_score": long_q, "short_location_score": short_q, "preferred_location": preferred,
        "long_location_valid": long_q >= 0.58, "short_location_valid": short_q >= 0.58,
        "side_reasoning": {"LONG": long_reasons, "SHORT": short_reasons},
        "quality_components": {k: round(v, 4) for k, v in components.items()}, "confidence": confidence,
        "evidence": evidence, "observations": evidence, "counter_evidence": counter, "conflicts": conflicts,
        "reason_codes": reasons or ["LOCATION_NEUTRAL"],
        "reasoning_trace": [
            f"QUESTION -> {QUESTION}", f"DATA_QUALITY -> valid_bars={len(bars)} invalid_bars={len(problems)} atr14={atr:.4f}",
            f"VALUE -> method={value_method} position={value_position:.3f} distance={value_distance_atr:.3f}ATR",
            f"STRUCTURE -> {structural_location} next_high={up_space}ATR next_low={down_space}ATR",
            f"LIQUIDITY -> {liquidity_location} sweep_high={sweep_high} sweep_low={sweep_low}",
            f"EXTENSION -> {extension_state} value_distance={extension_atr:.3f}ATR impulse={impulse_atr:.3f}ATR",
            f"SPACE -> LONG={space_long_state}({up_space}) SHORT={space_short_state}({down_space})",
            f"SIDE_COMPARISON -> LONG={long_q:.3f} SHORT={short_q:.3f} PREFERRED={preferred}",
            f"COUNTER_EVIDENCE -> {counter if counter else 'NONE'}", f"THESIS -> {thesis}",
            "AUTHORITY -> E5_LOCATION_ONLY; E9_ONLY_EXECUTION_DECISION",
        ],
        "professional_reasoning": {
            "question": QUESTION, "thesis": thesis,
            "evidence_hierarchy": "VALUE -> STRUCTURE -> LIQUIDITY -> EXTENSION -> SPACE -> LONG/SHORT COMPARISON -> COUNTER_EVIDENCE",
            "upstream_engines_read": sorted(ctx), "upstream_decisions_used": False, "upstream_gates_used": False, "upstream_scores_used": False,
            "independent_price_analysis": True, "both_sides_evaluated": True, "context_is_orientation_not_veto": True,
            "confidence_is_win_probability": False, "decision_authority": "E9_ONLY",
        },
        "trade_decision_authority": False, "decision_authority": "E9_ONLY", "gate": None, "specialist_gate": "NONE",
        "specialists": {}, "specialists_active": False, "specialists_status": "NOT_USED",
    }
