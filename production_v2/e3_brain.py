from __future__ import annotations

"""E3 single professional market-structure brain.

E3 is deliberately one brain. Former 3A-3F modules remain parked and are not
called by runtime. E3 independently interprets CLOSED M5 OHLC data and emits
structural evidence only. It never consumes E1/E2 direction, never issues a
trade decision, and never owns a gate.
"""

from typing import Any


def _atr(bars: list[dict[str, float]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        h = float(bars[i]["high"])
        l = float(bars[i]["low"])
        pc = float(bars[i - 1]["close"])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    window = trs[-period:]
    return sum(window) / len(window) if window else 0.0


def _pivots(bars: list[dict[str, float]], side: str, radius: int = 2) -> list[tuple[int, float]]:
    """Return confirmed pivots only; the last `radius` candles cannot form a pivot."""
    out: list[tuple[int, float]] = []
    for i in range(radius, len(bars) - radius):
        value = float(bars[i][side])
        left = [float(bars[j][side]) for j in range(i - radius, i)]
        right = [float(bars[j][side]) for j in range(i + 1, i + radius + 1)]
        if side == "high":
            valid = value > max(left) and value >= max(right)
        else:
            valid = value < min(left) and value <= min(right)
        if valid:
            out.append((i, value))
    return out


def _compress(points: list[tuple[int, float]], atr: float, min_spacing: int = 2) -> list[tuple[int, float]]:
    """Remove clustered same-side pivots without mixing highs and lows."""
    if not points:
        return []
    result: list[tuple[int, float]] = []
    min_move = max(atr * 0.10, 1e-12)
    for point in points:
        if not result:
            result.append(point)
            continue
        prev = result[-1]
        if point[0] - prev[0] >= min_spacing:
            result.append(point)
            continue
        # For same-side clustered pivots keep the more extreme point.
        if abs(point[1] - prev[1]) >= min_move:
            result[-1] = point
    return result


def _labels(points: list[tuple[int, float]], kind: str, atr: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    threshold = max(atr * 0.10, 1e-12)
    for i, (idx, value) in enumerate(points):
        label = "UNCLASSIFIED"
        if i:
            delta = value - points[i - 1][1]
            if abs(delta) <= threshold:
                label = "EQH" if kind == "HIGH" else "EQL"
            elif kind == "HIGH":
                label = "HH" if delta > 0 else "LH"
            else:
                label = "HL" if delta > 0 else "LL"
        out.append({"index": idx, "price": value, "label": label})
    return out


def _latest_pair_direction(highs: list[dict[str, Any]], lows: list[dict[str, Any]]) -> str:
    """Classify structure from the latest comparable high/low pairs."""
    high_labels = [x["label"] for x in highs if x["label"] in {"HH", "LH"}]
    low_labels = [x["label"] for x in lows if x["label"] in {"HL", "LL"}]
    if not high_labels or not low_labels:
        return "NEUTRAL"
    high = high_labels[-1]
    low = low_labels[-1]
    if high == "HH" and low == "HL":
        return "UP"
    if high == "LH" and low == "LL":
        return "DOWN"
    return "MIXED"


def _structure_state(highs: list[dict[str, Any]], lows: list[dict[str, Any]]) -> tuple[str, str, float]:
    direction = _latest_pair_direction(highs, lows)
    if direction == "UP":
        return "BULLISH", "CONTINUATION", 0.78
    if direction == "DOWN":
        return "BEARISH", "CONTINUATION", 0.78
    labels = [x["label"] for x in highs[-4:] + lows[-4:]]
    bull = sum(x in {"HH", "HL"} for x in labels)
    bear = sum(x in {"LH", "LL"} for x in labels)
    if bull and bear:
        return "MIXED", "TRANSITION", 0.52
    return "NEUTRAL", "RANGE_OR_INSUFFICIENT", 0.40


def _latest_bos(
    bars: list[dict[str, float]],
    highs: list[dict[str, Any]],
    lows: list[dict[str, Any]],
    atr: float,
) -> dict[str, Any]:
    """Detect only the most recent structural close-break of a confirmed swing."""
    if atr <= 0:
        return {"event": "NO_BOS", "direction": "NEUTRAL", "confirmed": False}

    candidates: list[tuple[int, float, str, str]] = []
    # Only meaningful structural swings can be broken.
    for item in highs:
        if item["label"] in {"HH", "LH", "EQH", "UNCLASSIFIED"}:
            candidates.append((int(item["index"]), float(item["price"]), "UP", "HIGH"))
    for item in lows:
        if item["label"] in {"HL", "LL", "EQL", "UNCLASSIFIED"}:
            candidates.append((int(item["index"]), float(item["price"]), "DOWN", "LOW"))
    candidates.sort(key=lambda x: x[0], reverse=True)

    # Examine the newest swing first. The first confirmed break is the active event.
    for swing_index, level, direction, swing_type in candidates:
        for j in range(swing_index + 1, len(bars)):
            close = float(bars[j]["close"])
            distance = (close - level) if direction == "UP" else (level - close)
            if distance >= atr * 0.05:
                return {
                    "event": "CONFIRMED_BOS",
                    "direction": direction,
                    "confirmed": True,
                    "level": level,
                    "swing_index": swing_index,
                    "swing_type": swing_type,
                    "break_candle_index": j,
                    "break_distance_atr": round(distance / atr, 4),
                }
    return {"event": "NO_BOS", "direction": "NEUTRAL", "confirmed": False}


def _failure(bars: list[dict[str, float]], bos: dict[str, Any]) -> dict[str, Any]:
    if not bos.get("confirmed"):
        return {"event": "NO_FAILURE", "direction": "NEUTRAL", "confirmed": False}
    level = float(bos["level"])
    start = int(bos["break_candle_index"])
    for j in range(start + 1, len(bars)):
        close = float(bars[j]["close"])
        if bos["direction"] == "UP" and close < level:
            return {
                "event": "FAILED_BOS",
                "direction": "DOWN",
                "confirmed": True,
                "level": level,
                "failure_candle_index": j,
            }
        if bos["direction"] == "DOWN" and close > level:
            return {
                "event": "FAILED_BOS",
                "direction": "UP",
                "confirmed": True,
                "level": level,
                "failure_candle_index": j,
            }
    return {"event": "NO_FAILURE", "direction": "NEUTRAL", "confirmed": False}


def _event_name(direction: str, bos: dict[str, Any], failure: dict[str, Any], state: str) -> str:
    if failure.get("confirmed"):
        return "STRUCTURE_FAILURE"
    if bos.get("confirmed"):
        return "BULLISH_BOS" if bos["direction"] == "UP" else "BEARISH_BOS"
    if direction == "UP":
        return "BULLISH_STRUCTURE"
    if direction == "DOWN":
        return "BEARISH_STRUCTURE"
    if state == "MIXED":
        return "MIXED_STRUCTURE"
    return "NO_CONFIRMED_STRUCTURE_EVENT"


def analyze_e3(bars: list[dict[str, float]]) -> dict[str, Any]:
    """Independent E3 structure analysis over the latest CLOSED M5 candles."""
    clean = list(bars[-200:])
    base = {
        "architecture": "E3_SINGLE_PROFESSIONAL_BRAIN_V1",
        "decision_authority": "E9_ONLY",
        "trade_decision_authority": False,
        "gate": None,
        "sub_engines_active": False,
        "sub_engines_status": "PAUSED",
        "upstream_direction_used": False,
        "upstream_decisions_used": False,
        "upstream_gates_used": False,
    }
    atr = _atr(clean)
    if len(clean) < 20 or atr <= 0:
        return {
            **base,
            "analysis_status": "INSUFFICIENT_DATA",
            "question": "What is price structure communicating?",
            "finding": "STRUCTURE_INSUFFICIENT_DATA",
            "structure_state": "INSUFFICIENT_DATA",
            "direction": "NEUTRAL",
            "internal_structure": {},
            "external_structure": {},
            "swing_map": {"highs": [], "lows": []},
            "bos": {"event": "NO_BOS", "direction": "NEUTRAL", "confirmed": False},
            "failure": {"event": "NO_FAILURE", "direction": "NEUTRAL", "confirmed": False},
            "structure_strength": 0.0,
            "confidence": 0.0,
            "evidence": [f"closed_candles={len(clean)}"],
            "observations": [f"closed_candles={len(clean)}", "insufficient_structure_sample=True"],
            "reason_codes": ["E3_INSUFFICIENT_DATA"],
            "reasons": ["E3_INSUFFICIENT_DATA"],
        }

    highs = _compress(_pivots(clean, "high"), atr)
    lows = _compress(_pivots(clean, "low"), atr)
    high_labels = _labels(highs, "HIGH", atr)
    low_labels = _labels(lows, "LOW", atr)
    structure_direction, structure_state, base_confidence = _structure_state(high_labels, low_labels)
    bos = _latest_bos(clean, high_labels, low_labels, atr)
    failure = _failure(clean, bos)

    direction = structure_direction
    state = structure_state
    if failure["confirmed"]:
        direction = failure["direction"]
        state = "STRUCTURE_FAILURE"
    elif bos["confirmed"]:
        direction = bos["direction"]
        state = "BREAKOUT_CONFIRMED"

    internal_highs = high_labels[-4:]
    internal_lows = low_labels[-4:]
    external_highs = high_labels[-2:]
    external_lows = low_labels[-2:]

    structural_events = sum(
        item["label"] in {"HH", "HL", "LH", "LL"}
        for item in internal_highs + internal_lows
    )
    strength = 0.35 + min(0.40, structural_events * 0.08)
    if bos["confirmed"]:
        strength += 0.20
    if failure["confirmed"]:
        strength -= 0.15
    strength = max(0.0, min(1.0, strength))
    confidence = max(0.0, min(1.0, 0.65 * base_confidence + 0.35 * strength))

    finding = _event_name(direction, bos, failure, state)
    evidence = [
        f"closed_candles={len(clean)}",
        f"atr14={atr:.6f}",
        f"structure_state={state}",
        f"structure_direction={direction}",
        f"external_structure={_latest_pair_direction(external_highs, external_lows)}",
        f"internal_structure={_latest_pair_direction(internal_highs, internal_lows)}",
        f"bos={bos['event']}",
        f"failure={failure['event']}",
        f"internal_swing_count={len(internal_highs) + len(internal_lows)}",
        f"external_swing_count={len(external_highs) + len(external_lows)}",
    ]
    if bos.get("confirmed"):
        evidence.extend([
            f"bos_level={bos['level']:.6f}",
            f"bos_break_candle={bos['break_candle_index']}",
            f"bos_break_distance_atr={bos['break_distance_atr']}",
        ])

    reasons: list[str] = []
    if not bos["confirmed"]:
        reasons.append("NO_CONFIRMED_BOS")
    if failure["confirmed"]:
        reasons.append("STRUCTURE_FAILURE_DETECTED")
    if direction == "MIXED":
        reasons.append("STRUCTURE_CONFLICT")
    if len(high_labels) < 2 or len(low_labels) < 2:
        reasons.append("LIMITED_SWING_HISTORY")

    observations = evidence[:]
    return {
        **base,
        "analysis_status": "COMPLETE",
        "question": "What is price structure communicating?",
        "finding": finding,
        "structure_state": state,
        "direction": direction,
        "internal_structure": {"highs": internal_highs, "lows": internal_lows},
        "external_structure": {"highs": external_highs, "lows": external_lows},
        "swing_map": {"highs": high_labels, "lows": low_labels},
        "bos": bos,
        "failure": failure,
        "structure_strength": round(strength, 4),
        "confidence": round(confidence, 4),
        "evidence": evidence,
        "observations": observations,
        "reason_codes": reasons,
        "reasons": reasons,
    }
