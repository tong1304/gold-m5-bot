from __future__ import annotations

"""E5 — Professional Location / Value Brain v6.0.

Single responsibility: determine whether current price location offers
favorable asymmetry for LONG, SHORT, BOTH conditionally, or neither.
E1–E4 are qualitative context only. E5 never creates orders, gates execution,
or overrides E9.
"""

from math import isfinite
from statistics import mean
from typing import Any

ARCHITECTURE = "E5_SINGLE_PROFESSIONAL_LOCATION_BRAIN_V6_0"
VERSION = "6.0"
QUESTION = "Is current location advantageous?"
MIN_BARS = 80
ATR_PERIOD = 14
VALUE_LOOKBACK = 20
STRUCTURE_LOOKBACK = 60
LIQUIDITY_LOOKBACK = 30
PIVOT_WING = 2


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
        b: dict[str, float] = {"open": o, "high": h, "low": l, "close": c}  # type: ignore[dict-item]
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
        trs.append(b["high"] - b["low"] if prev is None else max(
            b["high"] - b["low"], abs(b["high"] - prev), abs(b["low"] - prev)
        ))
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
        w = bars[i - wing:i + wing + 1]
        if bars[i]["high"] >= max(x["high"] for x in w):
            highs.append(bars[i]["high"])
        if bars[i]["low"] <= min(x["low"] for x in w):
            lows.append(bars[i]["low"])
    return highs[-16:], lows[-16:]


def _nearest_above(price: float, levels: list[float], tolerance: float) -> float | None:
    vals = [v for v in levels if v > price + tolerance]
    return min(vals) if vals else None


def _nearest_below(price: float, levels: list[float], tolerance: float) -> float | None:
    vals = [v for v in levels if v < price - tolerance]
    return max(vals) if vals else None


def _dist(price: float, level: float | None, atr: float) -> float | None:
    return None if level is None or atr <= 0 else abs(price - level) / atr


def _upstream(permitted: dict[str, Any] | None) -> tuple[dict[str, Any], list[str], list[str]]:
    ctx: dict[str, Any] = {}
    evidence: list[str] = []
    conflicts: list[str] = []
    for eid in ("E1", "E2", "E3", "E4"):
        package = (permitted or {}).get(eid)
        if not isinstance(package, dict):
            continue
        payload = package.get("evidence") or package.get("output") or {}
        if not isinstance(payload, dict):
            continue
        ctx[eid] = dict(payload)
        evidence.append(f"{eid}_QUALITATIVE_CONTEXT_READ")
        text = str(payload).upper()
        if any(t in text for t in ("CONFLICT", "MIXED", "UNRESOLVED", "PENDING")):
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
    high_sweep = last["high"] > rh and last["close"] < rh
    low_sweep = last["low"] < rl and last["close"] > rl
    e4 = str(ctx.get("E4", {})).upper()
    return (
        high_sweep or "SWEEP_HIGH" in e4 or "HIGH_SWEEP" in e4,
        low_sweep or "SWEEP_LOW" in e4 or "LOW_SWEEP" in e4,
    )


