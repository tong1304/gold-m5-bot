from __future__ import annotations

"""E3 — Professional Market Structure Brain.

Independent structural analyst for CLOSED M5 OHLC. E3 produces auditable
structure evidence for E9 and never consumes upstream direction, decisions,
gates or scores and never authorizes a trade.
"""

from statistics import mean
from typing import Any

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_SINGLE_PROFESSIONAL_BRAIN_V2"


def _num(value: Any) -> float | None:
    try:
        value = float(value)
        return value if value == value and abs(value) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _clean_bars(bars: list[dict[str, Any]] | None) -> tuple[list[dict[str, float]], list[str]]:
    valid: list[dict[str, float]] = []
    reasons: list[str] = []
    for i, bar in enumerate(bars or []):
        if not isinstance(bar, dict):
            reasons.append(f"bar_{i}_not_mapping")
            continue
        values = {k: _num(bar.get(k)) for k in ("open", "high", "low", "close")}
        if any(v is None for v in values.values()):
            reasons.append(f"bar_{i}_ohlc_invalid")
            continue
        o, h, l, c = (float(values[k]) for k in ("open", "high", "low", "close"))
        if h < max(o, c) or l > min(o, c) or h < l:
            reasons.append(f"bar_{i}_ohlc_inconsistent")
            continue
        valid.append({"open": o, "high": h, "low": l, "close": c})
    return valid, reasons


def _atr(bars: list[dict[str, float]], period: int = 14) -> float:
    if not bars:
        return 0.0
    trs: list[float] = []
    previous: float | None = None
    for bar in bars[-max(period + 1, 2):]:
        h, l, c = bar["high"], bar["low"], bar["close"]
        trs.append(h - l if previous is None else max(h - l, abs(h - previous), abs(l - previous)))
        previous = c
    return mean(trs[-period:]) if trs else 0.0


def _pivots(bars: list[dict[str, float]], side: str, radius: int = 2) -> list[tuple[int, float]]:
    points: list[tuple[int, float]] = []
    if len(bars) < radius * 2 + 1:
        return points
    for i in range(radius, len(bars) - radius):
        value = bars[i][side]
        left = [bars[j][side] for j in range(i - radius, i)]
        right = [bars[j][side] for j in range(i + 1, i + radius + 1)]
        if side == "high" and value >= max(left) and value > max(right):
            points.append((i, value))
        elif side == "low" and value <= min(left) and value < min(right):
            points.append((i, value))
    return points


def _compress(points: list[tuple[int, float]], atr: float, spacing: int = 2, side: str | None = None) -> list[tuple[int, float]]:
    """Collapse clustered pivots while preserving the correct extreme.

    The previous implementation compared every point as if it were a high and
    contained a dead conditional. That could discard the most important low.
    """
    if not points:
        return []
    result: list[tuple[int, float]] = []
    tolerance = max(atr * 0.10, 1e-12)
    for point in points:
        if not result:
            result.append(point)
            continue
        prev = result[-1]
        if point[0] - prev[0] >= spacing:
            result.append(point)
            continue
        if abs(point[1] - prev[1]) <= tolerance:
            continue
        if side == "low":
            if point[1] < prev[1]:
                result[-1] = point
        elif side == "high":
            if point[1] > prev[1]:
                result[-1] = point
        else:
            # Preserve backward compatibility for callers without a side.
            result[-1] = point
    return result


def _label(points: list[tuple[int, float]], kind: str, atr: float) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    tolerance = max(atr * 0.10, 1e-12)
    for i, (idx, value) in enumerate(points):
        if i == 0:
            name = "SWING_HIGH" if kind == "HIGH" else "SWING_LOW"
        else:
            delta = value - points[i - 1][1]
            if abs(delta) <= tolerance:
                name = "EQH" if kind == "HIGH" else "EQL"
            elif kind == "HIGH":
                name = "HH" if delta > 0 else "LH"
            else:
                name = "HL" if delta > 0 else "LL"
        result.append({"index": idx, "price": round(value, 8), "label": name})
    return result


def _pair_direction(highs: list[dict[str, Any]], lows: list[dict[str, Any]]) -> str:
    hs = [x for x in highs if x["label"] in {"HH", "LH"}]
    ls = [x for x in lows if x["label"] in {"HL", "LL"}]
    if not hs or not ls:
        return "NEUTRAL"
    high_dir = hs[-1]["label"]
    low_dir = ls[-1]["label"]
    if high_dir == "HH" and low_dir == "HL":
        return "UP"
    if high_dir == "LH" and low_dir == "LL":
        return "DOWN"
    return "MIXED"


def _slope_direction(bars: list[dict[str, float]], lookback: int = 20) -> tuple[str, float]:
    closes = [b["close"] for b in bars[-lookback:]]
    if len(closes) < 5:
        return "NEUTRAL", 0.0
    delta = closes[-1] - closes[0]
    atr = max(_atr(bars), 1e-12)
    normalized = delta / (atr * max(len(closes) - 1, 1))
    quality = min(1.0, abs(normalized) * 8.0)
    if normalized > 0.035:
        return "UP", quality
    if normalized < -0.035:
        return "DOWN", quality
    return "NEUTRAL", quality


