from __future__ import annotations

from math import sqrt
from statistics import mean, median
from typing import Any

from .contracts import EngineResult

NAME = "Trade Economics & Risk Brain"
QUESTION = "Is the proposed trade economically attractive, structurally survivable, and robust to execution uncertainty?"
ARCHITECTURE = "E8_PROFESSIONAL_TRADE_ECONOMICS_RISK_BRAIN_V26"
VERSION = "26.0"

# E8 is an economics/risk gate only. It never creates a setup or changes direction.
MIN_BARS = 30
ATR_PERIOD = 14
MIN_RR = 1.50
MIN_STOP_ATR = 0.50
MAX_STOP_ATR = 3.50
RISK_ATR_BUFFER = 0.20
FALLBACK_STOP_ATR = 1.20
STRUCTURE_LOOKBACK = 20
MAE_LOOKBACK = 100
MAE_HORIZON_BARS = 12
MIN_MAE_SAMPLES = 30
MIN_SPACE_ATR = 0.75
MIN_TARGET_CLEARANCE_ATR = 0.10
MAX_TARGET_EXTENSION_ATR = 3.50
TARGET_QUALITY_MIN = 70.0
MIN_SURVIVAL_MARGIN_ATR = 0.15
MAX_EXECUTION_COST_ATR = 0.15
MIN_ECONOMIC_EDGE = 0.10
MIN_PROBABILITY = 0.50
MIN_PROBABILITY_QUALITY = 70.0
MIN_PROBABILITY_SAMPLE = 30
PROBABILITY_STRESS = 0.03
WILSON_Z = 1.645
MIN_WILSON_LOWER = 0.50
SENSITIVITY_ENTRY_ATR = 0.20
SENSITIVITY_STOP_ATR = 0.20
SENSITIVITY_TARGET_ATR = 0.20
SPACE_CONFLICT_ATR = 0.75
ROBUSTNESS_MIN_MARGIN = 0.05
MIN_TARGET_REALISM = 0.60
MIN_STOP_QUALITY = 70.0
RISK_CLASS_A = 0.78
RISK_CLASS_B = 0.68
RISK_CLASS_C = 0.58


_VETO_PRIORITY = {
    "ENTRY_CONFIRMATION": 10,
    "NO_USABLE_STRUCTURAL_TARGET": 20,
    "INVALID_TRADE_GEOMETRY": 30,
    "STOP_TOO_TIGHT": 40,
    "STOP_TOO_WIDE": 40,
    "REAL_RR_BELOW_MINIMUM": 50,
    "EFFECTIVE_SPACE_UNRELIABLE": 60,
    "EFFECTIVE_SPACE_BELOW_MINIMUM": 60,
    "SPACE_CONFLICT": 60,
    "STRUCTURAL_SURVIVAL_NOT_PROVEN": 70,
    "EXECUTION_COST_TOO_HIGH": 80,
    "TARGET_REALISM_TOO_LOW": 90,
    "STOP_QUALITY_TOO_LOW": 90,
    "STRESSED_PROBABILITY_BELOW_MINIMUM": 100,
    "PROBABILITY_EDGE_NOT_POSITIVE": 100,
    "ECONOMIC_MARGIN_TOO_THIN": 100,
    "PROBABILITY_EDGE_NOT_TRUSTWORTHY": 110,
    "HISTORICAL_SAMPLE_INSUFFICIENT": 105,
    "SURVIVAL_FRAGILE": 120,
    "ECONOMICS_SENSITIVITY_FRAGILE": 130,
}

_VETO_LAYER = {
    "ENTRY_CONFIRMATION": "CONFIRMATION",
    "NO_USABLE_STRUCTURAL_TARGET": "TARGET",
    "INVALID_TRADE_GEOMETRY": "GEOMETRY",
    "STOP_TOO_TIGHT": "STOP",
    "STOP_TOO_WIDE": "STOP",
    "REAL_RR_BELOW_MINIMUM": "RR",
    "EFFECTIVE_SPACE_UNRELIABLE": "SPACE",
    "EFFECTIVE_SPACE_BELOW_MINIMUM": "SPACE",
    "SPACE_CONFLICT": "SPACE",
    "STRUCTURAL_SURVIVAL_NOT_PROVEN": "SURVIVAL",
    "EXECUTION_COST_TOO_HIGH": "EXECUTION",
    "TARGET_REALISM_TOO_LOW": "TARGET_REALISM",
    "STOP_QUALITY_TOO_LOW": "STOP_QUALITY",
    "STRESSED_PROBABILITY_BELOW_MINIMUM": "PROBABILITY",
    "PROBABILITY_EDGE_NOT_POSITIVE": "PROBABILITY",
    "ECONOMIC_MARGIN_TOO_THIN": "PROBABILITY",
    "PROBABILITY_EDGE_NOT_TRUSTWORTHY": "PROBABILITY",
    "HISTORICAL_SAMPLE_INSUFFICIENT": "PROBABILITY",
    "SURVIVAL_FRAGILE": "SURVIVAL",
    "ECONOMICS_SENSITIVITY_FRAGILE": "ROBUSTNESS",
}

_NEXT_EVENT = {
    "ENTRY_CONFIRMATION": "E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION",
    "NO_USABLE_STRUCTURAL_TARGET": "NEW_CREDIBLE_OPPOSING_STRUCTURAL_BARRIER",
    "INVALID_TRADE_GEOMETRY": "VALID_ENTRY_STOP_TARGET_GEOMETRY",
    "STOP_TOO_TIGHT": "STRUCTURAL_STOP_WITH_VALID_ATR_WIDTH",
    "STOP_TOO_WIDE": "TIGHTER_STRUCTURAL_STOP_OR_NEW_ENTRY",
    "REAL_RR_BELOW_MINIMUM": "ENTRY_OR_TARGET_REPRICING_TO_RR_THRESHOLD",
    "EFFECTIVE_SPACE_UNRELIABLE": "CONSISTENT_STRUCTURAL_SPACE_EVIDENCE",
    "EFFECTIVE_SPACE_BELOW_MINIMUM": "INCREASED_CLEAR_SPACE_BEYOND_MINIMUM",
    "SPACE_CONFLICT": "RESOLVED_SPACE_MEASUREMENT_CONSISTENCY",
    "STRUCTURAL_SURVIVAL_NOT_PROVEN": "HISTORICAL_MAE_SUPPORTING_STOP_SURVIVAL",
    "EXECUTION_COST_TOO_HIGH": "LOWER_SPREAD_SLIPPAGE_OR_HIGHER_ATR",
    "TARGET_REALISM_TOO_LOW": "CREDIBLE_TARGET_WITH_REALISTIC_PATH",
    "STOP_QUALITY_TOO_LOW": "HIGHER_QUALITY_STRUCTURAL_STOP",
    "STRESSED_PROBABILITY_BELOW_MINIMUM": "HIGHER_TRUSTED_STRESSED_PROBABILITY",
    "PROBABILITY_EDGE_NOT_POSITIVE": "POSITIVE_STRESSED_EXPECTANCY",
    "ECONOMIC_MARGIN_TOO_THIN": "WIDER_PROBABILITY_EDGE_OVER_BREAKEVEN",
    "PROBABILITY_EDGE_NOT_TRUSTWORTHY": "TRUSTED_SETUP_DIRECTION_PROBABILITY",
    "HISTORICAL_SAMPLE_INSUFFICIENT": "MORE_RESOLVED_SETUP_HISTORY",
    "SURVIVAL_FRAGILE": "LARGER_SURVIVAL_MARGIN",
    "ECONOMICS_SENSITIVITY_FRAGILE": "ROBUST_POSITIVE_ECONOMICS_UNDER_SHOCK",
}

