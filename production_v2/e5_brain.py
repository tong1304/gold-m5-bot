from __future__ import annotations

"""E5 — Professional Location / Value Brain v4.

E5 answers one question only: "Is current location advantageous?"
It is a location analyst, not an entry engine. It evaluates LONG and SHORT
independently using value, structure, liquidity, extension and available
space. Upstream engines provide context only; they never become E5 authority.
E5 never emits BUY/SELL, an order, a gate, or an execution decision.
"""

from math import isfinite
from statistics import mean
from typing import Any

ARCHITECTURE = "E5_SINGLE_PROFESSIONAL_LOCATION_BRAIN_V4"
VERSION = "4.0"
QUESTION = "Is current location advantageous?"
MIN_BARS = 80
ATR_PERIOD = 14
VALUE_LOOKBACK = 20
STRUCTURE_LOOKBACK = 60
LIQUIDITY_LOOKBACK = 30
EXTENSION_LOOKBACK = 20


def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if isfinite(x) else None


def _bars(snapshot: dict[str, Any]) -> tuple[list[dict[str, float]], list[str]]:
    valid: list[dict[str, float]] = []
    problems: list[str] = []
    for i, raw in enumerate(snapshot.get("bars") or []):
        if not isinstance(raw, dict):
            problems.append(f"BAR_{i}_INVALID")
            continue
        o, h, l, c = (_num(raw.get(k)) for k in ("open", "high", "low", "close"))
        v = _num(raw.get("volume"))
        if None in (o, h, l, c) or h < max(o, c) or l > min(o, c) or h < l:
            problems.append(f"BAR_{i}_OHLC_INVALID")
            continue
        b: dict[str, float] = {"open": o, "high": h, "low": l, "close": c}
        if v is not None and v >= 0:
            b["volume"] = v
        valid.append(b)
    return valid, problems


def _atr(bars: list[dict[str, float]], period: int = ATR_PERIOD) -> float:
    if len(bars) < 2:
        return 0.0
    sample = bars[-(period + 1):]
    trs: list[float] = []
    for i, b in enumerate(sample):
        prev = sample[i - 1]["close"] if i else None
        trs.append(b["high"] - b["low"] if prev is None else max(b["high"] - b["low"], abs(b["high"] - prev), abs(b["low"] - prev)))
    return mean(trs[-period:]) if trs else 0.0


def _value_price(bars: list[dict[str, float]]) -> tuple[float, str]:
    sample = bars[-VALUE_LOOKBACK:]
    has_volume = any(b.get("volume", 0) > 0 for b in sample)
    weights = [b.get("volume", 0) if has_volume else 1.0 for b in sample]
    prices = [(b["high"] + b["low"] + b["close"]) / 3 for b in sample]
    total = sum(weights)
    if total <= 0:
        return mean(prices), "EQUAL_WEIGHT_TYPICAL_PRICE"
    return sum(p * w for p, w in zip(prices, weights)) / total, ("VOLUME_WEIGHTED_TYPICAL_PRICE" if has_volume else "EQUAL_WEIGHT_TYPICAL_PRICE")


def _range(bars: list[dict[str, float]], lookback: int) -> tuple[float, float]:
    sample = bars[-lookback:]
    return min(b["low"] for b in sample), max(b["high"] for b in sample)


def _pivots(bars: list[dict[str, float]], wing: int = 2) -> tuple[list[float], list[float]]:
    highs: list[float] = []
    lows: list[float] = []
    for i in range(wing, len(bars) - wing):
        w = bars[i - wing:i + wing + 1]
        if bars[i]["high"] >= max(x["high"] for x in w): highs.append(bars[i]["high"])
        if bars[i]["low"] <= min(x["low"] for x in w): lows.append(bars[i]["low"])
    return highs[-12:], lows[-12:]


def _nearest_above(price: float, levels: list[float], tolerance: float) -> float | None:
    values = [v for v in levels if v > price + tolerance]
    return min(values) if values else None


def _nearest_below(price: float, levels: list[float], tolerance: float) -> float | None:
    values = [v for v in levels if v < price - tolerance]
    return max(values) if values else None


def _dist(price: float, level: float | None, atr: float) -> float | None:
    return None if level is None or atr <= 0 else abs(price - level) / atr