def _latest_break_candidate(highs: list[dict[str, Any]], lows: list[dict[str, Any]], latest_index: int) -> tuple[float, int, str] | None:
    candidates: list[tuple[int, float, str]] = []
    for item in highs:
        if item["index"] < latest_index:
            candidates.append((int(item["index"]), float(item["price"]), "UP"))
    for item in lows:
        if item["index"] < latest_index:
            candidates.append((int(item["index"]), float(item["price"]), "DOWN"))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    idx, level, direction = candidates[0]
    return level, idx, direction


def _bos(
    bars: list[dict[str, float]],
    highs: list[dict[str, Any]],
    lows: list[dict[str, Any]],
    atr: float,
    prior_structure: str,
) -> dict[str, Any]:
    if atr <= 0 or len(bars) < 2:
        return {"event": "NO_BOS", "direction": "NEUTRAL", "confirmed": False}
    latest = bars[-1]
    latest_index = len(bars) - 1
    # BOS is confirmed by a CLOSED candle close beyond the most recent eligible
    # swing. We do not search older swings after rejecting the newest one.
    candidate = _latest_break_candidate(highs, lows, latest_index)
    if candidate is None:
        return {"event": "NO_BOS", "direction": "NEUTRAL", "confirmed": False}
    level, swing_index, direction = candidate
    distance = latest["close"] - level if direction == "UP" else level - latest["close"]
    body = abs(latest["close"] - latest["open"])
    close_quality = body / atr
    if distance < atr * 0.10:
        return {"event": "NO_BOS", "direction": "NEUTRAL", "confirmed": False, "candidate_level": round(level, 8)}
    event = "CONFIRMED_CHOCH" if prior_structure in {"UP", "DOWN"} and direction != prior_structure else "CONFIRMED_BOS"
    return {
        "event": event,
        "direction": direction,
        "confirmed": True,
        "level": round(level, 8),
        "swing_index": swing_index,
        "break_candle_index": latest_index,
        "break_distance_atr": round(distance / atr, 4),
        "break_body_atr": round(close_quality, 4),
        "close_beyond_level": True,
    }


def _failure(bars: list[dict[str, float]], bos: dict[str, Any], atr: float) -> dict[str, Any]:
    if not bos.get("confirmed") or atr <= 0:
        return {"event": "NO_FAILURE", "direction": "NEUTRAL", "confirmed": False}
    level = float(bos["level"])
    direction = bos["direction"]
    close = bars[-1]["close"]
    reclaimed = close < level - atr * 0.05 if direction == "UP" else close > level + atr * 0.05
    if reclaimed:
        return {
            "event": "FAILED_BOS",
            "direction": "DOWN" if direction == "UP" else "UP",
            "confirmed": True,
            "level": level,
            "failure_candle_index": len(bars) - 1,
        }
    return {"event": "NO_FAILURE", "direction": "NEUTRAL", "confirmed": False}


def _strength(pair: str, bos: dict[str, Any], failure: dict[str, Any], swing_count: int, slope_quality: float) -> float:
    score = 0.20 + min(0.25, swing_count * 0.035)
    if pair in {"UP", "DOWN"}:
        score += 0.15
    if bos.get("confirmed"):
        score += min(0.30, 0.15 + float(bos.get("break_distance_atr", 0.0)) * 0.05)
    if failure.get("confirmed"):
        score += 0.05
    score += min(0.15, slope_quality * 0.15)
    return round(min(1.0, score), 4)


