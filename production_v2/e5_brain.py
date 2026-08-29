from __future__ import annotations

"""E5 — Professional Location / Value Brain v7.0.

E5 answers one specialist question only:
    "Is current location advantageous?"

Location, space, extension and liquidity are deliberately separated. LONG and
SHORT are evaluated independently. E1–E4 provide contextual compatibility,
never an execution gate. E5 has no order authority; E9 remains the sole master.
"""

from math import isfinite
from statistics import mean
from typing import Any

ARCHITECTURE = "E5_SINGLE_PROFESSIONAL_LOCATION_BRAIN_V7_0"
VERSION = "7.0"
QUESTION = "Is current location advantageous?"
MIN_BARS = 80
ATR_PERIOD = 14
VALUE_LOOKBACK = 20
STRUCTURE_LOOKBACK = 60
LIQUIDITY_LOOKBACK = 30
PIVOT_WING = 2


def _num(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if isfinite(x) else None


def _bars(snapshot: dict[str, Any]) -> tuple[list[dict[str, float]], list[str]]:
    bars: list[dict[str, float]] = []
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
        b: dict[str, float] = {"open": o, "high": h, "low": l, "close": c}  # type: ignore[dict-item]
        if v is not None and v >= 0:
            b["volume"] = v
        bars.append(b)
    return bars, problems


def _atr(bars: list[dict[str, float]], period: int = ATR_PERIOD) -> float:
    if len(bars) < 2:
        return 0.0
    sample = bars[-(period + 1):]
    trs: list[float] = []
    for i, bar in enumerate(sample):
        prev = sample[i - 1]["close"] if i else None
        trs.append(
            bar["high"] - bar["low"]
            if prev is None
            else max(
                bar["high"] - bar["low"],
                abs(bar["high"] - prev),
                abs(bar["low"] - prev),
            )
        )
    return mean(trs[-period:]) if trs else 0.0


def _range(bars: list[dict[str, float]], lookback: int) -> tuple[float, float]:
    sample = bars[-lookback:]
    return min(b["low"] for b in sample), max(b["high"] for b in sample)


def _value_price(bars: list[dict[str, float]]) -> tuple[float, str]:
    sample = bars[-VALUE_LOOKBACK:]
    prices = [(b["high"] + b["low"] + b["close"]) / 3.0 for b in sample]
    has_volume = any(b.get("volume", 0.0) > 0 for b in sample)
    weights = [b.get("volume", 0.0) if has_volume else 1.0 for b in sample]
    total = sum(weights)
    if total <= 0:
        return mean(prices), "EQUAL_WEIGHT_TYPICAL_PRICE"
    return sum(p * w for p, w in zip(prices, weights)) / total, (
        "VOLUME_WEIGHTED_TYPICAL_PRICE" if has_volume else "EQUAL_WEIGHT_TYPICAL_PRICE"
    )


def _pivots(bars: list[dict[str, float]], wing: int = PIVOT_WING) -> tuple[list[float], list[float]]:
    highs: list[float] = []
    lows: list[float] = []
    for i in range(wing, len(bars) - wing):
        window = bars[i - wing:i + wing + 1]
        if bars[i]["high"] >= max(x["high"] for x in window):
            highs.append(bars[i]["high"])
        if bars[i]["low"] <= min(x["low"] for x in window):
            lows.append(bars[i]["low"])
    return highs[-16:], lows[-16:]


def _nearest_above(price: float, levels: list[float], tolerance: float) -> float | None:
    values = [x for x in levels if x > price + tolerance]
    return min(values) if values else None


def _nearest_below(price: float, levels: list[float], tolerance: float) -> float | None:
    values = [x for x in levels if x < price - tolerance]
    return max(values) if values else None


def _dist_atr(price: float, level: float | None, atr: float) -> float | None:
    if level is None or atr <= 0:
        return None
    return abs(price - level) / atr


def _upstream(permitted: dict[str, Any] | None) -> tuple[dict[str, Any], list[str], list[str]]:
    context: dict[str, Any] = {}
    evidence: list[str] = []
    conflicts: list[str] = []
    for eid in ("E1", "E2", "E3", "E4"):
        package = (permitted or {}).get(eid)
        if not isinstance(package, dict):
            continue
        payload = package.get("evidence") or package.get("output") or {}
        if not isinstance(payload, dict):
            continue
        context[eid] = dict(payload)
        evidence.append(f"{eid}_QUALITATIVE_CONTEXT_READ")
        text = str(payload).upper()
        if any(t in text for t in ("CONFLICT", "MIXED", "UNRESOLVED", "PENDING")):
            conflicts.append(f"{eid}_CONTEXT_CONFLICT")
    return context, evidence, conflicts


def _context_direction(context: dict[str, Any]) -> str:
    text = str(context).upper()
    up = any(t in text for t in ("TREND_UP", "BULLISH", "DIRECTION=UP", "PRESSURE=BULLISH"))
    down = any(t in text for t in ("TREND_DOWN", "BEARISH", "DIRECTION=DOWN", "PRESSURE=BEARISH"))
    return "UP" if up and not down else "DOWN" if down and not up else "NEUTRAL"


def _sweeps(bars: list[dict[str, float]], context: dict[str, Any]) -> tuple[bool, bool]:
    prior = bars[-(LIQUIDITY_LOOKBACK + 1):-1]
    prior_high = max(b["high"] for b in prior)
    prior_low = min(b["low"] for b in prior)
    last = bars[-1]
    high_sweep = last["high"] > prior_high and last["close"] < prior_high
    low_sweep = last["low"] < prior_low and last["close"] > prior_low
    e4 = str(context.get("E4", {})).upper()
    return (
        high_sweep or "SWEEP_HIGH" in e4 or "HIGH_SWEEP" in e4,
        low_sweep or "SWEEP_LOW" in e4 or "LOW_SWEEP" in e4,
    )


def _label(score: float) -> str:
    if score >= 0.72:
        return "HIGH"
    if score >= 0.58:
        return "ACCEPTABLE"
    if score >= 0.45:
        return "CONDITIONAL"
    return "UNFAVORABLE"


def _space_label(space: float | None) -> str:
    if space is None:
        return "OPEN"
    if space >= 2.0:
        return "OPEN"
    if space >= 1.0:
        return "LIMITED"
    if space >= 0.5:
        return "CONSTRAINED"
    return "VERY_CONSTRAINED"


def _incomplete(reason: str, problems: list[str]) -> dict[str, Any]:
    evidence = problems or ["NO_RELIABLE_EVIDENCE"]
    return {
        "architecture": ARCHITECTURE,
        "version": VERSION,
        "question": QUESTION,
        "task": "ASSESS_PRICE_LOCATION_ONLY",
        "location_state": "UNRESOLVED",
        "location_quality": "UNRESOLVED",
        "direction": "NEUTRAL",
        "value_state": "UNKNOWN",
        "structural_location": "UNKNOWN",
        "liquidity_location": "UNKNOWN",
        "extension_state": "UNKNOWN",
        "available_space": "UNKNOWN",
        "long_location_quality": "UNKNOWN",
        "short_location_quality": "UNKNOWN",
        "preferred_location": "NONE",
        "confidence": 0.0,
        "evidence": evidence,
        "observations": evidence,
        "counter_evidence": [],
        "conflicts": problems,
        "reason_codes": ["E5_DATA_INCOMPLETE"],
        "reasoning_trace": [f"QUESTION -> {QUESTION}", f"DATA_QUALITY -> {reason}"],
        "professional_reasoning": {
            "question": QUESTION,
            "thesis": reason,
            "evidence_hierarchy": "VALUE -> STRUCTURE -> LIQUIDITY -> EXTENSION -> SPACE -> ASYMMETRY -> COUNTER_EVIDENCE",
            "upstream_decisions_used": False,
            "upstream_gates_used": False,
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


def analyze_e5(snapshot: dict[str, Any], permitted: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build an independent location thesis without making a trade decision."""
    bars, problems = _bars(snapshot)
    if len(bars) < MIN_BARS:
        return _incomplete(f"reliable candles below minimum {MIN_BARS}", problems[:8])

    atr = _atr(bars)
    if atr <= 0:
        return _incomplete("ATR invalid; location cannot be normalized", ["ATR_INVALID"])

    price = bars[-1]["close"]

    # 1) VALUE: position inside the recent auction and distance from its center.
    value, value_method = _value_price(bars)
    value_low, value_high = _range(bars, VALUE_LOOKBACK)
    value_width = max(value_high - value_low, atr)
    value_position = max(0.0, min(1.0, (price - value_low) / value_width))
    value_distance_atr = (price - value) / atr
    value_state = (
        "DISCOUNT" if value_position <= 0.35
        else "PREMIUM" if value_position >= 0.65
        else "EQUILIBRIUM"
    )

    # 2) STRUCTURE: nearest meaningful obstacle, not just direction.
    structure_low, structure_high = _range(bars, STRUCTURE_LOOKBACK)
    pivot_highs, pivot_lows = _pivots(bars)
    tolerance = 0.15 * atr
    next_resistance = _nearest_above(price, pivot_highs + [structure_high], tolerance)
    next_support = _nearest_below(price, pivot_lows + [structure_low], tolerance)
    long_space = _dist_atr(price, next_resistance, atr)
    short_space = _dist_atr(price, next_support, atr)
    near_resistance = (_dist_atr(price, structure_high, atr) or 999.0) <= 0.75
    near_support = (_dist_atr(price, structure_low, atr) or 999.0) <= 0.75
    structural_location = (
        "COMPRESSED_STRUCTURE" if near_resistance and near_support
        else "AT_RESISTANCE" if near_resistance
        else "AT_SUPPORT" if near_support
        else "INSIDE_STRUCTURE"
    )

    # 3) LIQUIDITY: fresh sweep/rejection evidence is separate from location.
    context, upstream_evidence, conflicts = _upstream(permitted)
    context_direction = _context_direction(context)
    sweep_high, sweep_low = _sweeps(bars, context)
    liquidity_location = (
        "BOTH_SWEEPS" if sweep_high and sweep_low
        else "HIGH_SWEEP" if sweep_high
        else "LOW_SWEEP" if sweep_low
        else "NO_FRESH_SWEEP"
    )

    # 4) EXTENSION: how far price has moved from recent value.
    extension_atr = abs(value_distance_atr)
    extension_state = (
        "NORMAL" if extension_atr < 0.75
        else "STRETCHED" if extension_atr < 1.5
        else "EXTENDED" if extension_atr < 2.5
        else "EXCESSIVE"
    )

    # 5) LONG/SHORT LOCATION THESIS.
    # Location is evaluated independently. Space and confirmation do not erase
    # the thesis; they are reported separately as constraints.
    def evaluate_side(side: str) -> tuple[float, list[str], list[str], dict[str, float]]:
        is_long = side == "LONG"
        favorable_value = value_position <= 0.35 if is_long else value_position >= 0.65
        adverse_value = value_position >= 0.65 if is_long else value_position <= 0.35
        opposing_structure = near_resistance if is_long else near_support
        supportive_sweep = sweep_low if is_long else sweep_high
        space = long_space if is_long else short_space

        value_component = 1.0 if favorable_value else 0.55 if not adverse_value else 0.10
        structure_component = 0.20 if opposing_structure else 0.85
        liquidity_component = 1.0 if supportive_sweep else 0.55
        extension_component = {
            "NORMAL": 1.0,
            "STRETCHED": 0.70,
            "EXTENDED": 0.40,
            "EXCESSIVE": 0.15,
        }[extension_state]
        space_component = (
            1.0 if space is None or space >= 2.0
            else 0.65 if space >= 1.0
            else 0.35 if space >= 0.5
            else 0.10
        )

        # Context compatibility is deliberately small. It prevents a premium
        # label from becoming an automatic counter-trend SHORT while preserving
        # the independent location thesis itself.
        counter_context = (
            (context_direction == "UP" and not is_long)
            or (context_direction == "DOWN" and is_long)
        )
        context_component = 0.65 if counter_context else 1.0

        score = round(
            0.25 * value_component
            + 0.15 * structure_component
            + 0.20 * liquidity_component
            + 0.20 * extension_component
            + 0.15 * space_component
            + 0.05 * context_component,
            4,
        )

        evidence: list[str] = []
        counter: list[str] = []
        if favorable_value:
            evidence.append("VALUE_FAVORABLE")
        if adverse_value:
            counter.append("VALUE_ADVERSE")
        if not opposing_structure:
            evidence.append("STRUCTURAL_SPACE_AVAILABLE")
        else:
            counter.append("OPPOSING_STRUCTURE_NEARBY")
        if supportive_sweep:
            evidence.append("LIQUIDITY_SWEEP_SUPPORTIVE")
        else:
            counter.append("NO_FRESH_LIQUIDITY_CONFIRMATION")
        if extension_state in {"NORMAL", "STRETCHED"}:
            evidence.append(f"EXTENSION_{extension_state}")
        else:
            counter.append("EXTENSION_RISK")
        if space is not None and space < 1.0:
            counter.append("SPACE_CONSTRAINED")
        if counter_context:
            counter.append(f"COUNTER_CONTEXT_{side}")
        return score, evidence, counter, {
            "value": value_component,
            "structure": structure_component,
            "liquidity": liquidity_component,
            "extension": extension_component,
            "space": space_component,
            "context_compatibility": context_component,
        }

    long_score, long_evidence, long_counter, long_components = evaluate_side("LONG")
    short_score, short_evidence, short_counter, short_components = evaluate_side("SHORT")

    # 6) ASYMMETRY: choose the stronger location thesis, but do not allow a
    # premium/discount label alone to manufacture a counter-trend preference.
    score_gap = abs(long_score - short_score)
    clear_long_context = context_direction == "UP"
    clear_short_context = context_direction == "DOWN"
    if clear_long_context and short_score > long_score and "VALUE_FAVORABLE" in short_evidence and score_gap < 0.20:
        preferred = "LONG" if long_score >= 0.45 else "BOTH_CONDITIONAL"
    elif clear_short_context and long_score > short_score and "VALUE_FAVORABLE" in long_evidence and score_gap < 0.20:
        preferred = "SHORT" if short_score >= 0.45 else "BOTH_CONDITIONAL"
    elif score_gap >= 0.08 and max(long_score, short_score) >= 0.45:
        preferred = "LONG" if long_score > short_score else "SHORT"
    elif max(long_score, short_score) >= 0.45:
        preferred = "BOTH_CONDITIONAL"
    else:
        preferred = "NONE"

    preferred_score = (
        long_score if preferred == "LONG"
        else short_score if preferred == "SHORT"
        else max(long_score, short_score)
    )
    preferred_space = (
        long_space if preferred == "LONG"
        else short_space if preferred == "SHORT"
        else None
    )

    # 7) FINAL LOCATION STATE keeps the thesis and its constraints visible.
    # This is not an entry signal. A good location can still be untradeable.
    if extension_state in {"EXTENDED", "EXCESSIVE"} and preferred_score < 0.72:
        location_state = "WAIT_REPRICING"
    elif preferred == "LONG" and long_space is not None and long_space < 1.0:
        location_state = "SPACE_CONSTRAINED"
    elif preferred == "SHORT" and short_space is not None and short_space < 1.0:
        location_state = "SPACE_CONSTRAINED"
    elif preferred == "LONG" and long_score >= 0.72:
        location_state = "ADVANTAGEOUS_LONG"
    elif preferred == "SHORT" and short_score >= 0.72:
        location_state = "ADVANTAGEOUS_SHORT"
    elif preferred in {"LONG", "SHORT"}:
        location_state = f"ACCEPTABLE_{preferred}"
    elif preferred == "BOTH_CONDITIONAL":
        location_state = "BOTH_CONDITIONAL"
    else:
        location_state = "UNFAVORABLE"

    # Confidence describes certainty of the location reading, not win rate.
    confidence = 0.55 + min(0.45, score_gap * 1.8)
    if value_state == "EQUILIBRIUM":
        confidence *= 0.90
    if conflicts:
        confidence *= max(0.55, 1.0 - 0.10 * len(conflicts))
    confidence = round(max(0.0, min(1.0, confidence)), 4)

    # Keep counter-evidence side-specific. The aggregate is intentionally a
    # labelled summary so downstream engines cannot confuse LONG evidence with
    # SHORT evidence.
    aggregate_counter = [
        *(f"LONG:{x}" for x in long_counter),
        *(f"SHORT:{x}" for x in short_counter),
        *(f"CONTEXT:{x}" for x in conflicts),
    ]
    reason_codes = [
        f"LOCATION_STATE_{location_state}",
        f"VALUE_{value_state}",
        f"EXTENSION_{extension_state}",
        f"LONG_LOCATION_{_label(long_score)}",
        f"SHORT_LOCATION_{_label(short_score)}",
    ]
    if long_space is not None and long_space < 1.0:
        reason_codes.append("LONG_SPACE_CONSTRAINED")
    if short_space is not None and short_space < 1.0:
        reason_codes.append("SHORT_SPACE_CONSTRAINED")
    if sweep_low:
        reason_codes.append("LOW_LIQUIDITY_SWEEP")
    if sweep_high:
        reason_codes.append("HIGH_LIQUIDITY_SWEEP")
    if conflicts:
        reason_codes.append("UPSTREAM_CONTEXT_CONFLICT")

    evidence = [
        f"PRICE={price:.5f}",
        f"ATR={atr:.5f}",
        f"VALUE={value:.5f}",
        f"VALUE_METHOD={value_method}",
        f"VALUE_STATE={value_state}",
        f"VALUE_DISTANCE_ATR={value_distance_atr:.3f}",
        f"STRUCTURE_HIGH={structure_high:.5f}",
        f"STRUCTURE_LOW={structure_low:.5f}",
        f"CONTEXT_DIRECTION={context_direction}",
        *upstream_evidence,
    ]
    observations = [
        f"LONG_LOCATION={long_score:.3f}/{_label(long_score)}",
        f"SHORT_LOCATION={short_score:.3f}/{_label(short_score)}",
        f"LONG_LOCATION_THESIS={long_evidence or 'NONE'}",
        f"SHORT_LOCATION_THESIS={short_evidence or 'NONE'}",
        f"LONG_COUNTER_EVIDENCE={long_counter or 'NONE'}",
        f"SHORT_COUNTER_EVIDENCE={short_counter or 'NONE'}",
        f"STRUCTURAL_LOCATION={structural_location}",
        f"LIQUIDITY_LOCATION={liquidity_location}",
        f"EXTENSION_STATE={extension_state}",
        f"LONG_SPACE={long_space if long_space is not None else 'UNKNOWN'}ATR/{_space_label(long_space)}",
        f"SHORT_SPACE={short_space if short_space is not None else 'UNKNOWN'}ATR/{_space_label(short_space)}",
        f"LOCATION_ASYMMETRY_GAP={score_gap:.3f}",
    ]
    trace = [
        f"QUESTION -> {QUESTION}",
        f"VALUE -> {value_state} distance={value_distance_atr:.3f}ATR",
        f"STRUCTURE -> {structural_location}",
        f"LIQUIDITY -> {liquidity_location}",
        f"EXTENSION -> {extension_state} distance={extension_atr:.3f}ATR",
        f"SPACE -> LONG={long_space if long_space is not None else 'UNKNOWN'}ATR / SHORT={short_space if short_space is not None else 'UNKNOWN'}ATR",
        f"LONG_THESIS -> score={long_score:.3f} quality={_label(long_score)}",
        f"SHORT_THESIS -> score={short_score:.3f} quality={_label(short_score)}",
        f"ASYMMETRY -> preferred={preferred} gap={score_gap:.3f}",
        f"COUNTER_EVIDENCE -> LONG={long_counter or 'NONE'} SHORT={short_counter or 'NONE'}",
        f"FINAL_LOCATION -> {location_state}",
    ]

    return {
        "architecture": ARCHITECTURE,
        "version": VERSION,
        "question": QUESTION,
        "task": "ASSESS_PRICE_LOCATION_ONLY",
        "location_state": location_state,
        "location_quality": _label(preferred_score),
        "direction": "LONG" if preferred == "LONG" else "SHORT" if preferred == "SHORT" else "NEUTRAL",
        "value_state": value_state,
        "structural_location": structural_location,
        "liquidity_location": liquidity_location,
        "extension_state": extension_state,
        "available_space": {
            "long_atr": long_space,
            "short_atr": short_space,
            "long_quality": _space_label(long_space),
            "short_quality": _space_label(short_space),
            "next_resistance": next_resistance,
            "next_support": next_support,
        },
        "long_location_quality": _label(long_score),
        "short_location_quality": _label(short_score),
        "long_location_score": round(long_score, 4),
        "short_location_score": round(short_score, 4),
        "preferred_location": preferred,
        "confidence": confidence,
        "evidence": evidence,
        "observations": observations,
        "counter_evidence": aggregate_counter,
        "conflicts": conflicts,
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "reasoning_trace": trace,
        "professional_reasoning": {
            "question": QUESTION,
            "thesis": location_state,
            "evidence_hierarchy": "VALUE -> STRUCTURE -> LIQUIDITY -> EXTENSION -> SPACE -> ASYMMETRY -> COUNTER_EVIDENCE",
            "location_vs_space_separated": True,
            "long_thesis": {
                "quality": _label(long_score),
                "score": round(long_score, 4),
                "evidence": long_evidence,
                "counter_evidence": long_counter,
                "space_atr": long_space,
                "space_quality": _space_label(long_space),
                "components": long_components,
            },
            "short_thesis": {
                "quality": _label(short_score),
                "score": round(short_score, 4),
                "evidence": short_evidence,
                "counter_evidence": short_counter,
                "space_atr": short_space,
                "space_quality": _space_label(short_space),
                "components": short_components,
            },
            "context_compatibility": context_direction,
            "upstream_decisions_used": False,
            "upstream_gates_used": False,
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
