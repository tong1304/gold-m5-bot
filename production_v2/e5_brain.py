from __future__ import annotations

"""Professional E5 Location / Value Brain.

E5 answers one question only:
    "Is the current price location advantageous?"

It is deliberately monolithic.  It does not import or execute any E5
sub-engine and it never makes the final trade decision.  E1-E4 evidence is
read as qualitative context; E5 independently recomputes location from price
and volatility data so an upstream label cannot manufacture a location edge.
E9 remains the only trade-decision authority.
"""

from math import isfinite
from statistics import mean, median
from typing import Any

ARCHITECTURE = "E5_SINGLE_PROFESSIONAL_LOCATION_BRAIN_V1"
QUESTION = "Is current location advantageous?"
MIN_BARS = 60
ATR_PERIOD = 14
VALUE_LOOKBACK = 20
STRUCTURE_LOOKBACK = 50
LIQUIDITY_LOOKBACK = 30
EXTENSION_LOOKBACK = 20
SPACE_LOOKBACK = 50


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
        if None in (o, h, l, c) or h < max(o, c) or l > min(o, c) or h < l:
            problems.append(f"BAR_{i}_OHLC_INVALID")
            continue
        valid.append({"open": o, "high": h, "low": l, "close": c})
    return valid, problems


def _atr(bars: list[dict[str, float]], period: int = ATR_PERIOD) -> float:
    sample = bars[-period:]
    if not sample:
        return 0.0
    trs: list[float] = []
    previous = None
    for bar in sample:
        h, l, c = bar["high"], bar["low"], bar["close"]
        trs.append(h - l if previous is None else max(h - l, abs(h - previous), abs(l - previous)))
        previous = c
    return mean(trs) if trs else 0.0


def _vwap(bars: list[dict[str, float]], lookback: int = VALUE_LOOKBACK) -> float:
    sample = bars[-lookback:]
    if not sample:
        return 0.0
    weighted = 0.0
    volume = 0.0
    for bar in sample:
        # Use supplied volume when present only; otherwise equal-weight typical price.
        # _bars intentionally strips non-OHLC fields, so this is a price VWAP proxy.
        typical = (bar["high"] + bar["low"] + bar["close"]) / 3.0
        weighted += typical
        volume += 1.0
    return weighted / volume if volume else 0.0


def _range_levels(bars: list[dict[str, float]], lookback: int) -> tuple[float, float]:
    sample = bars[-lookback:]
    return min(x["low"] for x in sample), max(x["high"] for x in sample)


def _pivot_levels(bars: list[dict[str, float]], wing: int = 2) -> tuple[list[float], list[float]]:
    highs: list[float] = []
    lows: list[float] = []
    if len(bars) < 2 * wing + 1:
        return highs, lows
    for i in range(wing, len(bars) - wing):
        window = bars[i - wing : i + wing + 1]
        h, l = bars[i]["high"], bars[i]["low"]
        if h >= max(x["high"] for x in window):
            highs.append(h)
        if l <= min(x["low"] for x in window):
            lows.append(l)
    return highs[-8:], lows[-8:]


def _nearest_above(price: float, levels: list[float], tolerance: float) -> float | None:
    candidates = [x for x in levels if x > price + tolerance]
    return min(candidates) if candidates else None


def _nearest_below(price: float, levels: list[float], tolerance: float) -> float | None:
    candidates = [x for x in levels if x < price - tolerance]
    return max(candidates) if candidates else None


def _extract_upstream(permitted: dict[str, Any] | None) -> tuple[dict[str, Any], list[str], list[str]]:
    permitted = permitted or {}
    context: dict[str, Any] = {}
    evidence: list[str] = []
    conflicts: list[str] = []
    for engine_id in ("E1", "E2", "E3", "E4"):
        package = permitted.get(engine_id)
        if not isinstance(package, dict):
            continue
        payload = package.get("evidence") or package.get("output") or {}
        if isinstance(payload, dict):
            # Only qualitative evidence is consumed.  Explicit decisions/gates/scores
            # are intentionally excluded from E5 reasoning.
            clean = {k: v for k, v in payload.items() if str(k).lower() not in {"decision", "trade_decision", "score", "decision_score", "gate", "gate_passed", "specialist_gate"}}
            context[engine_id] = clean
            evidence.append(f"{engine_id}_QUALITATIVE_CONTEXT")
            tokens = str(clean).upper()
            if "CONFLICT" in tokens or "MIXED" in tokens:
                conflicts.append(f"{engine_id}_MIXED_CONTEXT")
    return context, evidence, conflicts


