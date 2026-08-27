from __future__ import annotations

"""E3 — Professional Market Structure Brain.

E3 is a single independent analyst. It reads CLOSED M5 OHLC only and produces
structural evidence for E9. It never consumes E1/E2 direction, never emits a
trade decision, and never owns an execution gate.
"""

from typing import Any


def _atr(bars: list[dict[str, float]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs: list[float] = []
    for i in range(1, len(bars)):
        h, l = float(bars[i]["high"]), float(bars[i]["low"])
        pc = float(bars[i - 1]["close"])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    window = trs[-period:]
    return sum(window) / len(window) if window else 0.0


def _pivots(bars: list[dict[str, float]], side: str, radius: int = 2) -> list[tuple[int, float]]:
    """Confirmed pivots only; the newest radius candles remain unconfirmed."""
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
        elif abs(point[1] - prev[1]) >= min_move:
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


def _pair_direction(highs: list[dict[str, Any]], lows: list[dict[str, Any]]) -> str:
    hs = [x["label"] for x in highs if x["label"] in {"HH", "LH"}]
    ls = [x["label"] for x in lows if x["label"] in {"HL", "LL"}]
    if not hs or not ls:
        return "NEUTRAL"
    if hs[-1] == "HH" and ls[-1] == "HL":
        return "UP"
    if hs[-1] == "LH" and ls[-1] == "LL":
        return "DOWN"
    return "MIXED"


def _classify_structure(highs: list[dict[str, Any]], lows: list[dict[str, Any]]) -> tuple[str, str, float]:
    direction = _pair_direction(highs, lows)
    recent = [x["label"] for x in highs[-4:] + lows[-4:]]
    bull = sum(x in {"HH", "HL"} for x in recent)
    bear = sum(x in {"LH", "LL"} for x in recent)
    if direction == "UP":
        return "BULLISH", "CONTINUATION", 0.80
    if direction == "DOWN":
        return "BEARISH", "CONTINUATION", 0.80
    if bull and bear:
        return "MIXED", "TRANSITION", 0.55
    return "NEUTRAL", "RANGE_OR_INSUFFICIENT", 0.42


def _break_event(bars: list[dict[str, float]], highs: list[dict[str, Any]], lows: list[dict[str, Any]], atr: float) -> dict[str, Any]:
    """Find the newest meaningful close-break of the latest confirmed swing.

    A wick through a level is not a BOS. A close must clear the level by a
    small ATR-normalised buffer. This prevents stale/weak breaks from becoming
    structural events.
    """
    if atr <= 0:
        return {"event": "NO_BOS", "direction": "NEUTRAL", "confirmed": False}
    candidates: list[tuple[int, float, str, str]] = []
    for item in highs[-8:]:
        if item["label"] != "UNCLASSIFIED":
            candidates.append((int(item["index"]), float(item["price"]), "UP", "HIGH"))
    for item in lows[-8:]:
        if item["label"] != "UNCLASSIFIED":
            candidates.append((int(item["index"]), float(item["price"]), "DOWN", "LOW"))
    candidates.sort(key=lambda x: x[0], reverse=True)
    for swing_index, level, direction, swing_type in candidates:
        for j in range(swing_index + 1, len(bars)):
            close = float(bars[j]["close"])
            distance = close - level if direction == "UP" else level - close
            if distance >= atr * 0.05:
                return {
                    "event": "CONFIRMED_BOS",
                    "direction": direction,
                    "confirmed": True,
                    "level": level,
                    "swing_index": swing_index,
                    "break_candle_index": j,
                    "swing_type": swing_type,
                    "break_distance_atr": round(distance / atr, 4),
                }
    return {"event": "NO_BOS", "direction": "NEUTRAL", "confirmed": False}


def _acceptance(bars: list[dict[str, float]], bos: dict[str, Any], atr: float) -> dict[str, Any]:
    """Measure whether price accepted the broken level after the break."""
    if not bos.get("confirmed"):
        return {"event": "NO_ACCEPTANCE_TEST", "confirmed": False, "direction": "NEUTRAL"}
    level = float(bos["level"])
    start = int(bos["break_candle_index"])
    direction = bos["direction"]
    follow = bars[start + 1 : min(len(bars), start + 4)]
    if not follow:
        return {"event": "ACCEPTANCE_PENDING", "confirmed": False, "direction": direction}
    closes = [float(x["close"]) for x in follow]
    buffer = max(atr * 0.02, 1e-12)
    if direction == "UP":
        accepted = any(c >= level + buffer for c in closes)
        reclaimed = any(c < level - buffer for c in closes)
    else:
        accepted = any(c <= level - buffer for c in closes)
        reclaimed = any(c > level + buffer for c in closes)
    if reclaimed and not accepted:
        return {"event": "REJECTED_BREAK", "confirmed": True, "direction": "DOWN" if direction == "UP" else "UP", "level": level}
    if accepted:
        return {"event": "ACCEPTED_BREAK", "confirmed": True, "direction": direction, "level": level}
    return {"event": "ACCEPTANCE_PENDING", "confirmed": False, "direction": direction, "level": level}


def _failure(bars: list[dict[str, float]], bos: dict[str, Any], atr: float) -> dict[str, Any]:
    if not bos.get("confirmed"):
        return {"event": "NO_FAILURE", "direction": "NEUTRAL", "confirmed": False}
    level = float(bos["level"])
    start = int(bos["break_candle_index"])
    buffer = max(atr * 0.02, 1e-12)
    for j in range(start + 1, len(bars)):
        close = float(bars[j]["close"])
        if bos["direction"] == "UP" and close < level - buffer:
            return {"event": "FAILED_BOS", "direction": "DOWN", "confirmed": True, "level": level, "failure_candle_index": j}
        if bos["direction"] == "DOWN" and close > level + buffer:
            return {"event": "FAILED_BOS", "direction": "UP", "confirmed": True, "level": level, "failure_candle_index": j}
    return {"event": "NO_FAILURE", "direction": "NEUTRAL", "confirmed": False}


def _choch(structure_direction: str, bos: dict[str, Any], failure: dict[str, Any]) -> dict[str, Any]:
    """A structural shift is only called when the break opposes prior structure."""
    if failure.get("confirmed"):
        return {"event": "CHoCH", "direction": failure["direction"], "confirmed": True, "basis": "FAILED_BOS"}
    if bos.get("confirmed") and structure_direction in {"UP", "DOWN"} and bos["direction"] != structure_direction:
        return {"event": "CHoCH", "direction": bos["direction"], "confirmed": True, "basis": "OPPOSING_BOS"}
    return {"event": "NO_CHoCH", "direction": "NEUTRAL", "confirmed": False}


def _event_name(direction: str, state: str, bos: dict[str, Any], choch: dict[str, Any], failure: dict[str, Any], acceptance: dict[str, Any]) -> str:
    if failure.get("confirmed"):
        return "STRUCTURE_FAILURE"
    if choch.get("confirmed"):
        return "BULLISH_CHoCH" if choch["direction"] == "UP" else "BEARISH_CHoCH"
    if bos.get("confirmed"):
        if acceptance.get("event") == "ACCEPTED_BREAK":
            return "BULLISH_BOS_ACCEPTED" if bos["direction"] == "UP" else "BEARISH_BOS_ACCEPTED"
        return "BULLISH_BOS" if bos["direction"] == "UP" else "BEARISH_BOS"
    if direction == "UP":
        return "BULLISH_STRUCTURE"
    if direction == "DOWN":
        return "BEARISH_STRUCTURE"
    if state == "MIXED":
        return "MIXED_STRUCTURE"
    return "NO_CONFIRMED_STRUCTURE_EVENT"


def analyze_e3(bars: list[dict[str, float]]) -> dict[str, Any]:
    """Independent professional structure analysis over CLOSED M5 candles."""
    clean = list(bars[-200:])
    base = {
        "architecture": "E3_SINGLE_PROFESSIONAL_BRAIN_V2",
        "decision_authority": "E9_ONLY",
        "trade_decision_authority": False,
        "gate": None,
        "sub_engines_active": False,
        "sub_engines_status": "PAUSED",
        "upstream_direction_used": False,
        "upstream_decisions_used": False,
        "upstream_gates_used": False,
    }
    question = "What is price structure communicating?"
    atr = _atr(clean)
    if len(clean) < 30 or atr <= 0:
        return {**base, "analysis_status": "INSUFFICIENT_DATA", "question": question, "finding": "STRUCTURE_INSUFFICIENT_DATA", "structure_state": "INSUFFICIENT_DATA", "direction": "NEUTRAL", "internal_structure": {}, "external_structure": {}, "swing_map": {"highs": [], "lows": []}, "bos": {"event": "NO_BOS", "direction": "NEUTRAL", "confirmed": False}, "choch": {"event": "NO_CHoCH", "direction": "NEUTRAL", "confirmed": False}, "acceptance": {"event": "NO_ACCEPTANCE_TEST", "confirmed": False, "direction": "NEUTRAL"}, "failure": {"event": "NO_FAILURE", "direction": "NEUTRAL", "confirmed": False}, "structure_strength": 0.0, "confidence": 0.0, "evidence": [f"closed_candles={len(clean)}"], "observations": [f"closed_candles={len(clean)}", "insufficient_structure_sample=True"], "reason_codes": ["E3_INSUFFICIENT_DATA"], "reasons": ["E3_INSUFFICIENT_DATA"]}

    highs = _labels(_compress(_pivots(clean, "high"), atr), "HIGH", atr)
    lows = _labels(_compress(_pivots(clean, "low"), atr), "LOW", atr)
    structure_direction, structure_state, base_confidence = _classify_structure(highs, lows)
    bos = _break_event(clean, highs, lows, atr)
    acceptance = _acceptance(clean, bos, atr)
    failure = _failure(clean, bos, atr)
    choch = _choch(structure_direction, bos, failure)

    direction = structure_direction
    state = structure_state
    if failure["confirmed"]:
        direction, state = failure["direction"], "STRUCTURE_FAILURE"
    elif choch["confirmed"]:
        direction, state = choch["direction"], "STRUCTURAL_SHIFT"
    elif bos["confirmed"]:
        direction, state = bos["direction"], "BREAKOUT_CONFIRMED"

    internal_highs, internal_lows = highs[-4:], lows[-4:]
    external_highs, external_lows = highs[-2:], lows[-2:]
    structural_events = sum(x["label"] in {"HH", "HL", "LH", "LL"} for x in internal_highs + internal_lows)
    strength = 0.30 + min(0.42, structural_events * 0.07)
    if bos["confirmed"]:
        strength += 0.16
    if acceptance["event"] == "ACCEPTED_BREAK":
        strength += 0.08
    if failure["confirmed"]:
        strength -= 0.14
    if choch["confirmed"]:
        strength += 0.04
    if structure_direction == "MIXED":
        strength -= 0.06
    strength = max(0.0, min(1.0, strength))
    confidence = max(0.0, min(1.0, 0.60 * base_confidence + 0.40 * strength))

    finding = _event_name(direction, state, bos, choch, failure, acceptance)
    evidence = [
        f"closed_candles={len(clean)}", f"atr14={atr:.6f}", f"structure_state={state}",
        f"structure_direction={direction}", f"external_structure={_pair_direction(external_highs, external_lows)}",
        f"internal_structure={_pair_direction(internal_highs, internal_lows)}", f"bos={bos['event']}",
        f"choch={choch['event']}", f"acceptance={acceptance['event']}", f"failure={failure['event']}",
        f"internal_swing_count={len(internal_highs)+len(internal_lows)}", f"external_swing_count={len(external_highs)+len(external_lows)}",
    ]
    if bos.get("confirmed"):
        evidence += [f"bos_level={bos['level']:.6f}", f"bos_break_candle={bos['break_candle_index']}", f"bos_break_distance_atr={bos['break_distance_atr']}"]

    reasons: list[str] = []
    if not bos["confirmed"]:
        reasons.append("NO_CONFIRMED_BOS")
    if acceptance["event"] == "ACCEPTANCE_PENDING":
        reasons.append("BREAK_ACCEPTANCE_PENDING")
    if acceptance["event"] == "REJECTED_BREAK":
        reasons.append("BREAK_REJECTED")
    if failure["confirmed"]:
        reasons.append("STRUCTURE_FAILURE_DETECTED")
    if choch["confirmed"]:
        reasons.append("STRUCTURAL_SHIFT_DETECTED")
    if direction == "MIXED":
        reasons.append("STRUCTURE_CONFLICT")
    if len(highs) < 3 or len(lows) < 3:
        reasons.append("LIMITED_SWING_HISTORY")

    return {
        **base, "analysis_status": "COMPLETE", "question": question, "finding": finding,
        "structure_state": state, "direction": direction,
        "internal_structure": {"highs": internal_highs, "lows": internal_lows},
        "external_structure": {"highs": external_highs, "lows": external_lows},
        "swing_map": {"highs": highs, "lows": lows}, "bos": bos, "choch": choch,
        "acceptance": acceptance, "failure": failure,
        "structure_strength": round(strength, 4), "confidence": round(confidence, 4),
        "evidence": evidence, "observations": evidence, "reason_codes": reasons, "reasons": reasons,
    }