_DATA_BLOCKERS = {"HISTORICAL_SAMPLE_INSUFFICIENT", "PROBABILITY_EDGE_NOT_TRUSTWORTHY"}


def _economic_diagnosis(reasons: list[str], confirmation: str) -> dict[str, Any]:
    unique = list(dict.fromkeys(_text(x) for x in reasons if _text(x)))
    ranked = sorted(unique, key=lambda x: (_VETO_PRIORITY.get(x, 1000), x))
    primary = ranked[0] if ranked else "NONE"
    secondary = [x for x in ranked if x != primary]
    layers = list(dict.fromkeys(_VETO_LAYER.get(x, "OTHER") for x in ranked))
    primary_class = "DATA_INSUFFICIENT" if primary in _DATA_BLOCKERS else (
        "CONFIRMATION_REQUIRED" if primary == "ENTRY_CONFIRMATION" else "TRADE_INVALIDATION")
    if primary == "NONE" and confirmation != "CONFIRMED":
        primary = "ENTRY_CONFIRMATION"
        primary_class = "CONFIRMATION_REQUIRED"
        layers = ["CONFIRMATION"]
    return {
        "primary_veto": primary,
        "secondary_vetoes": secondary,
        "blocking_layers": layers,
        "veto_class": primary_class,
        "next_required_event": _NEXT_EVENT.get(primary, "NEW_CLOSED_CANDLE_EVIDENCE"),
        "next_required_events": list(dict.fromkeys(_NEXT_EVENT.get(x, "NEW_CLOSED_CANDLE_EVIDENCE") for x in ranked)),
        "veto_count": len(unique),
    }