def _upstream(permitted: dict[str, Any] | None) -> tuple[dict[str, Any], list[str], list[str]]:
    ctx: dict[str, Any] = {}
    evidence: list[str] = []
    conflicts: list[str] = []
    for eid in ("E1", "E2", "E3", "E4"):
        package = (permitted or {}).get(eid)
        if not isinstance(package, dict): continue
        payload = package.get("evidence") or package.get("output") or {}
        if not isinstance(payload, dict): continue
        ctx[eid] = dict(payload)
        evidence.append(f"{eid}_QUALITATIVE_CONTEXT_READ")
        text = str(payload).upper()
        if any(token in text for token in ("CONFLICT", "MIXED", "UNRESOLVED", "PENDING")):
            conflicts.append(f"{eid}_CONTEXT_CONFLICT")
    return ctx, evidence, conflicts


def _context_direction(ctx: dict[str, Any]) -> str:
    text = str(ctx).upper()
    up = any(t in text for t in ("TREND_UP", "BULLISH", "DIRECTION=UP", "PRESSURE=BULLISH"))
    down = any(t in text for t in ("TREND_DOWN", "BEARISH", "DIRECTION=DOWN", "PRESSURE=BEARISH"))
    return "UP" if up and not down else "DOWN" if down and not up else "NEUTRAL"


def _sweeps(bars: list[dict[str, float]], ctx: dict[str, Any]) -> tuple[bool, bool]:
    prior = bars[-(LIQUIDITY_LOOKBACK + 1):-1]
    rh, rl = max(b["high"] for b in prior), min(b["low"] for b in prior)
    last = bars[-1]
    high = last["high"] > rh and last["close"] < rh
    low = last["low"] < rl and last["close"] > rl
    e4 = str(ctx.get("E4", {})).upper()
    return high or "SWEEP_HIGH" in e4 or "HIGH_SWEEP" in e4, low or "SWEEP_LOW" in e4 or "LOW_SWEEP" in e4