def _incomplete(reason: str, problems: list[str]) -> dict[str, Any]:
    ev = problems or ["NO_RELIABLE_EVIDENCE"]
    return {
        "architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION,
        "task": "ASSESS_PRICE_LOCATION_ONLY", "location_state": "UNRESOLVED",
        "location_quality": "UNRESOLVED", "direction": "NEUTRAL", "value_state": "UNKNOWN",
        "structural_location": "UNKNOWN", "liquidity_location": "UNKNOWN", "extension_state": "UNKNOWN",
        "available_space": "UNKNOWN", "long_location_quality": "UNKNOWN", "short_location_quality": "UNKNOWN",
        "preferred_location": "NONE", "confidence": 0.0, "evidence": ev, "observations": ev,
        "counter_evidence": [], "conflicts": problems, "reason_codes": ["E5_DATA_INCOMPLETE"],
        "reasoning_trace": [f"QUESTION -> {QUESTION}", f"DATA_QUALITY -> {reason}"],
        "professional_reasoning": {
            "question": QUESTION, "thesis": reason,
            "evidence_hierarchy": "VALUE -> STRUCTURE -> LIQUIDITY -> EXTENSION -> SPACE -> ASYMMETRY -> COUNTER_EVIDENCE",
            "upstream_decisions_used": False, "upstream_gates_used": False, "decision_authority": "E9_ONLY",
        },
        "trade_decision_authority": False, "decision_authority": "E9_ONLY", "gate": None,
        "specialist_gate": "NONE", "specialists": {}, "specialists_active": False, "specialists_status": "NOT_USED",
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
    value_state = "DISCOUNT" if value_position <= 0.35 else "PREMIUM" if value_position >= 0.65 else "EQUILIBRIUM"

    struct_low, struct_high = _range(bars, STRUCTURE_LOOKBACK)
    ph, pl = _pivots(bars)
    tolerance = 0.15 * atr
    next_high = _nearest_above(price, ph + [struct_high], tolerance)
    next_low = _nearest_below(price, pl + [struct_low], tolerance)
    up_space = _dist(price, next_high, atr)
    down_space = _dist(price, next_low, atr)
    near_high = (_dist(price, struct_high, atr) or 999.0) <= 0.75
    near_low = (_dist(price, struct_low, atr) or 999.0) <= 0.75

    ctx, upstream_evidence, conflicts = _upstream(permitted)
    context_direction = _context_direction(ctx)
    sweep_high, sweep_low = _sweeps(bars, ctx)

    extension_atr = abs(value_distance_atr)
    extension_state = (
        "NORMAL" if extension_atr < 0.75 else
        "STRETCHED" if extension_atr < 1.5 else
        "EXTENDED" if extension_atr < 2.5 else "EXCESSIVE"
    )

    def side(name: str) -> tuple[float, list[str], dict[str, float]]:
        is_long = name == "LONG"
        favorable_value = value_position <= 0.35 if is_long else value_position >= 0.65
        adverse_value = value_position >= 0.65 if is_long else value_position <= 0.35
        opposing_structure = near_high if is_long else near_low
        supportive_sweep = sweep_low if is_long else sweep_high
        space = up_space if is_long else down_space
        value_component = 1.0 if favorable_value else 0.55 if not adverse_value else 0.10
        structure_component = 0.20 if opposing_structure else 0.85
        liquidity_component = 1.0 if supportive_sweep else 0.55
        extension_component = {"NORMAL": 1.0, "STRETCHED": 0.70, "EXTENDED": 0.40, "EXCESSIVE": 0.15}[extension_state]
        space_component = 1.0 if space is None or space >= 2.0 else 0.65 if space >= 1.0 else 0.10
        context_component = 0.65 if ((context_direction == "UP" and not is_long) or (context_direction == "DOWN" and is_long)) else 1.0
        score = round(
            0.25 * value_component + 0.15 * structure_component + 0.20 * liquidity_component +
            0.20 * extension_component + 0.15 * space_component + 0.05 * context_component, 4
        )
        reasons: list[str] = []
        if favorable_value: reasons.append("VALUE_FAVORABLE")
        if adverse_value: reasons.append("VALUE_ADVERSE")
        if opposing_structure: reasons.append("OPPOSING_STRUCTURE_NEARBY")
        if supportive_sweep: reasons.append("LIQUIDITY_SWEEP_SUPPORTIVE")
        if extension_state in {"EXTENDED", "EXCESSIVE"}: reasons.append("EXTENSION_RISK")
        if space is not None and space < 1.0: reasons.append("SPACE_CONSTRAINED")
        if context_direction == "UP" and not is_long: reasons.append("COUNTER_CONTEXT_SHORT")
        if context_direction == "DOWN" and is_long: reasons.append("COUNTER_CONTEXT_LONG")
        return score, reasons, {
            "value": value_component, "structure": structure_component, "liquidity": liquidity_component,
            "extension": extension_component, "space": space_component, "context": context_component,
        }

    long_q, long_reasons, long_components = side("LONG")
    short_q, short_reasons, short_components = side("SHORT")

    if context_direction == "UP":
        preferred = "LONG" if long_q >= 0.45 else "NONE"
        aligned_q, aligned_space = long_q, up_space
    elif context_direction == "DOWN":
        preferred = "SHORT" if short_q >= 0.45 else "NONE"
        aligned_q, aligned_space = short_q, down_space
    elif abs(long_q - short_q) >= 0.08 and max(long_q, short_q) >= 0.45:
        preferred = "LONG" if long_q > short_q else "SHORT"
        aligned_q = max(long_q, short_q)
        aligned_space = up_space if long_q > short_q else down_space
    elif max(long_q, short_q) >= 0.45:
        preferred = "BOTH_CONDITIONAL"
        aligned_q = max(long_q, short_q)
        aligned_space = max([x for x in (up_space, down_space) if x is not None], default=None)
    else:
        preferred = "NONE"
        aligned_q, aligned_space = max(long_q, short_q), None

    if context_direction in {"UP", "DOWN"} and extension_state in {"EXTENDED", "EXCESSIVE"} and aligned_q < 0.72:
        state = "WAIT_REPRICING"
    elif aligned_space is not None and aligned_space < 1.0 and aligned_q < 0.72:
        state = "SPACE_CONSTRAINED"
    elif preferred == "LONG" and long_q >= 0.72:
        state = "ADVANTAGEOUS_LONG"
    elif preferred == "SHORT" and short_q >= 0.72:
        state = "ADVANTAGEOUS_SHORT"
    elif preferred in {"LONG", "SHORT"}:
        state = f"ACCEPTABLE_{preferred}"
    elif preferred == "BOTH_CONDITIONAL":
        state = "BOTH_CONDITIONAL"
    else:
        state = "UNFAVORABLE"

    def label(q: float) -> str:
        return "HIGH" if q >= 0.72 else "ACCEPTABLE" if q >= 0.58 else "CONDITIONAL" if q >= 0.45 else "UNFAVORABLE"

    structural_location = (
        "COMPRESSED_STRUCTURE" if near_high and near_low else
        "AT_RESISTANCE" if near_high else
        "AT_SUPPORT" if near_low else "INSIDE_STRUCTURE"
    )
    liquidity_location = (
        "BOTH_SWEEPS" if sweep_high and sweep_low else
        "HIGH_SWEEP" if sweep_high else "LOW_SWEEP" if sweep_low else "NO_FRESH_SWEEP"
    )
    location_quality = label(aligned_q)
    direction = "LONG" if preferred == "LONG" else "SHORT" if preferred == "SHORT" else "NEUTRAL"

    # Confidence is certainty of the location assessment, not probability of profit.
    confidence = 0.55 + min(0.45, abs(long_q - short_q) * 1.8)
    if value_state == "EQUILIBRIUM":
        confidence *= 0.90
    if conflicts:
        confidence *= max(0.55, 1.0 - 0.10 * len(conflicts))
    confidence = round(max(0.0, min(1.0, confidence)), 4)

    evidence = [
        f"PRICE={price:.5f}", f"ATR={atr:.5f}", f"VALUE={value:.5f}", f"VALUE_METHOD={value_method}",
        f"VALUE_STATE={value_state}", f"VALUE_DISTANCE_ATR={value_distance_atr:.3f}",
        f"STRUCTURE_HIGH={struct_high:.5f}", f"STRUCTURE_LOW={struct_low:.5f}",
        f"UP_SPACE_ATR={up_space if up_space is not None else 'UNKNOWN'}",
        f"DOWN_SPACE_ATR={down_space if down_space is not None else 'UNKNOWN'}",
        f"EXTENSION_ATR={extension_atr:.3f}", f"CONTEXT_DIRECTION={context_direction}", *upstream_evidence,
    ]
    observations = [
        f"LONG_LOCATION={long_q:.3f}/{label(long_q)}", f"SHORT_LOCATION={short_q:.3f}/{label(short_q)}",
        f"STRUCTURAL_LOCATION={structural_location}", f"LIQUIDITY_LOCATION={liquidity_location}",
        f"EXTENSION_STATE={extension_state}",
        f"AVAILABLE_SPACE_LONG={up_space if up_space is not None else 'UNKNOWN'}",
        f"AVAILABLE_SPACE_SHORT={down_space if down_space is not None else 'UNKNOWN'}",
    ]
    counter_evidence = list(dict.fromkeys(long_reasons + short_reasons + conflicts))
    reason_codes = [f"LOCATION_STATE_{state}", f"VALUE_{value_state}", f"EXTENSION_{extension_state}"]
    if sweep_low: reason_codes.append("LOW_LIQUIDITY_SWEEP")
    if sweep_high: reason_codes.append("HIGH_LIQUIDITY_SWEEP")
    if up_space is not None and up_space < 1.0: reason_codes.append("LONG_SPACE_CONSTRAINED")
    if down_space is not None and down_space < 1.0: reason_codes.append("SHORT_SPACE_CONSTRAINED")
    if conflicts: reason_codes.append("UPSTREAM_CONTEXT_CONFLICT")

    trace = [
        f"QUESTION -> {QUESTION}", f"VALUE -> {value_state} distance={value_distance_atr:.3f}ATR",
        f"STRUCTURE -> {structural_location}", f"LIQUIDITY -> {liquidity_location}",
        f"EXTENSION -> {extension_state} distance={extension_atr:.3f}ATR",
        f"SPACE -> LONG={up_space if up_space is not None else 'UNKNOWN'}ATR / SHORT={down_space if down_space is not None else 'UNKNOWN'}ATR",
        f"ASYMMETRY -> LONG={long_q:.3f} SHORT={short_q:.3f}",
        f"COUNTER_EVIDENCE -> {counter_evidence or 'NONE'}", f"CONCLUSION -> {state}",
    ]

    return {
        "architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION,
        "task": "ASSESS_PRICE_LOCATION_ONLY", "location_state": state,
        "location_quality": location_quality, "direction": direction, "value_state": value_state,
        "structural_location": structural_location, "liquidity_location": liquidity_location,
        "extension_state": extension_state,
        "available_space": {"long_atr": up_space, "short_atr": down_space, "next_resistance": next_high, "next_support": next_low},
        "long_location_quality": label(long_q), "short_location_quality": label(short_q),
        "long_location_score": round(long_q, 4), "short_location_score": round(short_q, 4),
        "preferred_location": preferred, "confidence": confidence,
        "evidence": evidence, "observations": observations, "counter_evidence": counter_evidence,
        "conflicts": conflicts, "reason_codes": list(dict.fromkeys(reason_codes)), "reasoning_trace": trace,
        "professional_reasoning": {
            "question": QUESTION, "thesis": state,
            "evidence_hierarchy": "VALUE -> STRUCTURE -> LIQUIDITY -> EXTENSION -> SPACE -> ASYMMETRY -> COUNTER_EVIDENCE",
            "long_thesis": {"quality": label(long_q), "score": round(long_q, 4), "reasons": long_reasons, "counter_evidence": long_counter if False else [], "components": long_components},
            "short_thesis": {"quality": label(short_q), "score": round(short_q, 4), "reasons": short_reasons, "counter_evidence": [], "components": short_components},
            "upstream_decisions_used": False, "upstream_gates_used": False, "decision_authority": "E9_ONLY",
        },
        "trade_decision_authority": False, "decision_authority": "E9_ONLY", "gate": None,
        "specialist_gate": "NONE", "specialists": {}, "specialists_active": False, "specialists_status": "NOT_USED",
    }