def _direction_from_context(context: dict[str, Any]) -> str:
    text = str(context).upper()
    up = any(t in text for t in ("TREND_UP", "BULLISH", "DIRECTION=UP", "DIRECTIONAL_PRESSURE=BULLISH", "UPSTREAM_THESIS"))
    down = any(t in text for t in ("TREND_DOWN", "BEARISH", "DIRECTION=DOWN", "DIRECTIONAL_PRESSURE=BEARISH"))
    # Do not treat a generic word "UPSTREAM_THESIS" as directional evidence.
    up = "TREND_UP" in text or "BULLISH" in text or "DIRECTION=UP" in text
    down = "TREND_DOWN" in text or "BEARISH" in text or "DIRECTION=DOWN" in text
    return "UP" if up and not down else "DOWN" if down and not up else "NEUTRAL"


def _distance_in_atr(price: float, level: float | None, atr: float) -> float | None:
    if level is None or atr <= 0:
        return None
    return abs(price - level) / atr


def _location_label(direction: str, value_position: float, extension_atr: float, space_atr: float | None, nearest_target_atr: float | None) -> str:
    if extension_atr >= 2.5:
        return "EXTENDED"
    if extension_atr >= 1.75:
        return "LATE"
    if space_atr is not None and space_atr < 1.0:
        return "CROWDED"
    if direction == "UP":
        if value_position <= 0.35:
            return "ATTRACTIVE_LONG"
        if value_position >= 0.80:
            return "PREMIUM_LONG"
        return "NEUTRAL_LONG"
    if direction == "DOWN":
        if value_position >= 0.65:
            return "ATTRACTIVE_SHORT"
        if value_position <= 0.20:
            return "DISCOUNT_SHORT"
        return "NEUTRAL_SHORT"
    if value_position <= 0.20:
        return "LOWER_VALUE"
    if value_position >= 0.80:
        return "UPPER_VALUE"
    return "EQUILIBRIUM"


def _confidence(components: dict[str, float], conflicts: int, data_quality: float) -> float:
    # Confidence describes the quality of the location analysis, not win probability.
    base = mean(components.values()) if components else 0.0
    penalty = min(0.24, conflicts * 0.04)
    return round(max(0.0, min(0.99, 0.15 + 0.65 * base + 0.20 * data_quality - penalty)), 3)


def _incomplete(reason: str, problems: list[str]) -> dict[str, Any]:
    return {
        "architecture": ARCHITECTURE,
        "question": QUESTION,
        "location_state": "UNRESOLVED",
        "direction": "NEUTRAL",
        "value_state": "UNKNOWN",
        "structural_location": "UNKNOWN",
        "liquidity_location": "UNKNOWN",
        "extension_state": "UNKNOWN",
        "available_space": "UNKNOWN",
        "location_quality": "UNRESOLVED",
        "confidence": 0.0,
        "evidence": problems,
        "counter_evidence": [],
        "conflicts": problems,
        "reason_codes": ["E5_DATA_INCOMPLETE"],
        "reasoning_trace": [f"QUESTION -> {QUESTION}", f"DATA_QUALITY -> {reason}"],
        "professional_reasoning": {
            "question": QUESTION,
            "task": "ASSESS_PRICE_LOCATION_ONLY",
            "thesis": reason,
            "evidence_hierarchy": "VALUE -> STRUCTURE -> LIQUIDITY -> EXTENSION -> SPACE -> QUALITY",
            "decision_authority": "E9_ONLY",
        },
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
        "gate": None,
        "specialists": {},
        "specialists_active": False,
        "specialists_status": "NOT_USED",
    }