def _num(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if x == x else default
    except (TypeError, ValueError):
        return default


def _text(v: Any) -> str:
    return str(v or "").upper().strip()


def _evidence(results: dict[str, EngineResult], key: str) -> dict[str, Any]:
    e = results.get(key)
    return dict(e.output or {}) if e else {}


def _first_num(m: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        try:
            x = float(m[key])
            if x == x and x > 0:
                return x
        except (KeyError, TypeError, ValueError):
            pass
    return None


def _direction(e6: dict[str, Any]) -> str:
    for raw in (e6.get("direction"), e6.get("direction_thesis"), e6.get("thesis_direction")):
        x = _text(raw)
        if x in {"BUY", "BULLISH", "UP", "LONG", "BUYERS", "TREND_UP"}:
            return "BUY"
        if x in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS", "TREND_DOWN"}:
            return "SELL"
    parts = _text(e6.get("finding")).split()
    if parts and parts[0] in {"BUY", "BULLISH", "UP", "LONG"}:
        return "BUY"
    if parts and parts[0] in {"SELL", "BEARISH", "DOWN", "SHORT"}:
        return "SELL"
    return "NEUTRAL"


def _setup(e6: dict[str, Any]) -> str:
    for key in ("setup", "setup_family", "setup_type", "thesis_setup"):
        if e6.get(key) not in (None, ""):
            return str(e6[key])
    parts = str(e6.get("finding") or "").split()
    return parts[1] if len(parts) >= 2 and _text(parts[0]) in {"BUY", "SELL"} else "UNKNOWN"


def _confirmation(e7: dict[str, Any]) -> tuple[str, list[str]]:
    reasons = [_text(x) for x in (e7.get("reason_codes") or e7.get("reasons") or [])]
    hard_missing = {
        "PROOF_GATES_INCOMPLETE", "VALID_CLOSED_CANDLE_TRIGGER_MISSING",
        "TRIGGER_OBSERVED_NOT_AUTOMATIC_CONFIRMATION", "LIQUIDITY_RECLAIM_LEVEL_REQUIRED",
    }
    hard_confirmed = {"CONFIRMATION_PROVEN", "CAUSAL_FOLLOW_THROUGH_PROVEN"}
    if any(x in hard_missing for x in reasons):
        return "NOT_CONFIRMED", reasons
    if any(x in hard_confirmed for x in reasons):
        return "CONFIRMED", reasons
    trace: list[str] = []
    for key in ("confirmation", "confirmation_state", "trigger_state", "proof_state"):
        if e7.get(key) not in (None, ""):
            trace.append(_text(e7[key]))
    proof = e7.get("proof_gates")
    if isinstance(proof, dict):
        for key in ("confirmation", "closed_candle_confirmation", "follow_through"):
            value = proof.get(key)
            if value is True or _text(value) in {"PASS", "CONFIRMED", "PROVEN", "VALID", "VALIDATED"}:
                trace.append("CONFIRMED")
            elif value is False or _text(value) in {"FAIL", "PENDING", "UNAVAILABLE", "NOT_PROVEN"}:
                trace.append("NOT_CONFIRMED")
    for key in ("confirmed", "confirmation_proven", "closed_candle_confirmed"):
        if key in e7:
            trace.append("CONFIRMED" if bool(e7[key]) else "NOT_CONFIRMED")
    state = "CONFIRMED" if any(x in {"CONFIRMED", "PROVEN", "VALIDATED"} for x in trace) else "NOT_CONFIRMED"
    return state, trace + reasons


def _true_range(bars: list[dict[str, Any]], i: int) -> float:
    if i <= 0 or i >= len(bars):
        return 0.0
    h, l = _num(bars[i].get("high")), _num(bars[i].get("low"))
    pc = _num(bars[i - 1].get("close"))
    if h <= 0 or l < 0 or pc <= 0:
        return 0.0
    return max(h - l, abs(h - pc), abs(l - pc))


def _atr_at(bars: list[dict[str, Any]], index: int, period: int = ATR_PERIOD) -> float:
    start = max(1, index - period + 1)
    trs = [_true_range(bars, i) for i in range(start, index + 1)]
    trs = [x for x in trs if x > 0]
    return mean(trs) if trs else 0.0


def _atr(bars: list[dict[str, Any]], period: int = ATR_PERIOD) -> float:
    return _atr_at(bars, len(bars) - 1, period) if bars else 0.0


def _levels(e3: dict[str, Any], e4: dict[str, Any], e5: dict[str, Any], bars: list[dict[str, Any]]) -> dict[str, Any]:
    prior = bars[-(STRUCTURE_LOOKBACK + 1):-1]
    highs = [_num(x.get("high")) for x in prior if _num(x.get("high")) > 0]
    lows = [_num(x.get("low")) for x in prior if _num(x.get("low")) > 0]
    return {
        "protected_high": _first_num(e3, ("protected_high", "external_protected_high", "internal_protected_high")),
        "protected_low": _first_num(e3, ("protected_low", "external_protected_low", "internal_protected_low")),
        "next_resistance": _first_num(e5, ("next_resistance", "nearest_resistance", "resistance")),
        "next_support": _first_num(e5, ("next_support", "nearest_support", "support")),
        "liquidity_event_level": _first_num(e4, ("event_level", "liquidity_level", "nearest_liquidity", "opposing_liquidity_level")),
        "structure_high_20": max(highs) if highs else None,
        "structure_low_20": min(lows) if lows else None,
    }


def _target(levels: dict[str, Any], direction: str, entry: float, atr: float, e4: dict[str, Any]) -> dict[str, Any]:
    raw = ([
        ("RESISTANCE", levels.get("next_resistance"), 92.0),
        ("PROTECTED_HIGH", levels.get("protected_high"), 90.0),
        ("LIQUIDITY_EVENT", levels.get("liquidity_event_level"), 80.0),
        ("STRUCTURE_HIGH_20", levels.get("structure_high_20"), 70.0),
    ] if direction == "BUY" else [
        ("SUPPORT", levels.get("next_support"), 92.0),
        ("PROTECTED_LOW", levels.get("protected_low"), 90.0),
        ("LIQUIDITY_EVENT", levels.get("liquidity_event_level"), 80.0),
        ("STRUCTURE_LOW_20", levels.get("structure_low_20"), 70.0),
    ] if direction == "SELL" else [])
    candidates: list[dict[str, Any]] = []
    for source, level, quality in raw:
        if level is None or not (level > entry if direction == "BUY" else level < entry):
            continue
        distance = abs(level - entry)
        distance_atr = distance / max(atr, 1e-9)
        rejection: list[str] = []
        if distance_atr < MIN_TARGET_CLEARANCE_ATR:
            rejection.append("CLEARANCE_TOO_SMALL")
        if distance_atr > MAX_TARGET_EXTENSION_ATR:
            rejection.append("EXTENSION_TOO_FAR")
        if source.startswith("STRUCTURE_"):
            quality = min(quality, 62.0)
        if source == "LIQUIDITY_EVENT":
            ext = _text(e4.get("liquidity_externality"))
            state = _text(e4.get("auction_state"))
            info = _text(e4.get("auction_information"))
            if ext == "EXTERNAL":
                quality += 5
            elif ext == "INTERNAL":
                quality -= 10
            if state == "PENDING":
                rejection.append("AUCTION_PENDING")
            if info == "LOW_INFORMATION":
                rejection.append("LOW_INFORMATION_LIQUIDITY")
        quality = max(0.0, min(100.0, quality))
        candidates.append({
            "source": source, "level": level, "distance": distance, "distance_atr": distance_atr,
            "quality": quality, "credible": quality >= TARGET_QUALITY_MIN and not rejection,
            "rejection": rejection,
        })
    credible = [x for x in candidates if x["credible"]]
    if not credible:
        return {"source": None, "level": None, "distance": 0.0, "distance_atr": 0.0,
                "quality": 0.0, "credible": False, "rejection": ["NO_CREDIBLE_OPPOSING_BARRIER"],
                "candidate_trace": candidates, "selection_rule": "NEAREST_CREDIBLE_OPPOSING_BARRIER"}
    selected = min(credible, key=lambda x: (x["distance_atr"], -x["quality"]))
    return {**selected, "candidate_trace": candidates, "selection_rule": "NEAREST_CREDIBLE_OPPOSING_BARRIER"}


def _space(e5: dict[str, Any], target: dict[str, Any], direction: str) -> dict[str, Any]:
    key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short"
    e5_space = _num(e5.get(key)) if e5.get(key) is not None else 0.0
    target_space = _num(target.get("distance_atr")) if target.get("credible") else 0.0
    vals = [v for v in (e5_space, target_space) if v > 0]
    if not vals:
        return {"state": "UNAVAILABLE", "e5_available_space_atr": e5_space,
                "target_barrier_space_atr": target_space, "effective_available_space_atr": 0.0,
                "space_consistency_delta_atr": None, "space_source": "NO_USABLE_SPACE_EVIDENCE",
                "space_ok": False, "space_conflict": False}
    effective = min(vals)
    delta = abs(e5_space - target_space) if e5_space > 0 and target_space > 0 else None
    conflict = delta is not None and delta >= SPACE_CONFLICT_ATR
    state = "CONFLICTED" if conflict else ("CONSTRAINED" if effective < MIN_SPACE_ATR else "USABLE")
    return {"state": state, "e5_available_space_atr": e5_space, "target_barrier_space_atr": target_space,
            "effective_available_space_atr": effective, "space_consistency_delta_atr": delta,
            "space_source": "MIN(E5_LOCATION,TARGET_BARRIER)" if len(vals) == 2 else "AVAILABLE_EVIDENCE",
            "space_ok": state == "USABLE", "space_conflict": conflict}


def _stop(direction: str, entry: float, atr: float, levels: dict[str, Any]) -> dict[str, Any]:
    candidates = ([
        ("PROTECTED_LOW", levels.get("protected_low"), 100.0),
        ("STRUCTURE_LOW_20", levels.get("structure_low_20"), 80.0),
    ] if direction == "BUY" else [
        ("PROTECTED_HIGH", levels.get("protected_high"), 100.0),
        ("STRUCTURE_HIGH_20", levels.get("structure_high_20"), 80.0),
    ] if direction == "SELL" else [])
    candidates = [x for x in candidates if x[1] is not None and
                  ((direction == "BUY" and x[1] < entry) or (direction == "SELL" and x[1] > entry))]
    evaluated: list[dict[str, Any]] = []
    for source, level, quality in candidates:
        stop = level - RISK_ATR_BUFFER * atr if direction == "BUY" else level + RISK_ATR_BUFFER * atr
        risk_atr = abs(entry - stop) / max(atr, 1e-9)
        width_valid = MIN_STOP_ATR <= risk_atr <= MAX_STOP_ATR
        evaluated.append({"source": source, "level": level, "stop": stop, "quality": quality,
                          "risk_atr": risk_atr, "width_valid": width_valid})
    if not evaluated:
        fallback = entry - FALLBACK_STOP_ATR * atr if direction == "BUY" else entry + FALLBACK_STOP_ATR * atr
        return {"source": None, "level": None, "stop": fallback, "basis": "ATR_FALLBACK_LOWER_CONFIDENCE",
                "quality": 0.0, "risk_atr": FALLBACK_STOP_ATR, "candidate_trace": [], "structural": False}
    valid = [x for x in evaluated if x["width_valid"]]
    selected = max(valid, key=lambda x: (x["quality"], -x["risk_atr"])) if valid else min(evaluated, key=lambda x: x["risk_atr"])
    return {"source": selected["source"], "level": selected["level"], "stop": selected["stop"],
            "basis": "STRUCTURAL_LEVEL_PLUS_ATR_BUFFER", "quality": selected["quality"],
            "risk_atr": selected["risk_atr"], "candidate_trace": evaluated, "structural": True,
            "selection_rule": "BEST_STRUCTURAL_QUALITY_WITH_VALID_ATR_WIDTH" if valid else "NEAREST_STRUCTURAL_LEVEL_FALLBACK"}


def _historical_mae(bars: list[dict[str, Any]], direction: str) -> dict[str, Any]:
    end = len(bars) - MAE_HORIZON_BARS - 1
    start = max(ATR_PERIOD + 1, len(bars) - MAE_LOOKBACK - MAE_HORIZON_BARS - 1)
    values: list[float] = []
    if end >= start:
        for i in range(start, end + 1):
            a = _atr_at(bars, i)
            entry = _num(bars[i].get("close"))
            if a <= 0 or entry <= 0:
                continue
            adverse = 0.0
            for j in range(i + 1, min(len(bars), i + 1 + MAE_HORIZON_BARS)):
                low, high = _num(bars[j].get("low")), _num(bars[j].get("high"))
                adverse_price = max(0.0, entry - low) if direction == "BUY" else max(0.0, high - entry)
                adverse = max(adverse, adverse_price / a)
            values.append(adverse)
    if len(values) < MIN_MAE_SAMPLES:
        return {"state": "UNAVAILABLE", "sample": len(values), "window_bars": MAE_LOOKBACK,
                "horizon_bars": MAE_HORIZON_BARS, "max_adverse_excursion_atr": None,
                "median_adverse_excursion_atr": None, "p95_adverse_excursion_atr": None,
                "survival_margin_atr": None, "risk_atr": None,
                "method": "HISTORICAL_HYPOTHETICAL_ENTRY_MAE"}
    values.sort()
    p95 = values[min(len(values) - 1, int((len(values) - 1) * 0.95))]
    return {"state": "CALCULATED", "sample": len(values), "window_bars": MAE_LOOKBACK,
            "horizon_bars": MAE_HORIZON_BARS, "max_adverse_excursion_atr": max(values),
            "median_adverse_excursion_atr": median(values), "p95_adverse_excursion_atr": p95,
            "historical_mae_p95_atr": p95, "risk_atr": None, "survival_margin_atr": None,
            "method": "HISTORICAL_HYPOTHETICAL_ENTRY_MAE"}


def _survival(mae: dict[str, Any], risk_atr: float) -> dict[str, Any]:
    if mae.get("state") != "CALCULATED" or risk_atr <= 0:
        return {**mae, "state": "UNAVAILABLE", "risk_atr": risk_atr}
    p95 = _num(mae.get("p95_adverse_excursion_atr"), 0.0)
    margin = risk_atr - p95
    state = "ROBUST" if margin >= MIN_SURVIVAL_MARGIN_ATR else "FRAGILE" if margin >= 0 else "NON_SURVIVABLE"
    return {**mae, "state": state, "risk_atr": risk_atr, "survival_margin_atr": margin,
            "tail_excursion_ratio": _num(mae.get("max_adverse_excursion_atr")) / max(risk_atr, 1e-9)}


def _execution(snapshot: dict[str, Any], atr: float) -> dict[str, Any]:
    spread = _first_num(snapshot, ("spread", "spread_price", "current_spread")) or 0.0
    slippage = _first_num(snapshot, ("slippage", "slippage_price", "expected_slippage")) or 0.0
    total = max(0.0, spread + slippage)
    cost_atr = total / atr if atr > 0 else float("inf")
    return {"spread": spread, "slippage": slippage, "total_cost": total, "cost_atr": cost_atr,
            "cost_ok": atr > 0 and cost_atr <= MAX_EXECUTION_COST_ATR}


def _wilson_interval(wins: int, losses: int, z: float = WILSON_Z) -> tuple[float, float]:
    n = wins + losses
    if n <= 0:
        return 0.0, 1.0
    p = wins / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = p + z2 / (2.0 * n)
    spread = z * sqrt((p * (1.0 - p) / n) + (z2 / (4.0 * n * n)))
    return max(0.0, (centre - spread) / denom), min(1.0, (centre + spread) / denom)


def _historical_probability(snapshot: dict[str, Any], direction: str, setup: str) -> dict[str, Any]:
    records = snapshot.get("historical_outcomes") or snapshot.get("setup_history") or snapshot.get("historical_trades")
    if not isinstance(records, list):
        return {"state": "UNQUANTIFIED", "probability": None, "quality": None, "sample": 0,
                "source": None, "source_engine": None, "stress_probability": None,
                "wilson_lower": None, "wilson_upper": None, "decision_probability": None,
                "trusted": False, "minimum_probability": MIN_PROBABILITY,
                "method": "NO_SETUP_HISTORY_AVAILABLE"}
    matches: list[dict[str, Any]] = []
    setup_key = _text(setup)
    for row in records:
        if not isinstance(row, dict):
            continue
        rdir = _text(row.get("direction") or row.get("side"))
        rsetup = _text(row.get("setup") or row.get("setup_family") or row.get("setup_type"))
        if rdir and rdir != direction:
            continue
        # When E6 has identified a concrete setup, unlabeled or differently
        # labeled outcomes are not allowed to masquerade as setup evidence.
        if setup_key != "UNKNOWN" and rsetup != setup_key:
            continue
        if setup_key == "UNKNOWN" and rsetup:
            continue
        matches.append(row)
    wins = losses = 0
    for row in matches:
        result = row.get("win")
        if result is None:
            result = row.get("outcome")
        if isinstance(result, str):
            result = _text(result) in {"WIN", "WON", "PROFIT", "TP", "SUCCESS"}
            if _text(row.get("outcome")) in {"LOSS", "LOST", "SL", "FAIL"}:
                result = False
        if isinstance(result, bool):
            wins += int(result)
            losses += int(not result)
    n = wins + losses
    if n == 0:
        return {"state": "UNQUANTIFIED", "probability": None, "quality": None, "sample": 0,
                "source": "historical_outcomes", "source_engine": "SNAPSHOT", "stress_probability": None,
                "wilson_lower": None, "wilson_upper": None, "decision_probability": None,
                "trusted": False, "minimum_probability": MIN_PROBABILITY, "method": "NO_RESOLVED_SETUP_OUTCOMES"}
    p = (wins + 1.0) / (n + 2.0)
    lower, upper = _wilson_interval(wins, losses)
    interval_width = max(0.0, upper - lower)
    sample_quality = min(100.0, 55.0 + 45.0 * min(1.0, n / 100.0))
    quality = max(0.0, min(100.0, sample_quality * (1.0 - 0.50 * interval_width)))
    decision_probability = lower
    trusted = (n >= MIN_PROBABILITY_SAMPLE and quality >= MIN_PROBABILITY_QUALITY
               and lower >= MIN_WILSON_LOWER)
    stress_probability = max(0.0, decision_probability - PROBABILITY_STRESS)
    return {"state": "TRUSTED" if trusted else "UNTRUSTED", "probability": p, "quality": quality,
            "sample": n, "wins": wins, "losses": losses, "source": "historical_outcomes",
            "source_engine": "SNAPSHOT", "stress_probability": stress_probability,
            "wilson_lower": lower, "wilson_upper": upper, "decision_probability": decision_probability,
            "trusted": trusted, "minimum_probability": MIN_PROBABILITY,
            "method": "SETUP_DIRECTION_CONDITIONED_WILSON"}


def _probability(e7: dict[str, Any], snapshot: dict[str, Any], direction: str, setup: str) -> dict[str, Any]:
    hist = _historical_probability(snapshot, direction, setup)
    if hist.get("trusted") or hist.get("sample", 0) > 0:
        return hist
    for source_name, source in (("E7", e7), ("SNAPSHOT", snapshot)):
        for key in ("historical_probability", "win_probability", "probability", "estimated_probability"):
            if key not in source:
                continue
            p = _num(source.get(key), -1.0)
            if p > 1.0:
                p /= 100.0
            if 0.0 < p <= 1.0:
                q = _num(source.get("probability_quality"), 0.0)
                n = int(_num(source.get("probability_sample"), 0.0))
                lower = _num(source.get("probability_lower_bound"), 0.0)
                upper = _num(source.get("probability_upper_bound"), 1.0)
                if lower <= 0.0 or upper < lower:
                    lower, upper = _wilson_interval(int(round(p * n)), max(0, n - int(round(p * n)))) if n else (0.0, 1.0)
                decision_probability = lower if n else p
                trusted = (q >= MIN_PROBABILITY_QUALITY and n >= MIN_PROBABILITY_SAMPLE
                           and decision_probability >= MIN_WILSON_LOWER)
                return {"state": "TRUSTED" if trusted else "UNTRUSTED", "probability": p,
                        "quality": q, "sample": n, "source": key, "source_engine": source_name,
                        "stress_probability": max(0.0, decision_probability - PROBABILITY_STRESS),
                        "wilson_lower": lower, "wilson_upper": upper,
                        "decision_probability": decision_probability, "trusted": trusted,
                        "minimum_probability": MIN_PROBABILITY, "method": "UPSTREAM_PROBABILITY_WITH_CONFIDENCE_BOUND"}
    return hist


def _geometry(direction: str, entry: float, stop: float, target: float, atr: float, cost_atr: float) -> dict[str, Any]:
    side_ok = (direction == "BUY" and stop < entry < target) or (direction == "SELL" and target < entry < stop)
    risk_price = abs(entry - stop)
    reward_price = abs(target - entry)
    risk_atr = risk_price / max(atr, 1e-9)
    nominal_rr = reward_price / max(risk_price, 1e-9)
    effective_reward_atr = max(0.0, reward_price / max(atr, 1e-9) - cost_atr)
    effective_risk_atr = risk_atr + cost_atr
    real_rr = effective_reward_atr / max(effective_risk_atr, 1e-9)
    return {"side_valid": side_ok, "risk_price": risk_price, "reward_price": reward_price,
            "risk_atr": risk_atr, "nominal_rr": nominal_rr, "real_rr": real_rr,
            "effective_reward_atr": effective_reward_atr, "effective_risk_atr": effective_risk_atr}


def _target_realism(target: dict[str, Any], space: dict[str, Any], survival: dict[str, Any],
                    geometry: dict[str, Any], e4: dict[str, Any]) -> dict[str, Any]:
    q = _num(target.get("quality"), 0.0) / 100.0
    target_distance = _num(target.get("distance_atr"))
    available = _num(space.get("effective_available_space_atr"))
    space_ratio = min(1.0, available / max(target_distance, 1e-9)) if target.get("credible") else 0.0
    p95 = _num(survival.get("p95_adverse_excursion_atr"), 0.0)
    risk_atr = max(_num(geometry.get("risk_atr")), 1e-9)
    survival_ratio = max(0.0, min(1.0, 1.0 - p95 / risk_atr)) if survival.get("state") != "UNAVAILABLE" else 0.0
    auction_penalty = 0.15 if _text(e4.get("auction_state")) == "PENDING" else 0.0
    realism = max(0.0, min(1.0, 0.45 * q + 0.30 * space_ratio + 0.25 * survival_ratio - auction_penalty))
    return {"score": realism, "state": "REALISTIC" if realism >= MIN_TARGET_REALISM else "UNREALISTIC",
            "quality_component": q, "space_component": space_ratio,
            "survival_component": survival_ratio, "auction_penalty": auction_penalty}


def _stop_quality(stop_plan: dict[str, Any], survival: dict[str, Any], geometry: dict[str, Any]) -> dict[str, Any]:
    base = _num(stop_plan.get("quality"), 0.0)
    if not stop_plan.get("structural"):
        return {"score": 0.0, "state": "FALLBACK_ONLY", "structural": False}
    margin = _num(survival.get("survival_margin_atr"), -1.0)
    survival_component = max(0.0, min(100.0, 50.0 + 50.0 * margin / max(MIN_SURVIVAL_MARGIN_ATR, 1e-9)))
    width = _num(geometry.get("risk_atr"), 0.0)
    width_component = 100.0 if MIN_STOP_ATR <= width <= MAX_STOP_ATR else 0.0
    score = 0.55 * base + 0.30 * survival_component + 0.15 * width_component
    return {"score": max(0.0, min(100.0, score)), "state": "QUALITY" if score >= MIN_STOP_QUALITY else "WEAK",
            "structural": True}


def _economic(geometry: dict[str, Any], probability: dict[str, Any], execution: dict[str, Any],
              survival: dict[str, Any], space: dict[str, Any], target_realism: dict[str, Any],
              stop_quality: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    rr = _num(geometry.get("real_rr"))
    cost_atr = _num(execution.get("cost_atr"), float("inf"))
    if rr < MIN_RR:
        reasons.append("REAL_RR_BELOW_MINIMUM")
    if cost_atr > MAX_EXECUTION_COST_ATR:
        reasons.append("EXECUTION_COST_TOO_HIGH")
    if survival.get("state") in {"NON_SURVIVABLE", "UNAVAILABLE"}:
        reasons.append("STRUCTURAL_SURVIVAL_NOT_PROVEN")
    elif survival.get("state") == "FRAGILE":
        reasons.append("SURVIVAL_FRAGILE")
    if space.get("state") in {"UNAVAILABLE", "CONFLICTED"}:
        reasons.append("EFFECTIVE_SPACE_UNRELIABLE")
    elif _num(space.get("effective_available_space_atr")) < MIN_SPACE_ATR:
        reasons.append("EFFECTIVE_SPACE_BELOW_MINIMUM")
    if target_realism.get("state") != "REALISTIC":
        reasons.append("TARGET_REALISM_TOO_LOW")
    if stop_quality.get("state") != "QUALITY":
        reasons.append("STOP_QUALITY_TOO_LOW")

    ev = breakeven = margin = None
    stress_p = probability.get("stress_probability")
    if probability.get("trusted") and stress_p is not None:
        p = _num(stress_p)
        reward = max(0.0, rr - cost_atr)
        risk = 1.0 + cost_atr
        breakeven = risk / max(risk + reward, 1e-9)
        ev = p * reward - (1.0 - p) * risk
        margin = p - breakeven
        if p < MIN_PROBABILITY:
            reasons.append("STRESSED_PROBABILITY_BELOW_MINIMUM")
        if ev < MIN_ECONOMIC_EDGE:
            reasons.append("PROBABILITY_EDGE_NOT_POSITIVE")
        if margin < ROBUSTNESS_MIN_MARGIN:
            reasons.append("ECONOMIC_MARGIN_TOO_THIN")
    else:
        reasons.append("PROBABILITY_EDGE_NOT_TRUSTWORTHY")

    hard = {"REAL_RR_BELOW_MINIMUM", "EXECUTION_COST_TOO_HIGH", "STRUCTURAL_SURVIVAL_NOT_PROVEN",
            "EFFECTIVE_SPACE_UNRELIABLE", "EFFECTIVE_SPACE_BELOW_MINIMUM",
            "STRESSED_PROBABILITY_BELOW_MINIMUM", "PROBABILITY_EDGE_NOT_POSITIVE",
            "ECONOMIC_MARGIN_TOO_THIN", "TARGET_REALISM_TOO_LOW", "STOP_QUALITY_TOO_LOW"}
    state = "NOT_EVALUABLE" if not probability.get("trusted") else (
        "ECONOMICALLY_INVALID" if any(x in hard for x in reasons) else
        "FRAGILE" if reasons else "ECONOMICALLY_ACCEPTABLE")
    return {"state": state, "expected_value_r": ev, "economic_edge_r": ev, "rr_used": rr,
            "stress_probability": stress_p, "breakeven_probability": breakeven,
            "economic_margin": margin, "effective_reward_r": max(0.0, rr - cost_atr),
            "effective_risk_r": 1.0 + cost_atr, "reasons": reasons}


def _sensitivity(direction: str, entry: float, stop: float, target: float, atr: float,
                 probability: dict[str, Any], cost_atr: float) -> dict[str, Any]:
    p = probability.get("stress_probability")
    if atr <= 0 or p is None or target <= 0:
        return {"state": "UNQUANTIFIED"}
    p = _num(p)

    def ev(e: float, s: float, t: float) -> float:
        risk = abs(e - s)
        reward = abs(t - e)
        if risk <= 0 or reward <= 0:
            return -1.0
        rr = reward / risk
        return p * max(0.0, rr - cost_atr) - (1.0 - p) * (1.0 + cost_atr)

    ew = entry + (SENSITIVITY_ENTRY_ATR * atr if direction == "BUY" else -SENSITIVITY_ENTRY_ATR * atr)
    sw = stop - (SENSITIVITY_STOP_ATR * atr if direction == "BUY" else -SENSITIVITY_STOP_ATR * atr)
    tw = target - (SENSITIVITY_TARGET_ATR * atr if direction == "BUY" else -SENSITIVITY_TARGET_ATR * atr)
    vals = [ev(ew, stop, target), ev(entry, sw, target), ev(entry, stop, tw)]
    worst = min(vals)
    return {"state": "ROBUST" if worst >= 0 else "FRAGILE", "base": ev(entry, stop, target),
            "entry_worse": vals[0], "stop_worse": vals[1], "target_worse": vals[2],
            "worst_case": worst, "entry_shock_atr": SENSITIVITY_ENTRY_ATR,
            "stop_shock_atr": SENSITIVITY_STOP_ATR, "target_shock_atr": SENSITIVITY_TARGET_ATR}


def _risk_quality(economics: dict[str, Any], survival: dict[str, Any], sensitivity: dict[str, Any],
                  target: dict[str, Any], target_realism: dict[str, Any], stop_quality: dict[str, Any],
                  execution: dict[str, Any], probability: dict[str, Any], confirmation: str) -> dict[str, Any]:
    parts = [
        _num(target.get("quality")) / 100.0,
        _num(target_realism.get("score")),
        _num(stop_quality.get("score")) / 100.0,
        1.0 if survival.get("state") == "ROBUST" else 0.5 if survival.get("state") == "FRAGILE" else 0.0,
        1.0 if sensitivity.get("state") == "ROBUST" else 0.5 if sensitivity.get("state") == "FRAGILE" else 0.0,
        1.0 if economics.get("state") == "ECONOMICALLY_ACCEPTABLE" else 0.5 if economics.get("state") == "FRAGILE" else 0.0,
        max(0.0, 1.0 - min(1.0, _num(execution.get("cost_atr"), 1.0) / max(MAX_EXECUTION_COST_ATR, 1e-9))),
        min(1.0, _num(probability.get("quality"), 0.0) / 100.0),
        1.0 if confirmation == "CONFIRMED" else 0.0,
    ]
    score = sum(parts) / len(parts)
    if score >= RISK_CLASS_A:
        cls = "A"
    elif score >= RISK_CLASS_B:
        cls = "B"
    elif score >= RISK_CLASS_C:
        cls = "C"
    else:
        cls = "NO_TRADE"
    return {"score": score, "class": cls, "components": parts,
            "budget_guidance": {"A": "FULL_ALLOWED_RISK", "B": "REDUCED_RISK",
                                 "C": "MINIMAL_RISK_ONLY", "NO_TRADE": "NO_RISK"}[cls]}


def _confidence(economics: dict[str, Any], survival: dict[str, Any], sensitivity: dict[str, Any],
                target: dict[str, Any], target_realism: dict[str, Any], stop_quality: dict[str, Any],
                execution: dict[str, Any], confirmation: str, probability: dict[str, Any]) -> float:
    components = [
        _num(target.get("quality")) / 100.0,
        _num(target_realism.get("score")),
        _num(stop_quality.get("score")) / 100.0,
        1.0 if survival.get("state") == "ROBUST" else 0.5 if survival.get("state") == "FRAGILE" else 0.0,
        1.0 if sensitivity.get("state") == "ROBUST" else 0.5 if sensitivity.get("state") == "FRAGILE" else 0.0,
        1.0 if economics.get("state") == "ECONOMICALLY_ACCEPTABLE" else 0.5 if economics.get("state") == "FRAGILE" else 0.0,
        max(0.0, 1.0 - min(1.0, _num(execution.get("cost_atr"), 1.0) / max(MAX_EXECUTION_COST_ATR, 1e-9))),
        min(1.0, _num(probability.get("quality"), 0.0) / 100.0),
        1.0 if confirmation == "CONFIRMED" else 0.0,
    ]
    return sum(components) / len(components)


def _unresolved(direction: str, setup: str, confirmation: str, bars: int, atr: float,
                reasons: list[str]) -> EngineResult:
    diagnosis = _economic_diagnosis(reasons, confirmation)
    output = {"engine_id": "E8", "role": "TRADE_ECONOMICS_RISK_ANALYST", "question": QUESTION,
              "architecture": ARCHITECTURE, "version": VERSION, "finding": "UNRESOLVED",
              "direction": direction, "setup": setup, "confirmation": confirmation,
              "economic_state": "NOT_EVALUABLE", "gate_passed": False, "risk_ready": False,
              "observations": [f"valid_candles={bars}", f"atr14={atr:.6f}"],
              "reasons": reasons, "reason_codes": reasons,
              **diagnosis,
              "professional_rule": "E8_ECONOMICS_ONLY_E9_FINAL_AUTHORITY", "decision_authority": "E9"}
    return EngineResult("E8", NAME, False, 0.0, output, tuple(reasons))


def analyze_e8(snapshot: dict[str, Any], results: dict[str, EngineResult]) -> EngineResult:
    bars = list(snapshot.get("bars") or [])
    e3, e4, e5, e6, e7 = (_evidence(results, k) for k in ("E3", "E4", "E5", "E6", "E7"))
    reasons: list[str] = []
    direction, setup = _direction(e6), _setup(e6)
    confirmation, confirmation_trace = _confirmation(e7)

    if len(bars) < MIN_BARS:
        return _unresolved(direction, setup, confirmation, len(bars), 0.0, ["INSUFFICIENT_BARS"])

    atr = _atr(bars)
    entry = _num(snapshot.get("price") or snapshot.get("close") or bars[-1].get("close"))
    if atr <= 0 or entry <= 0:
        return _unresolved(direction, setup, confirmation, len(bars), atr, ["INVALID_ECONOMIC_INPUTS"])
    if direction == "NEUTRAL":
        return _unresolved(direction, setup, confirmation, len(bars), atr, ["DIRECTION_UNRESOLVED"])

    levels = _levels(e3, e4, e5, bars)
    target = _target(levels, direction, entry, atr, e4)
    stop_plan = _stop(direction, entry, atr, levels)
    stop = _num(stop_plan.get("stop"))
    target_valid = bool(target.get("credible") and target.get("level") is not None)
    if not target_valid:
        reasons.append("NO_USABLE_STRUCTURAL_TARGET")
    target_level = _num(target.get("level")) if target_valid else 0.0

    execution = _execution(snapshot, atr)
    geometry = _geometry(direction, entry, stop, target_level, atr, execution["cost_atr"]) if target_valid and stop > 0 else {
        "side_valid": False, "risk_price": abs(entry - stop), "reward_price": 0.0,
        "risk_atr": abs(entry - stop) / max(atr, 1e-9), "nominal_rr": 0.0,
        "real_rr": 0.0, "effective_reward_atr": 0.0, "effective_risk_atr": 0.0}
    if not geometry["side_valid"]:
        reasons.append("INVALID_TRADE_GEOMETRY")
    risk_atr = geometry["risk_atr"]
    if risk_atr < MIN_STOP_ATR:
        reasons.append("STOP_TOO_TIGHT")
    if risk_atr > MAX_STOP_ATR:
        reasons.append("STOP_TOO_WIDE")
    if target_valid and geometry["real_rr"] < MIN_RR:
        reasons.append("REAL_RR_BELOW_MINIMUM")

    space = _space(e5, target, direction)
    if space["state"] == "CONFLICTED":
        reasons.append("SPACE_CONFLICT")

    mae = _historical_mae(bars, direction)
    survival = _survival(mae, risk_atr)
    probability = _probability(e7, snapshot, direction, setup)
    if probability.get("sample", 0) < MIN_PROBABILITY_SAMPLE:
        reasons.append("HISTORICAL_SAMPLE_INSUFFICIENT")
    target_realism = _target_realism(target, space, survival, geometry, e4)
    stop_quality = _stop_quality(stop_plan, survival, geometry)
    economics = _economic(geometry, probability, execution, survival, space, target_realism, stop_quality)
    sensitivity = _sensitivity(direction, entry, stop, target_level, atr, probability, execution["cost_atr"]) if target_valid else {"state": "UNQUANTIFIED"}
    risk_quality = _risk_quality(economics, survival, sensitivity, target, target_realism, stop_quality, execution, probability, confirmation)

    if confirmation != "CONFIRMED":
        reasons.append("ENTRY_CONFIRMATION")
    for code in economics["reasons"]:
        if code not in reasons:
            reasons.append(code)
    if sensitivity.get("state") == "FRAGILE":
        reasons.append("ECONOMICS_SENSITIVITY_FRAGILE")

    hard_fail = any(code in reasons for code in {
        "NO_USABLE_STRUCTURAL_TARGET", "INVALID_TRADE_GEOMETRY", "REAL_RR_BELOW_MINIMUM",
        "EFFECTIVE_SPACE_BELOW_MINIMUM", "SPACE_CONFLICT", "STOP_TOO_TIGHT", "STOP_TOO_WIDE",
        "STRUCTURAL_SURVIVAL_NOT_PROVEN", "EXECUTION_COST_TOO_HIGH", "ENTRY_CONFIRMATION",
        "STRESSED_PROBABILITY_BELOW_MINIMUM", "EFFECTIVE_SPACE_UNRELIABLE",
        "PROBABILITY_EDGE_NOT_POSITIVE", "ECONOMIC_MARGIN_TOO_THIN",
        "TARGET_REALISM_TOO_LOW", "STOP_QUALITY_TOO_LOW"})
    risk_ready = bool(
        confirmation == "CONFIRMED" and target_valid and geometry["side_valid"]
        and MIN_STOP_ATR <= risk_atr <= MAX_STOP_ATR
        and geometry["real_rr"] >= MIN_RR and space["space_ok"]
        and survival["state"] == "ROBUST" and execution["cost_ok"]
        and probability["trusted"] and economics["state"] == "ECONOMICALLY_ACCEPTABLE"
        and sensitivity.get("state") == "ROBUST" and target_realism["state"] == "REALISTIC"
        and stop_quality["state"] == "QUALITY" and risk_quality["class"] in {"A", "B"}
        and not hard_fail)

    if risk_ready:
        finding, gate = "ECONOMICALLY_ACCEPTABLE", True
    elif economics["state"] == "NOT_EVALUABLE":
        finding, gate = "UNRESOLVED", False
    else:
        finding, gate = ("ECONOMICALLY_INVALID" if hard_fail or economics["state"] == "ECONOMICALLY_INVALID" else "FRAGILE"), False

    diagnosis = _economic_diagnosis(reasons, confirmation)
    confidence = _confidence(economics, survival, sensitivity, target, target_realism, stop_quality, execution, confirmation, probability)
    if risk_ready:
        confidence = max(confidence, 0.70)

    observations = [
        f"bars={len(bars)}", f"atr14={atr:.6f}", f"entry={entry:.8f}", f"risk_atr={risk_atr:.6f}",
        f"nominal_rr={geometry['nominal_rr']:.6f}", f"real_rr={geometry['real_rr']:.6f}",
        f"target={target.get('source') or 'NONE'}", f"target_selection={target.get('selection_rule')}",
        f"target_realism={target_realism['score']:.6f}", f"stop_quality={stop_quality['score']:.6f}",
        f"stop_selection={stop_plan.get('selection_rule')}",
        f"space={space['state']}", f"survival={survival['state']}",
        f"mae_method={survival.get('method')}", f"mae_samples={survival.get('sample', 0)}",
        f"execution_cost_atr={execution['cost_atr']:.6f}",
        f"probability={probability.get('probability') if probability.get('probability') is not None else 'UNQUANTIFIED'}",
        f"probability_sample={probability.get('sample', 0)}", f"probability_method={probability.get('method')}",
        f"wilson_lower={probability.get('wilson_lower') if probability.get('wilson_lower') is not None else 'UNQUANTIFIED'}",
        f"wilson_upper={probability.get('wilson_upper') if probability.get('wilson_upper') is not None else 'UNQUANTIFIED'}",
        f"decision_probability={probability.get('decision_probability') if probability.get('decision_probability') is not None else 'UNQUANTIFIED'}",
        f"stress_probability={probability.get('stress_probability') if probability.get('stress_probability') is not None else 'UNQUANTIFIED'}",
        f"breakeven_probability={economics.get('breakeven_probability') if economics.get('breakeven_probability') is not None else 'UNQUANTIFIED'}",
        f"economic_margin={economics.get('economic_margin') if economics.get('economic_margin') is not None else 'UNQUANTIFIED'}",
        f"economic_state={economics['state']}", f"sensitivity={sensitivity.get('state', 'UNQUANTIFIED')}",
        f"risk_quality={risk_quality['score']:.6f}", f"risk_class={risk_quality['class']}",
        f"primary_veto={diagnosis['primary_veto']}", f"veto_class={diagnosis['veto_class']}",
        f"next_required_event={diagnosis['next_required_event']}"]

    trade_plan = {"valid": risk_ready, "direction": direction, "setup": setup, "entry": entry,
                  "stop": stop if risk_ready else None, "target": target_level if risk_ready else None,
                  "risk_price": geometry["risk_price"], "risk_atr": risk_atr,
                  "reward_price": geometry["reward_price"], "rr": geometry["real_rr"],
                  "nominal_rr": geometry["nominal_rr"], "real_rr": geometry["real_rr"],
                  "target_source": target.get("source"), "stop_source": stop_plan.get("source"),
                  "economic_state": economics["state"], "expected_value_r": economics["expected_value_r"],
                  "breakeven_probability": economics.get("breakeven_probability"),
                  "economic_margin": economics.get("economic_margin"), "robustness": sensitivity.get("state", "UNQUANTIFIED"),
                  "target_realism": target_realism["score"], "stop_quality": stop_quality["score"],
                  "risk_quality": risk_quality["score"], "risk_class": risk_quality["class"]}

    output = {"engine_id": "E8", "role": "TRADE_ECONOMICS_RISK_ANALYST", "question": QUESTION,
              "architecture": ARCHITECTURE, "version": VERSION, "finding": finding,
              "direction": direction, "setup": setup, "confirmation": confirmation,
              "confirmation_trace": confirmation_trace, "entry": entry, "atr14": atr,
              "risk_atr": risk_atr, "rr": geometry["real_rr"], "real_rr": geometry["real_rr"],
              "nominal_rr": geometry["nominal_rr"], "target": target, "stop_plan": stop_plan,
              "geometry": geometry, "space": space, "survival": survival, "execution": execution,
              "probability": probability, "target_realism": target_realism, "stop_quality": stop_quality,
              "economics": economics, "sensitivity": sensitivity, "risk_quality": risk_quality,
              "economic_state": economics["state"], "risk_ready": risk_ready, "gate_passed": gate,
              "trade_plan": trade_plan, "observations": observations, "reasons": reasons,
              "reason_codes": reasons, "confidence": confidence,
              **diagnosis,
              "professional_rule": "E8_ECONOMICS_ONLY_E9_FINAL_AUTHORITY", "decision_authority": "E9"}
    return EngineResult("E8", NAME, gate, confidence * 100.0, output, tuple(reasons))