def _incomplete(reason: str, problems: list[str]) -> dict[str, Any]:
    evidence = problems or ["NO_RELIABLE_EVIDENCE"]
    return {"architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION, "task": "ASSESS_PRICE_LOCATION_ONLY", "location_state": "UNRESOLVED", "location_quality": "UNRESOLVED", "direction": "NEUTRAL", "value_state": "UNKNOWN", "structural_location": "UNKNOWN", "liquidity_location": "UNKNOWN", "extension_state": "UNKNOWN", "available_space": "UNKNOWN", "long_location_quality": "UNKNOWN", "short_location_quality": "UNKNOWN", "preferred_location": "NONE", "confidence": 0.0, "evidence": evidence, "observations": evidence, "counter_evidence": [], "conflicts": problems, "reason_codes": ["E5_DATA_INCOMPLETE"], "reasoning_trace": [f"QUESTION -> {QUESTION}", f"DATA_QUALITY -> {reason}"], "professional_reasoning": {"question": QUESTION, "thesis": reason, "evidence_hierarchy": "VALUE -> STRUCTURE -> LIQUIDITY -> EXTENSION -> SPACE -> COUNTER_EVIDENCE", "upstream_decisions_used": False, "upstream_gates_used": False, "decision_authority": "E9_ONLY"}, "trade_decision_authority": False, "decision_authority": "E9_ONLY", "gate": None, "specialist_gate": "NONE", "specialists": {}, "specialists_active": False, "specialists_status": "NOT_USED"}


def analyze_e5(snapshot: dict[str, Any], permitted: dict[str, Any] | None = None) -> dict[str, Any]:
    bars, problems = _bars(snapshot)
    if len(bars) < MIN_BARS: return _incomplete(f"reliable candles below minimum {MIN_BARS}", problems[:8])
    atr = _atr(bars)
    if atr <= 0: return _incomplete("ATR invalid; location cannot be normalized", ["ATR_INVALID"])

    price = bars[-1]["close"]
    value, value_method = _value_price(bars)
    value_lo, value_hi = _range(bars, VALUE_LOOKBACK)
    value_width = max(value_hi - value_lo, atr)
    value_position = max(0.0, min(1.0, (price - value_lo) / value_width))
    value_distance_atr = (price - value) / atr

    struct_low, struct_high = _range(bars, STRUCTURE_LOOKBACK)
    pivot_highs, pivot_lows = _pivots(bars)
    tolerance = 0.15 * atr
    next_high = _nearest_above(price, pivot_highs + [struct_high], tolerance)
    next_low = _nearest_below(price, pivot_lows + [struct_low], tolerance)
    up_space, down_space = _dist(price, next_high, atr), _dist(price, next_low, atr)
    high_distance, low_distance = _dist(price, struct_high, atr), _dist(price, struct_low, atr)
    near_high = high_distance is not None and high_distance <= 0.75
    near_low = low_distance is not None and low_distance <= 0.75

    ctx, upstream_evidence, conflicts = _upstream(permitted)
    context_direction = _context_direction(ctx)
    sweep_high, sweep_low = _sweeps(bars, ctx)

    impulse_start = bars[-EXTENSION_LOOKBACK]["close"]
    impulse_displacement_atr = abs(price - impulse_start) / atr
    extension_atr = abs(value_distance_atr)
    extension_state = "NORMAL" if extension_atr < 0.75 else "STRETCHED" if extension_atr < 1.50 else "EXTENDED" if extension_atr < 2.50 else "EXCESSIVE"

    def side(side_name: str) -> tuple[float, list[str], dict[str, float]]:
        long = side_name == "LONG"
        favorable_value = value_position <= 0.35 if long else value_position >= 0.65
        adverse_value = value_position >= 0.65 if long else value_position <= 0.35
        opposite_near = near_high if long else near_low
        sweep = sweep_low if long else sweep_high
        space = up_space if long else down_space
        value_component = 1.0 if favorable_value else 0.60 if not adverse_value else 0.15
        structure_component = 0.20 if opposite_near else 0.85
        liquidity_component = 1.0 if sweep else 0.55
        extension_component = 0.20 if extension_state == "EXCESSIVE" else 0.40 if extension_state == "EXTENDED" else 0.70 if extension_state == "STRETCHED" else 1.0
        space_component = 1.0 if space is None or space >= 2.0 else 0.65 if space >= 1.0 else 0.10
        quality = round(0.30 * value_component + 0.15 * structure_component + 0.20 * liquidity_component + 0.20 * extension_component + 0.15 * space_component, 4)
        reasons: list[str] = []
        if favorable_value: reasons.append("VALUE_FAVORABLE")
        if adverse_value: reasons.append("VALUE_ADVERSE")
        if opposite_near: reasons.append("OPPOSING_STRUCTURE_NEARBY")
        if sweep: reasons.append("LIQUIDITY_SWEEP_AT_LOCATION")
        if extension_state in {"EXTENDED", "EXCESSIVE"}: reasons.append("EXTENSION_RISK")
        if space is not None and space < 1.0: reasons.append("SPACE_CONSTRAINED")
        if long and context_direction == "DOWN": reasons.append("COUNTER_CONTEXT_LONG")
        if not long and context_direction == "UP": reasons.append("COUNTER_CONTEXT_SHORT")
        return quality, reasons, {"value": value_component, "structure": structure_component, "liquidity": liquidity_component, "extension": extension_component, "space": space_component}

    long_q, long_reasons, long_components = side("LONG")
    short_q, short_reasons, short_components = side("SHORT")

    if context_direction == "UP" and long_q >= 0.45:
        preferred = "LONG"
    elif context_direction == "DOWN" and short_q >= 0.45:
        preferred = "SHORT"
    elif abs(long_q - short_q) >= 0.08 and max(long_q, short_q) >= 0.45:
        preferred = "LONG" if long_q > short_q else "SHORT"
    elif max(long_q, short_q) >= 0.45:
        preferred = "BOTH_CONDITIONAL"
    else:
        preferred = "NONE"

    aligned_extension = context_direction in {"UP", "DOWN"} and extension_state in {"EXTENDED", "EXCESSIVE"}
    aligned_quality = long_q if context_direction == "UP" else short_q if context_direction == "DOWN" else max(long_q, short_q)
    if aligned_extension and aligned_quality < 0.72:
        location_state = "WAIT_REPRICING"
    elif preferred == "LONG" and long_q >= 0.72:
        location_state = "ADVANTAGEOUS_LONG"
    elif preferred == "SHORT" and short_q >= 0.72:
        location_state = "ADVANTAGEOUS_SHORT"
    elif preferred in {"LONG", "SHORT"}:
        location_state = f"ACCEPTABLE_{preferred}"
    elif preferred == "BOTH_CONDITIONAL":
        location_state = "BOTH_CONDITIONAL"
    else:
        location_state = "UNFAVORABLE"

    def label(q: float) -> str:
        return "HIGH" if q >= 0.72 else "ACCEPTABLE" if q >= 0.58 else "CONDITIONAL" if q >= 0.45 else "UNFAVORABLE"

    structural_location = "COMPRESSED_STRUCTURE" if near_high and near_low else "AT_RESISTANCE" if near_high else "AT_SUPPORT" if near_low else "INSIDE_STRUCTURE"
    liquidity_location = "SELL_SIDE_LIQUIDITY_SWEPT" if sweep_low else "BUY_SIDE_LIQUIDITY_SWEPT" if sweep_high else "NEAR_RESISTANCE" if near_high else "NEAR_SUPPORT" if near_low else "LIQUIDITY_UNCLEAR"
    space_long_state = "OPEN" if up_space is None or up_space >= 2 else "MODERATE" if up_space >= 1 else "TIGHT"
    space_short_state = "OPEN" if down_space is None or down_space >= 2 else "MODERATE" if down_space >= 1 else "TIGHT"

    counter: list[str] = []
    if context_direction == "UP" and short_q > long_q: counter.append("COUNTERTREND_SHORT_NOT_PROMOTED")
    if context_direction == "DOWN" and long_q > short_q: counter.append("COUNTERTREND_LONG_NOT_PROMOTED")
    if near_high: counter.append("LONG_NEAR_RESISTANCE")
    if near_low: counter.append("SHORT_NEAR_SUPPORT")
    if extension_state in {"EXTENDED", "EXCESSIVE"}: counter.append("PRICE_STRETCHED_FROM_VALUE")
    if up_space is not None and up_space < 1.0: counter.append("LONG_SPACE_CONSTRAINED")
    if down_space is not None and down_space < 1.0: counter.append("SHORT_SPACE_CONSTRAINED")
    counter.extend(conflicts)

    combined = {k: max(long_components[k], short_components[k]) for k in long_components}
    data_quality = max(0.0, 1.0 - len(problems) / max(1, len(bars)))
    confidence = round(max(0.0, min(0.99, 0.20 + 0.65 * mean(combined.values()) + 0.15 * data_quality - min(0.10, 0.02 * len(conflicts)))), 3)

    reasons: list[str] = []
    if preferred in {"LONG", "SHORT"}: reasons.append(f"PREFERRED_{preferred}_LOCATION")
    if location_state == "WAIT_REPRICING": reasons.append("WAITING_FOR_REPRICING")
    if sweep_high or sweep_low: reasons.append("LIQUIDITY_EVENT_AT_LOCATION")
    if extension_state in {"EXTENDED", "EXCESSIVE"}: reasons.append("EXTENSION_RISK")
    if (up_space is not None and up_space < 1.0) or (down_space is not None and down_space < 1.0): reasons.append("SPACE_CONSTRAINED")
    if conflicts: reasons.append("UPSTREAM_CONTEXT_CONFLICT_IS_COUNTER_EVIDENCE")
    if not reasons: reasons.append("LOCATION_NEUTRAL")

    value_state = "DISCOUNT" if value_position <= 0.35 else "PREMIUM" if value_position >= 0.65 else "EQUILIBRIUM"
    thesis = f"Location={location_state}; preferred={preferred}; long_quality={long_q:.2f}; short_quality={short_q:.2f}; value_state={value_state}; extension={extension_state}; space_long={space_long_state}; space_short={space_short_state}. E5 describes location only; E9 owns execution."
    evidence = [f"price={price:.6f}", f"atr14={atr:.6f}", f"value={value:.6f}", f"value_method={value_method}", f"value_distance_atr={value_distance_atr:.3f}", f"value_position={value_position:.3f}", f"structural_location={structural_location}", f"structural_high={struct_high:.6f}", f"structural_low={struct_low:.6f}", f"distance_to_next_high_atr={up_space if up_space is not None else 'OPEN'}", f"distance_to_next_low_atr={down_space if down_space is not None else 'OPEN'}", f"liquidity_location={liquidity_location}", f"sweep_high={sweep_high}", f"sweep_low={sweep_low}", f"extension_atr={extension_atr:.3f}", f"extension_state={extension_state}", f"impulse_displacement_atr={impulse_displacement_atr:.3f}", f"long_quality={long_q:.3f}", f"short_quality={short_q:.3f}", f"preferred_location={preferred}", f"context_direction={context_direction}"] + upstream_evidence

    return {
        "architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION, "task": "ASSESS_PRICE_LOCATION_ONLY",
        "location_state": location_state, "location_quality": label(max(long_q, short_q)), "direction": context_direction,
        "value_state": value_state, "value": round(value, 6), "value_method": value_method, "value_distance_atr": round(value_distance_atr, 4), "value_position": round(value_position, 4),
        "structural_location": structural_location, "structural_high": struct_high, "structural_low": struct_low,
        "distance_to_next_high_atr": None if up_space is None else round(up_space, 4), "distance_to_next_low_atr": None if down_space is None else round(down_space, 4),
        "liquidity_location": liquidity_location, "sweep_high": sweep_high, "sweep_low": sweep_low,
        "extension_state": extension_state, "extension_atr": round(extension_atr, 4), "impulse_displacement_atr": round(impulse_displacement_atr, 4),
        "available_space": {"LONG": space_long_state, "SHORT": space_short_state}, "available_space_atr": {"LONG": up_space, "SHORT": down_space},
        "up_space_atr": up_space, "down_space_atr": down_space,
        "long_location_quality": label(long_q), "short_location_quality": label(short_q), "long_location_score": long_q, "short_location_score": short_q,
        "preferred_location": preferred, "long_location_valid": long_q >= 0.58, "short_location_valid": short_q >= 0.58,
        "side_reasoning": {"LONG": long_reasons, "SHORT": short_reasons},
        "quality_components": {"LONG": {k: round(v, 4) for k, v in long_components.items()}, "SHORT": {k: round(v, 4) for k, v in short_components.items()}},
        "confidence": confidence, "evidence": evidence, "observations": evidence, "counter_evidence": counter, "conflicts": conflicts, "reason_codes": reasons,
        "reasoning_trace": [f"QUESTION -> {QUESTION}", f"DATA_QUALITY -> valid_bars={len(bars)} invalid_bars={len(problems)} atr14={atr:.4f}", f"VALUE -> method={value_method} position={value_position:.3f} distance={value_distance_atr:.3f}ATR", f"STRUCTURE -> {structural_location} next_high={up_space}ATR next_low={down_space}ATR", f"LIQUIDITY -> {liquidity_location} sweep_high={sweep_high} sweep_low={sweep_low}", f"EXTENSION -> {extension_state} value_distance={extension_atr:.3f}ATR impulse={impulse_displacement_atr:.3f}ATR", f"SPACE -> LONG={space_long_state}({up_space}) SHORT={space_short_state}({down_space})", f"SIDE_COMPARISON -> LONG={long_q:.3f} SHORT={short_q:.3f} PREFERRED={preferred}", f"COUNTER_EVIDENCE -> {counter if counter else 'NONE'}", f"THESIS -> {thesis}", "AUTHORITY -> E5_LOCATION_ONLY; E9_ONLY_EXECUTION_DECISION"],
        "professional_reasoning": {"question": QUESTION, "thesis": thesis, "evidence_hierarchy": "VALUE -> STRUCTURE -> LIQUIDITY -> EXTENSION -> SPACE -> CONTEXT_ALIGNMENT -> COUNTER_EVIDENCE", "upstream_engines_read": sorted(ctx), "upstream_decisions_used": False, "upstream_gates_used": False, "upstream_scores_used": False, "independent_price_analysis": True, "both_sides_evaluated": True, "context_is_orientation_not_veto": True, "countertrend_location_not_promoted": True, "extension_requires_repricing_when_context_aligned": True, "confidence_is_win_probability": False, "decision_authority": "E9_ONLY"},
        "trade_decision_authority": False, "decision_authority": "E9_ONLY", "gate": None, "specialist_gate": "NONE", "specialists": {}, "specialists_active": False, "specialists_status": "NOT_USED",
    }