def analyze_e5(snapshot: dict[str, Any], permitted: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the complete E5 location/value analysis as one professional brain."""
    bars, problems = _bars(snapshot)
    if len(bars) < MIN_BARS:
        return _incomplete(f"reliable candles below minimum {MIN_BARS}", problems[:8])

    atr = _atr(bars)
    if atr <= 0:
        return _incomplete("ATR invalid; location cannot be normalized", ["ATR_INVALID"])

    price = bars[-1]["close"]
    lo, hi = _range_levels(bars, VALUE_LOOKBACK)
    value_width = max(hi - lo, atr)
    value_position = max(0.0, min(1.0, (price - lo) / value_width))
    value = _vwap(bars, VALUE_LOOKBACK)
    value_distance_atr = (price - value) / atr

    structural_high, structural_low = _range_levels(bars, STRUCTURE_LOOKBACK)
    piv_highs, piv_lows = _pivot_levels(bars)
    all_highs = piv_highs + [structural_high]
    all_lows = piv_lows + [structural_low]
    tolerance = 0.15 * atr

    context, upstream_evidence, upstream_conflicts = _extract_upstream(permitted)
    direction = _direction_from_context(context)
    e3 = context.get("E3", {})
    e4 = context.get("E4", {})

    # Structural location: identify whether price is near a meaningful swing edge.
    above_distance = _distance_in_atr(price, _nearest_above(price, all_highs, tolerance), atr)
    below_distance = _distance_in_atr(price, _nearest_below(price, all_lows, tolerance), atr)
    near_high = above_distance is not None and above_distance <= 0.75
    near_low = below_distance is not None and below_distance <= 0.75
    structural_location = "AT_RESISTANCE" if near_high else "AT_SUPPORT" if near_low else "INSIDE_STRUCTURE"

    # Liquidity location: use E4 qualitative evidence plus independently detected
    # prior extremes. E5 does not accept E4's score or gate as truth.
    recent_high = max(x["high"] for x in bars[-LIQUIDITY_LOOKBACK - 1 : -1])
    recent_low = min(x["low"] for x in bars[-LIQUIDITY_LOOKBACK - 1 : -1])
    sweep_high = bars[-1]["high"] > recent_high and price < recent_high
    sweep_low = bars[-1]["low"] < recent_low and price > recent_low
    e4_text = str(e4).upper()
    e4_sweep_high = "SWEEP_HIGH" in e4_text or "HIGH_SWEEP" in e4_text
    e4_sweep_low = "SWEEP_LOW" in e4_text or "LOW_SWEEP" in e4_text
    liquidity_location = (
        "SELL_SIDE_LIQUIDITY_SWEPT" if sweep_low or e4_sweep_low else
        "BUY_SIDE_LIQUIDITY_SWEPT" if sweep_high or e4_sweep_high else
        "NEAR_BUY_SIDE_LIQUIDITY" if near_high else
        "NEAR_SELL_SIDE_LIQUIDITY" if near_low else
        "LIQUIDITY_UNCLEAR"
    )

    # Extension: compare current displacement from the local value and the recent
    # impulse. A professional trader distinguishes being directionally right from
    # being late to the move.
    closes = [x["close"] for x in bars]
    impulse_start = closes[-EXTENSION_LOOKBACK]
    displacement_atr = abs(price - impulse_start) / atr
    extension_atr = abs(price - value) / atr
    if extension_atr < 0.75:
        extension_state = "NORMAL"
    elif extension_atr < 1.5:
        extension_state = "STRETCHED"
    elif extension_atr < 2.5:
        extension_state = "EXTENDED"
    else:
        extension_state = "EXCESSIVE"

    # Available space is directional and forward-looking, but not a trade plan.
    # E5 identifies room to the next structural/liquidity obstacle; E8 still owns
    # final risk/reward economics.
    next_high = _nearest_above(price, all_highs, tolerance)
    next_low = _nearest_below(price, all_lows, tolerance)
    up_space_atr = _distance_in_atr(price, next_high, atr)
    down_space_atr = _distance_in_atr(price, next_low, atr)
    if direction == "UP":
        space_atr = up_space_atr
    elif direction == "DOWN":
        space_atr = down_space_atr
    else:
        candidates = [x for x in (up_space_atr, down_space_atr) if x is not None]
        space_atr = min(candidates) if candidates else None

    if space_atr is None:
        space_state = "OPEN"
    elif space_atr < 1.0:
        space_state = "TIGHT"
    elif space_atr < 2.0:
        space_state = "MODERATE"
    else:
        space_state = "OPEN"

    # Directional location quality is deliberately asymmetric: a trend direction
    # at a bad price can be a bad trade location. E3/E4 provide context, never a veto.
    long_location = (
        value_position <= 0.45 and not near_high and extension_atr < 1.75 and (up_space_atr is None or up_space_atr >= 1.0)
    )
    short_location = (
        value_position >= 0.55 and not near_low and extension_atr < 1.75 and (down_space_atr is None or down_space_atr >= 1.0)
    )
    if sweep_low and value_position <= 0.55:
        long_location = True
    if sweep_high and value_position >= 0.45:
        short_location = True

    label = _location_label(direction, value_position, extension_atr, space_atr, space_atr)
    if direction == "UP":
        quality = "HIGH" if long_location else "LOW"
    elif direction == "DOWN":
        quality = "HIGH" if short_location else "LOW"
    else:
        quality = "BIDIRECTIONAL_CONTEXT" if long_location and short_location else "LOW" if not (long_location or short_location) else "CONDITIONAL"

    value_quality = max(0.0, 1.0 - min(1.0, abs(value_distance_atr) / 2.0))
    structural_quality = 0.85 if near_low or near_high else 0.60
    liquidity_quality = 0.90 if sweep_low or sweep_high else 0.55 if (near_low or near_high) else 0.35
    extension_quality = max(0.05, 1.0 - min(1.0, extension_atr / 3.0))
    space_quality = 0.90 if space_atr is None or space_atr >= 2.0 else 0.65 if space_atr >= 1.0 else 0.20
    quality_components = {
        "value": value_quality,
        "structure": structural_quality,
        "liquidity": liquidity_quality,
        "extension": extension_quality,
        "space": space_quality,
    }
    data_quality = max(0.0, 1.0 - min(1.0, len(problems) / max(1, len(bars))))
    confidence = _confidence(quality_components, len(upstream_conflicts), data_quality)

    evidence = [
        f"price={price}", f"value={value:.6f}", f"value_distance_atr={value_distance_atr:.3f}",
        f"value_position={value_position:.3f}", f"structural_location={structural_location}",
        f"liquidity_location={liquidity_location}", f"extension_atr={extension_atr:.3f}",
        f"available_space_atr={space_atr if space_atr is not None else 'OPEN'}",
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
        counter.append("UPSTREAM_DIRECTION_BUT_POOR_LONG_LOCATION")
    if direction == "DOWN" and not short_location:
        counter.append("UPSTREAM_DIRECTION_BUT_POOR_SHORT_LOCATION")

    reason_codes: list[str] = []
    if label in {"ATTRACTIVE_LONG", "ATTRACTIVE_SHORT"}:
        reason_codes.append("LOCATION_ALIGNED")
    if extension_state in {"EXTENDED", "EXCESSIVE"}:
        reason_codes.append("EXTENSION_RISK")
    if space_state == "TIGHT":
        reason_codes.append("SPACE_CONSTRAINED")
    if sweep_low or sweep_high:
        reason_codes.append("LIQUIDITY_EVENT_AT_LOCATION")
    if upstream_conflicts:
        reason_codes.append("UPSTREAM_CONTEXT_CONFLICT")
    if not reason_codes:
        reason_codes.append("LOCATION_NEUTRAL")

    thesis = (
        f"E5 finds {label}: direction={direction}, value_position={value_position:.2f}, "
        f"extension={extension_state}, space={space_state}. "
        "Location quality is evidence for downstream setup/risk analysis, not an execution decision."
    )

    return {
        "architecture": ARCHITECTURE,
        "version": "1.0",
        "question": QUESTION,
        "task": "ASSESS_PRICE_LOCATION_ONLY",
        "location_state": label,
        "location_quality": quality,
        "direction": direction,
        "value_state": "DISCOUNT" if value_position <= 0.35 else "PREMIUM" if value_position >= 0.65 else "EQUILIBRIUM",
        "value": value,
        "value_distance_atr": round(value_distance_atr, 4),
        "value_position": round(value_position, 4),
        "structural_location": structural_location,
        "structural_high": structural_high,
        "structural_low": structural_low,
        "distance_to_next_high_atr": None if up_space_atr is None else round(up_space_atr, 4),
        "distance_to_next_low_atr": None if down_space_atr is None else round(down_space_atr, 4),
        "liquidity_location": liquidity_location,
        "sweep_high": sweep_high or e4_sweep_high,
        "sweep_low": sweep_low or e4_sweep_low,
        "extension_state": extension_state,
        "extension_atr": round(extension_atr, 4),
        "impulse_displacement_atr": round(displacement_atr, 4),
        "available_space": space_state,
        "available_space_atr": None if space_atr is None else round(space_atr, 4),
        "up_space_atr": None if up_space_atr is None else round(up_space_atr, 4),
        "down_space_atr": None if down_space_atr is None else round(down_space_atr, 4),
        "long_location_valid": long_location,
        "short_location_valid": short_location,
        "quality_components": {k: round(v, 4) for k, v in quality_components.items()},
        "confidence": confidence,
        "evidence": evidence,
        "counter_evidence": counter,
        "conflicts": upstream_conflicts,
        "reason_codes": reason_codes,
        "reasoning_trace": [
            f"QUESTION -> {QUESTION}",
            "VALUE -> price versus local equilibrium",
            "STRUCTURE -> price versus structural extremes",
            "LIQUIDITY -> independent sweep/extreme assessment plus E4 qualitative context",
            "EXTENSION -> displacement versus ATR/value",
            "SPACE -> distance to next structural obstacle",
            f"QUALITY -> {quality}",
            f"THESIS -> {thesis}",
        ],
        "professional_reasoning": {
            "question": QUESTION,
            "thesis": thesis,
            "evidence_hierarchy": "VALUE -> STRUCTURE -> LIQUIDITY -> EXTENSION -> SPACE -> QUALITY",
            "upstream_engines_read": sorted(context),
            "upstream_decisions_used": False,
            "upstream_gates_used": False,
            "upstream_scores_used": False,
            "independent_price_analysis": True,
            "e3_context_available": bool(e3),
            "e4_context_available": bool(e4),
            "decision_authority": "E9_ONLY",
        },
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
        "gate": None,
        "specialist_gate": "NONE",
        "specialists": {},
        "specialists_active": False,
        "specialists_status": "NOT_USED",
    }