def analyze_e3(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Return an independent, auditable E3 structural thesis from CLOSED M5 OHLC."""
    clean, data_reasons = _clean_bars(bars)
    base = {
        "architecture": ARCHITECTURE,
        "reasoning_role": "MARKET_STRUCTURE_ANALYST",
        "question": QUESTION,
        "decision": None,
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
        "gate": None,
        "sub_engines_active": False,
        "sub_engines_status": "PAUSED",
        "specialists_active": False,
        "specialists_status": "PAUSED",
        "upstream_direction_used": False,
        "upstream_decisions_used": False,
        "upstream_gates_used": False,
        "score_used": False,
    }
    if len(clean) < 20:
        return {
            **base,
            "analysis_status": "INSUFFICIENT_DATA",
            "finding": "STRUCTURE_INSUFFICIENT_DATA",
            "structure_state": "INSUFFICIENT_DATA",
            "direction": "NEUTRAL",
            "swing_map": {"highs": [], "lows": []},
            "internal_structure": {},
            "external_structure": {},
            "bos": {"event": "NO_BOS", "direction": "NEUTRAL", "confirmed": False},
            "failure": {"event": "NO_FAILURE", "direction": "NEUTRAL", "confirmed": False},
            "structure_strength": 0.0,
            "confidence": 0.0,
            "evidence": [f"closed_candles={len(clean)}"],
            "observations": [f"closed_candles={len(clean)}"],
            "reason_codes": ["E3_INSUFFICIENT_DATA", *data_reasons[:4]],
            "reasons": ["E3_INSUFFICIENT_DATA", *data_reasons[:4]],
        }

    atr = _atr(clean)
    highs = _compress(_pivots(clean, "high"), atr, side="high")
    lows = _compress(_pivots(clean, "low"), atr, side="low")
    high_labels = _label(highs, "HIGH", atr)
    low_labels = _label(lows, "LOW", atr)
    pair = _pair_direction(high_labels, low_labels)
    slope, slope_quality = _slope_direction(clean)

    # In a monotonic leg, use context anchors only as evidence; they are not
    # promoted to HH/HL and therefore cannot manufacture a BOS by themselves.
    if not high_labels and not low_labels:
        anchor_index = len(clean) - 1
        anchor = {"index": anchor_index, "price": round(clean[-1]["close"], 8), "label": "DIRECTIONAL_CONTEXT_ANCHOR"}
        if slope == "UP":
            high_labels = [anchor]
            low_labels = [{"index": max(0, len(clean) - 20), "price": round(clean[-20]["close"], 8), "label": "DIRECTIONAL_CONTEXT_ANCHOR"}]
        elif slope == "DOWN":
            high_labels = [{"index": max(0, len(clean) - 20), "price": round(clean[-20]["close"], 8), "label": "DIRECTIONAL_CONTEXT_ANCHOR"}]
            low_labels = [anchor]

    bos = _bos(clean, high_labels, low_labels, atr, pair)
    failure = _failure(clean, bos, atr)

    if failure["confirmed"]:
        direction, state, finding = failure["direction"], "STRUCTURE_FAILURE", "STRUCTURE_FAILURE"
    elif bos["confirmed"]:
        direction = bos["direction"]
        state = "BREAKOUT_CONFIRMED" if bos["event"] == "CONFIRMED_BOS" else "CHANGE_OF_CHARACTER"
        finding = "BULLISH_BOS" if direction == "UP" else "BEARISH_BOS"
        if bos["event"] == "CONFIRMED_CHOCH":
            finding = "BULLISH_CHOCH" if direction == "UP" else "BEARISH_CHOCH"
    elif pair in {"UP", "DOWN"}:
        direction, state = pair, "CONTINUATION"
        finding = "BULLISH_STRUCTURE" if direction == "UP" else "BEARISH_STRUCTURE"
    elif slope in {"UP", "DOWN"} and slope_quality >= 0.45:
        direction, state = slope, "DIRECTIONAL_STRUCTURE"
        finding = "BULLISH_STRUCTURE" if direction == "UP" else "BEARISH_STRUCTURE"
    elif high_labels or low_labels:
        direction, state, finding = "MIXED", "TRANSITION", "MIXED_STRUCTURE"
    else:
        direction, state, finding = "NEUTRAL", "RANGE_OR_INSUFFICIENT", "NO_CONFIRMED_STRUCTURE_EVENT"

    internal = {"highs": high_labels[-4:], "lows": low_labels[-4:]}
    external = {"highs": high_labels[-2:], "lows": low_labels[-2:]}
    swing_count = len(high_labels) + len(low_labels)
    strength = _strength(pair, bos, failure, swing_count, slope_quality)
    confidence = round(min(1.0, 0.35 + strength * 0.40 + slope_quality * 0.15), 4)

    reasons: list[str] = []
    if not bos["confirmed"]:
        reasons.append("NO_CONFIRMED_BOS")
    if failure["confirmed"]:
        reasons.append("STRUCTURE_FAILURE_DETECTED")
    if bos.get("event") == "CONFIRMED_CHOCH":
        reasons.append("CHANGE_OF_CHARACTER_DETECTED")
    if pair == "MIXED":
        reasons.append("STRUCTURE_CONFLICT")
    if slope in {"UP", "DOWN"} and pair not in {slope, "NEUTRAL"}:
        reasons.append("SWING_SLOPE_DISAGREEMENT")
    if not high_labels or not low_labels:
        reasons.append("LIMITED_SWING_SIDE")
    reasons.extend(data_reasons[:2])

    evidence = [
        f"closed_candles={len(clean)}",
        f"atr14={atr:.8f}",
        f"swing_structure={pair}",
        f"slope_context={slope}",
        f"slope_quality={slope_quality:.4f}",
        f"bos={bos['event']}",
        f"failure={failure['event']}",
        f"internal_swing_count={len(internal['highs']) + len(internal['lows'])}",
        f"external_swing_count={len(external['highs']) + len(external['lows'])}",
    ]
    if bos.get("confirmed"):
        evidence.extend([
            f"bos_level={bos['level']}",
            f"bos_break_distance_atr={bos['break_distance_atr']}",
            f"bos_break_body_atr={bos['break_body_atr']}",
        ])

    return {
        **base,
        "analysis_status": "COMPLETE",
        "finding": finding,
        "structure_state": state,
        "direction": direction,
        "internal_structure": internal,
        "external_structure": external,
        "swing_map": {"highs": high_labels, "lows": low_labels},
        "bos": bos,
        "failure": failure,
        "structure_strength": strength,
        "confidence": confidence,
        "evidence": evidence,
        "observations": evidence,
        "reason_codes": reasons,
        "reasons": reasons,
    }
