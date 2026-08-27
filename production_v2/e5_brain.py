from __future__ import annotations

"""E5 — Professional Location / Value Brain.

E5 answers exactly one question:
    "Is the current price location advantageous?"

Design rules:
- one monolithic brain; no E5 sub-engines
- E1-E4 are qualitative context only; their decisions, gates and scores are not used
- all location evidence is independently derived from the closed-candle price series
- E5 never makes a BUY/SELL or execution decision; E9 is the only trade authority
- confidence describes location-analysis quality, not win probability
- every conclusion must be explainable through observable evidence
"""

from math import isfinite
from statistics import mean
from typing import Any

ARCHITECTURE = "E5_SINGLE_PROFESSIONAL_LOCATION_BRAIN_V2"
VERSION = "2.0"
QUESTION = "Is current location advantageous?"
MIN_BARS = 60
ATR_PERIOD = 14
VALUE_LOOKBACK = 20
STRUCTURE_LOOKBACK = 50
LIQUIDITY_LOOKBACK = 30
EXTENSION_LOOKBACK = 20


_FORBIDDEN_UPSTREAM_KEYS = {
    "decision", "trade_decision", "score", "decision_score", "gate",
    "gate_passed", "specialist_gate", "execution", "order", "entry",
}


def _num(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if isfinite(x) else None


def _bars(snapshot: dict[str, Any]) -> tuple[list[dict[str, float]], list[str]]:
    raw = snapshot.get("bars") or []
    valid: list[dict[str, float]] = []
    problems: list[str] = []
    for i, bar in enumerate(raw):
        if not isinstance(bar, dict):
            problems.append(f"BAR_{i}_INVALID")
            continue
        o, h, l, c = (_num(bar.get(k)) for k in ("open", "high", "low", "close"))
        v = _num(bar.get("volume"))
        if None in (o, h, l, c) or h < max(o, c) or l > min(o, c) or h < l:
            problems.append(f"BAR_{i}_OHLC_INVALID")
            continue
        item: dict[str, float] = {"open": o, "high": h, "low": l, "close": c}
        if v is not None and v >= 0:
            item["volume"] = v
        valid.append(item)
    return valid, problems


def _atr(bars: list[dict[str, float]], period: int = ATR_PERIOD) -> float:
    sample = bars[-period:]
    if not sample:
        return 0.0
    trs: list[float] = []
    previous_close: float | None = None
    for bar in sample:
        h, l, c = bar["high"], bar["low"], bar["close"]
        tr = h - l if previous_close is None else max(h - l, abs(h - previous_close), abs(l - previous_close))
        trs.append(tr)
        previous_close = c
    return mean(trs) if trs else 0.0


def _value_price(bars: list[dict[str, float]], lookback: int = VALUE_LOOKBACK) -> tuple[float, str]:
    """Return volume-weighted typical price when volume exists; otherwise a transparent proxy."""
    sample = bars[-lookback:]
    if not sample:
        return 0.0, "UNAVAILABLE"
    has_volume = any("volume" in b and b["volume"] > 0 for b in sample)
    weighted = 0.0
    weight = 0.0
    for bar in sample:
        typical = (bar["high"] + bar["low"] + bar["close"]) / 3.0
        w = bar.get("volume", 0.0) if has_volume else 1.0
        if w > 0:
            weighted += typical * w
            weight += w
    if weight <= 0:
        return mean((b["high"] + b["low"] + b["close"]) / 3.0 for b in sample), "EQUAL_WEIGHT_TYPICAL_PRICE"
    return weighted / weight, "VOLUME_WEIGHTED_TYPICAL_PRICE" if has_volume else "EQUAL_WEIGHT_TYPICAL_PRICE"


def _range_levels(bars: list[dict[str, float]], lookback: int) -> tuple[float, float]:
    sample = bars[-lookback:]
    return min(x["low"] for x in sample), max(x["high"] for x in sample)


def _pivot_levels(bars: list[dict[str, float]], wing: int = 2) -> tuple[list[float], list[float]]:
    highs: list[float] = []
    lows: list[float] = []
    if len(bars) < 2 * wing + 1:
        return highs, lows
    for i in range(wing, len(bars) - wing):
        window = bars[i - wing:i + wing + 1]
        h, l = bars[i]["high"], bars[i]["low"]
        if h >= max(x["high"] for x in window):
            highs.append(h)
        if l <= min(x["low"] for x in window):
            lows.append(l)
    return highs[-8:], lows[-8:]


def _nearest_above(price: float, levels: list[float], tolerance: float) -> float | None:
    values = [x for x in levels if x > price + tolerance]
    return min(values) if values else None


def _nearest_below(price: float, levels: list[float], tolerance: float) -> float | None:
    values = [x for x in levels if x < price - tolerance]
    return max(values) if values else None


def _distance_atr(price: float, level: float | None, atr: float) -> float | None:
    if level is None or atr <= 0:
        return None
    return abs(price - level) / atr


def _extract_upstream(permitted: dict[str, Any] | None) -> tuple[dict[str, Any], list[str], list[str]]:
    context: dict[str, Any] = {}
    evidence: list[str] = []
    conflicts: list[str] = []
    for engine_id in ("E1", "E2", "E3", "E4"):
        package = (permitted or {}).get(engine_id)
        if not isinstance(package, dict):
            continue
        payload = package.get("evidence") or package.get("output") or {}
        if not isinstance(payload, dict):
            continue
        clean = {k: v for k, v in payload.items() if str(k).lower() not in _FORBIDDEN_UPSTREAM_KEYS}
        context[engine_id] = clean
        evidence.append(f"{engine_id}_QUALITATIVE_CONTEXT_READ")
        text = str(clean).upper()
        if "CONFLICT" in text or "MIXED" in text or "UNRESOLVED" in text:
            conflicts.append(f"{engine_id}_CONTEXT_CONFLICT")
    return context, evidence, conflicts


def _direction_from_context(context: dict[str, Any]) -> str:
    text = str(context).upper()
    up = any(token in text for token in ("TREND_UP", "BULLISH", "DIRECTION=UP", "PRESSURE=BULLISH"))
    down = any(token in text for token in ("TREND_DOWN", "BEARISH", "DIRECTION=DOWN", "PRESSURE=BEARISH"))
    return "UP" if up and not down else "DOWN" if down and not up else "NEUTRAL"


def _quality_label(direction: str, value_position: float, extension_atr: float, space_atr: float | None,
                   near_high: bool, near_low: bool, sweep_high: bool, sweep_low: bool) -> str:
    if extension_atr >= 2.5:
        return "EXTENDED"
    if extension_atr >= 1.75:
        return "LATE"
    if space_atr is not None and space_atr < 1.0:
        return "CROWDED"
    if direction == "UP":
        if sweep_low and value_position <= 0.65 and not near_high:
            return "RECLAIM_LONG"
        if value_position <= 0.35 and not near_high:
            return "ATTRACTIVE_LONG"
        if value_position >= 0.80 or near_high:
            return "PREMIUM_LONG"
        return "NEUTRAL_LONG"
    if direction == "DOWN":
        if sweep_high and value_position >= 0.35 and not near_low:
            return "RECLAIM_SHORT"
        if value_position >= 0.65 and not near_low:
            return "ATTRACTIVE_SHORT"
        if value_position <= 0.20 or near_low:
            return "DISCOUNT_SHORT"
        return "NEUTRAL_SHORT"
    if value_position <= 0.20:
        return "LOWER_VALUE"
    if value_position >= 0.80:
        return "UPPER_VALUE"
    return "EQUILIBRIUM"


def _incomplete(reason: str, problems: list[str]) -> dict[str, Any]:
    return {
        "architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION,
        "task": "ASSESS_PRICE_LOCATION_ONLY", "location_state": "UNRESOLVED",
        "location_quality": "UNRESOLVED", "direction": "NEUTRAL",
        "value_state": "UNKNOWN", "structural_location": "UNKNOWN",
        "liquidity_location": "UNKNOWN", "extension_state": "UNKNOWN",
        "available_space": "UNKNOWN", "confidence": 0.0,
        "evidence": problems, "counter_evidence": [], "conflicts": problems,
        "reason_codes": ["E5_DATA_INCOMPLETE"],
        "reasoning_trace": [f"QUESTION -> {QUESTION}", f"DATA_QUALITY -> {reason}"],
        "professional_reasoning": {
            "question": QUESTION, "task": "ASSESS_PRICE_LOCATION_ONLY", "thesis": reason,
            "evidence_hierarchy": "VALUE -> STRUCTURE -> LIQUIDITY -> EXTENSION -> SPACE -> COUNTER_EVIDENCE",
            "decision_authority": "E9_ONLY", "upstream_decisions_used": False,
        },
        "trade_decision_authority": False, "decision_authority": "E9_ONLY",
        "gate": None, "specialist_gate": "NONE", "specialists": {},
        "specialists_active": False, "specialists_status": "NOT_USED",
    }


def analyze_e5(snapshot: dict[str, Any], permitted: dict[str, Any] | None = None) -> dict[str, Any]:
    """Analyze location independently as a single professional specialist brain."""
    bars, problems = _bars(snapshot)
    if len(bars) < MIN_BARS:
        return _incomplete(f"reliable candles below minimum {MIN_BARS}", problems[:8])
    atr = _atr(bars)
    if atr <= 0:
        return _incomplete("ATR invalid; location cannot be normalized", ["ATR_INVALID"])

    price = bars[-1]["close"]
    value, value_method = _value_price(bars)
    value_distance_atr = (price - value) / atr
    value_lo, value_hi = _range_levels(bars, VALUE_LOOKBACK)
    value_width = max(value_hi - value_lo, atr)
    value_position = max(0.0, min(1.0, (price - value_lo) / value_width))

    structural_low, structural_high = _range_levels(bars, STRUCTURE_LOOKBACK)
    pivot_highs, pivot_lows = _pivot_levels(bars)
    highs = pivot_highs + [structural_high]
    lows = pivot_lows + [structural_low]
    tolerance = 0.15 * atr
    next_high = _nearest_above(price, highs, tolerance)
    next_low = _nearest_below(price, lows, tolerance)
    up_space_atr = _distance_atr(price, next_high, atr)
    down_space_atr = _distance_atr(price, next_low, atr)

    context, upstream_evidence, upstream_conflicts = _extract_upstream(permitted)
    direction = _direction_from_context(context)

    near_high = _distance_atr(price, structural_high, atr) <= 0.75
    near_low = _distance_atr(price, structural_low, atr) <= 0.75
    structural_location = "AT_RESISTANCE" if near_high else "AT_SUPPORT" if near_low else "INSIDE_STRUCTURE"

    prior = bars[-LIQUIDITY_LOOKBACK - 1:-1]
    recent_high = max(b["high"] for b in prior)
    recent_low = min(b["low"] for b in prior)
    sweep_high = bars[-1]["high"] > recent_high and price < recent_high
    sweep_low = bars[-1]["low"] < recent_low and price > recent_low
    e4_text = str(context.get("E4", {})).upper()
    e4_sweep_high = "SWEEP_HIGH" in e4_text or "HIGH_SWEEP" in e4_text
    e4_sweep_low = "SWEEP_LOW" in e4_text or "LOW_SWEEP" in e4_text
    sweep_high = sweep_high or e4_sweep_high
    sweep_low = sweep_low or e4_sweep_low
    liquidity_location = (
        "SELL_SIDE_LIQUIDITY_SWEPT" if sweep_low else
        "BUY_SIDE_LIQUIDITY_SWEPT" if sweep_high else
        "NEAR_BUY_SIDE_LIQUIDITY" if near_high else
        "NEAR_SELL_SIDE_LIQUIDITY" if near_low else "LIQUIDITY_UNCLEAR"
    )

    impulse_start = bars[-EXTENSION_LOOKBACK]["close"]
    impulse_displacement_atr = abs(price - impulse_start) / atr
    extension_atr = abs(value_distance_atr)
    extension_state = (
        "NORMAL" if extension_atr < 0.75 else
        "STRETCHED" if extension_atr < 1.50 else
        "EXTENDED" if extension_atr < 2.50 else "EXCESSIVE"
    )

    if direction == "UP":
        space_atr = up_space_atr
    elif direction == "DOWN":
        space_atr = down_space_atr
    else:
        candidates = [x for x in (up_space_atr, down_space_atr) if x is not None]
        space_atr = min(candidates) if candidates else None
    space_state = "OPEN" if space_atr is None or space_atr >= 2.0 else "MODERATE" if space_atr >= 1.0 else "TIGHT"

    # A liquidity sweep is evidence of a location event, not permission to chase.
    # It can improve location only when value and structural conditions also agree.
    long_location = (
        direction in ("UP", "NEUTRAL") and value_position <= 0.45 and
        not near_high and extension_atr < 1.75 and (up_space_atr is None or up_space_atr >= 1.0)
    )
    short_location = (
        direction in ("DOWN", "NEUTRAL") and value_position >= 0.55 and
        not near_low and extension_atr < 1.75 and (down_space_atr is None or down_space_atr >= 1.0)
    )
    if sweep_low and value_position <= 0.60 and not near_high and extension_atr < 1.75:
        long_location = long_location or (up_space_atr is None or up_space_atr >= 1.0)
    if sweep_high and value_position >= 0.40 and not near_low and extension_atr < 1.75:
        short_location = short_location or (down_space_atr is None or down_space_atr >= 1.0)

    label = _quality_label(direction, value_position, extension_atr, space_atr, near_high, near_low, sweep_high, sweep_low)
    if direction == "UP":
        quality = "HIGH" if long_location else "LOW"
    elif direction == "DOWN":
        quality = "HIGH" if short_location else "LOW"
    else:
        quality = "CONDITIONAL" if long_location or short_location else "LOW"

    value_quality = max(0.0, 1.0 - min(1.0, abs(value_distance_atr) / 2.0))
    structure_quality = 0.90 if near_low or near_high else 0.65
    liquidity_quality = 0.90 if sweep_low or sweep_high else 0.60 if (near_low or near_high) else 0.35
    extension_quality = max(0.05, 1.0 - min(1.0, extension_atr / 3.0))
    space_quality = 0.90 if space_atr is None or space_atr >= 2.0 else 0.65 if space_atr >= 1.0 else 0.20
    components = {"value": value_quality, "structure": structure_quality, "liquidity": liquidity_quality,
                  "extension": extension_quality, "space": space_quality}
    data_quality = max(0.0, 1.0 - min(1.0, len(problems) / max(1, len(bars))))
    base = mean(components.values())
    confidence = round(max(0.0, min(0.99, 0.15 + 0.65 * base + 0.20 * data_quality - min(0.24, 0.04 * len(upstream_conflicts)))), 3)

    evidence = [
        f"price={price:.6f}", f"atr14={atr:.6f}", f"value={value:.6f}", f"value_method={value_method}",
        f"value_distance_atr={value_distance_atr:.3f}", f"value_position={value_position:.3f}",
        f"structural_location={structural_location}", f"structural_high={structural_high:.6f}", f"structural_low={structural_low:.6f}",
        f"distance_to_next_high_atr={up_space_atr if up_space_atr is not None else 'OPEN'}",
        f"distance_to_next_low_atr={down_space_atr if down_space_atr is not None else 'OPEN'}",
        f"liquidity_location={liquidity_location}", f"sweep_high={sweep_high}", f"sweep_low={sweep_low}",
        f"extension_atr={extension_atr:.3f}", f"extension_state={extension_state}",
        f"impulse_displacement_atr={impulse_displacement_atr:.3f}",
        f"available_space={space_state}", f"available_space_atr={space_atr if space_atr is not None else 'OPEN'}",
        f"long_location_valid={long_location}", f"short_location_valid={short_location}",
        f"directional_context={direction}",
    ] + upstream_evidence

    counter: list[str] = []
    if near_high:
        counter.append("PRICE_NEAR_STRUCTURAL_HIGH")
    if near_low:
        counter.append("PRICE_NEAR_STRUCTURAL_LOW")
    if extension_atr >= 1.75:
        counter.append("LATE_OR_EXTENDED_PRICE")
    if space_atr is not None and space_atr < 1.0:
        counter.append("LIMITED_AVAILABLE_SPACE")
    if direction == "UP" and not long_location:
        counter.append("BULLISH_CONTEXT_BUT_POOR_LONG_LOCATION")
    if direction == "DOWN" and not short_location:
        counter.append("BEARISH_CONTEXT_BUT_POOR_SHORT_LOCATION")
    counter.extend(upstream_conflicts)

    reasons: list[str] = []
    if label in {"ATTRACTIVE_LONG", "ATTRACTIVE_SHORT", "RECLAIM_LONG", "RECLAIM_SHORT"}:
        reasons.append("LOCATION_ALIGNED")
    if extension_state in {"EXTENDED", "EXCESSIVE"}:
        reasons.append("EXTENSION_RISK")
    if extension_state == "STRETCHED":
        reasons.append("EXTENSION_ELEVATED")
    if space_state == "TIGHT":
        reasons.append("SPACE_CONSTRAINED")
    if sweep_low or sweep_high:
        reasons.append("LIQUIDITY_EVENT_AT_LOCATION")
    if upstream_conflicts:
        reasons.append("UPSTREAM_CONTEXT_CONFLICT")
    if not reasons:
        reasons.append("LOCATION_NEUTRAL")

    thesis = (
        f"Current location is {label}: direction={direction}, value_position={value_position:.2f}, "
        f"value_distance={value_distance_atr:.2f} ATR, extension={extension_state}, "
        f"space={space_state}. Location quality={quality}. "
        "This is location evidence only; execution remains downstream."
    )

    return {
        "architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION,
        "task": "ASSESS_PRICE_LOCATION_ONLY", "location_state": label, "location_quality": quality,
        "direction": direction,
        "value_state": "DISCOUNT" if value_position <= 0.35 else "PREMIUM" if value_position >= 0.65 else "EQUILIBRIUM",
        "value": round(value, 6), "value_method": value_method,
        "value_distance_atr": round(value_distance_atr, 4), "value_position": round(value_position, 4),
        "structural_location": structural_location, "structural_high": structural_high, "structural_low": structural_low,
        "distance_to_next_high_atr": None if up_space_atr is None else round(up_space_atr, 4),
        "distance_to_next_low_atr": None if down_space_atr is None else round(down_space_atr, 4),
        "liquidity_location": liquidity_location, "sweep_high": sweep_high, "sweep_low": sweep_low,
        "extension_state": extension_state, "extension_atr": round(extension_atr, 4),
        "impulse_displacement_atr": round(impulse_displacement_atr, 4),
        "available_space": space_state, "available_space_atr": None if space_atr is None else round(space_atr, 4),
        "up_space_atr": None if up_space_atr is None else round(up_space_atr, 4),
        "down_space_atr": None if down_space_atr is None else round(down_space_atr, 4),
        "long_location_valid": long_location, "short_location_valid": short_location,
        "quality_components": {k: round(v, 4) for k, v in components.items()}, "confidence": confidence,
        "evidence": evidence, "counter_evidence": counter, "conflicts": upstream_conflicts,
        "reason_codes": reasons,
        "reasoning_trace": [
            f"QUESTION -> {QUESTION}",
            f"DATA_QUALITY -> valid_bars={len(bars)} invalid_bars={len(problems)} atr14={atr:.4f}",
            f"VALUE -> method={value_method} position={value_position:.3f} distance={value_distance_atr:.3f}ATR",
            f"STRUCTURE -> {structural_location} next_high={up_space_atr}ATR next_low={down_space_atr}ATR",
            f"LIQUIDITY -> {liquidity_location} sweep_high={sweep_high} sweep_low={sweep_low}",
            f"EXTENSION -> {extension_state} distance={extension_atr:.3f}ATR impulse={impulse_displacement_atr:.3f}ATR",
            f"SPACE -> {space_state} directional_space={space_atr}",
            f"COUNTER_EVIDENCE -> {counter if counter else 'NONE'}",
            f"THESIS -> {thesis}",
            f"AUTHORITY -> E5_LOCATION_ONLY; E9_ONLY_EXECUTION_DECISION",
        ],
        "professional_reasoning": {
            "question": QUESTION, "thesis": thesis,
            "evidence_hierarchy": "VALUE -> STRUCTURE -> LIQUIDITY -> EXTENSION -> SPACE -> COUNTER_EVIDENCE -> THESIS",
            "upstream_engines_read": sorted(context), "upstream_decisions_used": False,
            "upstream_gates_used": False, "upstream_scores_used": False,
            "independent_price_analysis": True, "confidence_is_win_probability": False,
            "decision_authority": "E9_ONLY",
        },
        "trade_decision_authority": False, "decision_authority": "E9_ONLY",
        "gate": None, "specialist_gate": "NONE", "specialists": {},
        "specialists_active": False, "specialists_status": "NOT_USED",
    }
