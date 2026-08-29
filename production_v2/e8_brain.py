from __future__ import annotations

from statistics import mean, median
from typing import Any

from .contracts import EngineResult

NAME = "Trade Economics & Risk Brain"
QUESTION = "Is the proposed trade economically attractive and structurally survivable?"
ARCHITECTURE = "E8_PROFESSIONAL_TRADE_ECONOMICS_RISK_BRAIN_V12"
VERSION = "12.0"

MIN_BARS = 30
MIN_RR = 1.50
ATR_PERIOD = 14
RISK_ATR_BUFFER = 0.20
FALLBACK_STOP_ATR = 1.20
STRUCTURE_LOOKBACK = 20
MIN_STOP_ATR = 0.50
MAX_STOP_ATR = 3.50
MIN_SPACE_ATR = 0.75
MIN_TARGET_CLEARANCE_ATR = 0.10
MAX_TARGET_EXTENSION_ATR = 3.50
TP1_FRACTION = 0.50
MAX_LIQUIDITY_RISK_R = 1.00
MAX_EXECUTION_COST_ATR = 0.15
MAX_LAST_RANGE_ATR = 2.50
MODERATE_EXPANSION_ATR = 1.75
SPACE_CONFLICT_ATR = 0.75
TARGET_QUALITY_MIN = 70.0
SECONDARY_TARGET_QUALITY = 62.0
STOP_STABILITY_MIN_RATIO = 0.75
STOP_STABILITY_MAX_RATIO = 1.35
MIN_SURVIVAL_MARGIN_ATR = 0.15
MAX_ADVERSE_EXCURSION_ATR = 1.00
MIN_ECONOMIC_EDGE = 0.10


def _num(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if value == value else default
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _evidence(e: EngineResult | None) -> dict[str, Any]:
    return dict(e.output or {}) if e else {}


def _first_num(mapping: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        try:
            value = float(mapping[key])
            if value == value and value > 0:
                return value
        except (KeyError, TypeError, ValueError):
            pass
    return None


def _direction(e6: dict[str, Any]) -> str:
    for raw in (e6.get("direction"), e6.get("direction_thesis"), e6.get("thesis_direction")):
        value = _text(raw)
        if value in {"BUY", "BULLISH", "UP", "LONG", "BUYERS", "TREND_UP"}:
            return "BUY"
        if value in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS", "TREND_DOWN"}:
            return "SELL"
    prefix = _text(e6.get("finding")).split()
    if prefix and prefix[0] in {"BUY", "BULLISH", "UP", "LONG"}:
        return "BUY"
    if prefix and prefix[0] in {"SELL", "BEARISH", "DOWN", "SHORT"}:
        return "SELL"
    return "NEUTRAL"


def _setup(e6: dict[str, Any]) -> str:
    for key in ("setup", "setup_family", "setup_type", "thesis_setup"):
        if e6.get(key) not in (None, ""):
            return str(e6[key])
    parts = str(e6.get("finding") or "").split()
    return parts[1] if len(parts) >= 2 and _text(parts[0]) in {"BUY", "SELL"} else "UNKNOWN"


def _confirmation(e7: dict[str, Any]) -> tuple[str, list[str]]:
    observed: list[str] = []
    for key in ("confirmation", "confirmation_state", "trigger_state", "proof_state"):
        if e7.get(key) not in (None, ""):
            observed.append(_text(e7[key]))
    proof = e7.get("proof_gates")
    if isinstance(proof, dict):
        for key in ("confirmation", "closed_candle_confirmation", "follow_through"):
            value = proof.get(key)
            if value is True or value in {"PASS", "CONFIRMED", "PROVEN", "VALID", "VALIDATED"}:
                observed.append("CONFIRMED")
            elif value is False or value in {"FAIL", "PENDING", "UNAVAILABLE", "NOT_PROVEN"}:
                observed.append("NOT_CONFIRMED")
    for key in ("confirmed", "confirmation_proven", "closed_candle_confirmed"):
        if key in e7:
            observed.append("CONFIRMED" if bool(e7[key]) else "NOT_CONFIRMED")
    reasons = [_text(x) for x in (e7.get("reason_codes") or e7.get("reasons") or [])]
    if any(x in {"PROOF_GATES_INCOMPLETE", "VALID_CLOSED_CANDLE_TRIGGER_MISSING", "TRIGGER_OBSERVED_NOT_AUTOMATIC_CONFIRMATION", "LIQUIDITY_RECLAIM_LEVEL_REQUIRED"} for x in reasons):
        return "NOT_CONFIRMED", observed + reasons
    if any(x in {"CONFIRMATION_PROVEN", "CAUSAL_FOLLOW_THROUGH_PROVEN"} for x in reasons):
        return "CONFIRMED", observed + reasons
    return ("CONFIRMED" if any(x in {"CONFIRMED", "PROVEN", "VALIDATED"} for x in observed) else "NOT_CONFIRMED"), observed + reasons


def _atr(bars: list[dict[str, Any]], period: int = ATR_PERIOD) -> float:
    trs: list[float] = []
    for i in range(max(1, len(bars) - period), len(bars)):
        h, l, pc = _num(bars[i].get("high")), _num(bars[i].get("low")), _num(bars[i - 1].get("close"))
        if h > 0 and l >= 0 and pc > 0:
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return mean(trs) if trs else 0.0


def _atr_series(bars: list[dict[str, Any]], period: int = ATR_PERIOD) -> list[float]:
    trs: list[float] = []
    for i in range(1, len(bars)):
        h, l, pc = _num(bars[i].get("high")), _num(bars[i].get("low")), _num(bars[i - 1].get("close"))
        if h > 0 and l >= 0 and pc > 0:
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return [mean(trs[max(0, i - period + 1): i + 1]) for i in range(len(trs))]


def _levels(e3: dict[str, Any], e4: dict[str, Any], e5: dict[str, Any], bars: list[dict[str, Any]]) -> dict[str, Any]:
    recent = bars[-(STRUCTURE_LOOKBACK + 1):-1]
    highs = [_num(x.get("high")) for x in recent if _num(x.get("high")) > 0]
    lows = [_num(x.get("low")) for x in recent if _num(x.get("low")) > 0]
    return {
        "protected_high": _first_num(e3, ("protected_high", "external_protected_high", "internal_protected_high")),
        "protected_low": _first_num(e3, ("protected_low", "external_protected_low", "internal_protected_low")),
        "next_resistance": _first_num(e5, ("next_resistance", "nearest_resistance", "resistance")),
        "next_support": _first_num(e5, ("next_support", "nearest_support", "support")),
        "liquidity_event_level": _first_num(e4, ("event_level", "liquidity_level", "nearest_liquidity", "opposing_liquidity_level")),
        "structure_high_20": max(highs) if highs else None,
        "structure_low_20": min(lows) if lows else None,
    }


def _target_candidates(levels: dict[str, Any], direction: str, entry: float, atr: float, e4: dict[str, Any]) -> list[dict[str, Any]]:
    if direction == "BUY":
        raw = [("RESISTANCE", levels.get("next_resistance"), 92.0, 1), ("PROTECTED_HIGH", levels.get("protected_high"), 90.0, 2), ("LIQUIDITY_EVENT", levels.get("liquidity_event_level"), 80.0, 3), ("STRUCTURE_HIGH_20", levels.get("structure_high_20"), 70.0, 4)]
        directional = [(s, v, q, r) for s, v, q, r in raw if v is not None and v > entry]
    elif direction == "SELL":
        raw = [("SUPPORT", levels.get("next_support"), 92.0, 1), ("PROTECTED_LOW", levels.get("protected_low"), 90.0, 2), ("LIQUIDITY_EVENT", levels.get("liquidity_event_level"), 80.0, 3), ("STRUCTURE_LOW_20", levels.get("structure_low_20"), 70.0, 4)]
        directional = [(s, v, q, r) for s, v, q, r in raw if v is not None and v < entry]
    else:
        return []
    candidates: list[dict[str, Any]] = []
    for source, level, base_quality, rank in directional:
        distance = abs(level - entry)
        distance_atr = distance / max(atr, 1e-9)
        quality = base_quality
        rejection: list[str] = []
        if distance_atr < MIN_TARGET_CLEARANCE_ATR:
            rejection.append("CLEARANCE_TOO_SMALL")
        if distance_atr > MAX_TARGET_EXTENSION_ATR:
            rejection.append("EXTENSION_TOO_FAR")
        if source in {"STRUCTURE_HIGH_20", "STRUCTURE_LOW_20"}:
            quality = min(quality, SECONDARY_TARGET_QUALITY)
        if source == "LIQUIDITY_EVENT":
            ext, state, info = _text(e4.get("liquidity_externality")), _text(e4.get("auction_state")), _text(e4.get("auction_information"))
            if ext == "EXTERNAL": quality += 5.0
            elif ext == "INTERNAL": quality -= 10.0
            if state == "PENDING": rejection.append("AUCTION_PENDING")
            if info == "LOW_INFORMATION": rejection.append("LOW_INFORMATION_LIQUIDITY")
        quality = max(0.0, min(100.0, quality))
        candidates.append({"hierarchy_rank": rank, "source": source, "level": level, "distance": distance, "distance_atr": distance_atr, "quality": quality, "credible": quality >= TARGET_QUALITY_MIN and not rejection, "rejection": rejection})
    candidates.sort(key=lambda x: (x["distance"], x["hierarchy_rank"]))
    return candidates


def _dynamic_target(levels: dict[str, Any], direction: str, entry: float, atr: float, e4: dict[str, Any]) -> dict[str, Any]:
    candidates = _target_candidates(levels, direction, entry, atr, e4)
    credible = [x for x in candidates if x["credible"]]
    if not credible:
        return {"source": None, "level": None, "distance": 0.0, "distance_atr": 0.0, "quality": 0.0, "credible": False, "rejection": ["NO_CREDIBLE_OPPOSING_BARRIER"], "candidate_trace": candidates, "selection_rule": "HIERARCHY_THEN_NEAREST_CREDIBLE_BARRIER"}
    chosen = min(credible, key=lambda x: (x["hierarchy_rank"], x["distance"]))
    return {**chosen, "candidate_trace": candidates, "selection_rule": "HIERARCHY_THEN_NEAREST_CREDIBLE_BARRIER"}


def _space(e5: dict[str, Any], target: dict[str, Any], direction: str) -> dict[str, Any]:
    key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short"
    e5_present = e5.get(key) is not None
    e5_space = _num(e5.get(key)) if e5_present else 0.0
    target_space = _num(target.get("distance_atr")) if target.get("credible") else 0.0
    evidence: list[tuple[str, float]] = []
    if e5_present and e5_space > 0: evidence.append(("E5_LOCATION", e5_space))
    if target.get("credible") and target_space > 0: evidence.append(("TARGET_BARRIER", target_space))
    if not evidence:
        return {"state": "UNAVAILABLE", "e5_available_space_atr": e5_space, "target_barrier_space_atr": target_space, "effective_available_space_atr": 0.0, "space_consistency_delta_atr": None, "space_evidence_present": e5_present or bool(target.get("credible")), "space_conflict": False, "space_source": "NO_USABLE_SPACE_EVIDENCE", "minimum_required_atr": MIN_SPACE_ATR, "space_ok": False}
    values = [v for _, v in evidence]
    effective = min(values)
    delta = abs(e5_space - target_space) if len(values) == 2 else None
    conflict = delta is not None and delta >= SPACE_CONFLICT_ATR
    state = "CONFLICTED" if conflict else ("CONSTRAINED" if effective < MIN_SPACE_ATR else "USABLE")
    return {"state": state, "e5_available_space_atr": e5_space, "target_barrier_space_atr": target_space, "effective_available_space_atr": effective, "space_consistency_delta_atr": delta, "space_evidence_present": True, "space_conflict": conflict, "space_source": "MIN(E5_LOCATION,TARGET_BARRIER)" if len(values) == 2 else evidence[0][0], "minimum_required_atr": MIN_SPACE_ATR, "space_ok": state == "USABLE"}


def _volatility(bars: list[dict[str, Any]], atr: float) -> dict[str, Any]:
    series = _atr_series(bars)
    if atr <= 0 or len(series) < 2:
        return {"state": "INVALID", "last_range_atr": 0.0, "expansion_ratio": 0.0, "atr_stability": "INVALID", "atr_drift": 0.0}
    last_range = max(0.0, _num(bars[-1].get("high")) - _num(bars[-1].get("low")))
    prev_range = max(0.0, _num(bars[-2].get("high")) - _num(bars[-2].get("low")))
    last_range_atr = last_range / atr
    expansion_ratio = last_range / max(prev_range, 1e-9)
    recent = mean(series[-5:]) if len(series) >= 5 else mean(series)
    baseline = mean(series[-min(len(series), ATR_PERIOD):])
    drift = recent / max(baseline, 1e-9)
    atr_stability = "STABLE" if 0.65 <= drift <= 1.50 else "UNSTABLE"
    if last_range_atr >= MAX_LAST_RANGE_ATR: state = "EXPANSION_EXTREME"
    elif last_range_atr >= MODERATE_EXPANSION_ATR or expansion_ratio >= 2.0: state = "EXPANSION"
    elif last_range_atr <= 0.60: state = "COMPRESSION"
    else: state = "NORMAL"
    return {"state": state, "last_range_atr": last_range_atr, "expansion_ratio": expansion_ratio, "atr_stability": atr_stability, "atr_drift": drift}


def _stop_stability(risk: float, atr: float, bars: list[dict[str, Any]]) -> dict[str, Any]:
    series = _atr_series(bars)
    current = risk / max(atr, 1e-9)
    prior = series[-6:-1] if len(series) >= 6 else series[:-1]
    if not prior:
        return {"state": "UNAVAILABLE", "current_stop_atr": current, "prior_atr_median": None, "prior_normalized_stop_atr": None, "ratio_to_prior": None}
    reference = median(prior)
    prior_normalized = risk / max(reference, 1e-9)
    ratio = current / max(prior_normalized, 1e-9)
    state = "STABLE" if STOP_STABILITY_MIN_RATIO <= ratio <= STOP_STABILITY_MAX_RATIO else "UNSTABLE"
    return {"state": state, "current_stop_atr": current, "prior_atr_median": reference, "prior_normalized_stop_atr": prior_normalized, "ratio_to_prior": ratio}


def _execution(snapshot: dict[str, Any], atr: float) -> dict[str, Any]:
    spread = _first_num(snapshot, ("spread", "spread_price", "current_spread")) or 0.0
    slippage = _first_num(snapshot, ("slippage", "slippage_price", "expected_slippage")) or 0.0
    total = spread + slippage
    return {"spread": spread, "slippage": slippage, "total_cost": total, "cost_atr": total / atr if atr > 0 else float("inf")}


def _liquidity(e4: dict[str, Any]) -> dict[str, Any]:
    return {"liquidity_quality": _first_num(e4, ("liquidity_quality",)) or 0.0, "auction_quality": _first_num(e4, ("auction_quality",)) or 0.0, "proximity": _text(e4.get("liquidity_proximity")), "externality": _text(e4.get("liquidity_externality")), "auction_state": _text(e4.get("auction_state")), "information": _text(e4.get("auction_information"))}


def _structural_stop(direction: str, entry: float, atr: float, levels: dict[str, Any]) -> dict[str, Any]:
    if direction == "BUY":
        candidates = [("PROTECTED_LOW", levels.get("protected_low"), 1.0), ("STRUCTURE_LOW_20", levels.get("structure_low_20"), 0.8)]
        candidates = [(s, v, q) for s, v, q in candidates if v is not None and v < entry]
        if not candidates:
            return {"source": None, "level": None, "stop": entry - FALLBACK_STOP_ATR * atr, "basis": "ATR_FALLBACK_LOWER_CONFIDENCE", "quality": 0.0, "distance_atr": FALLBACK_STOP_ATR}
        source, level, quality = min(candidates, key=lambda x: abs(entry - x[1]))
        stop = level - RISK_ATR_BUFFER * atr
    elif direction == "SELL":
        candidates = [("PROTECTED_HIGH", levels.get("protected_high"), 1.0), ("STRUCTURE_HIGH_20", levels.get("structure_high_20"), 0.8)]
        candidates = [(s, v, q) for s, v, q in candidates if v is not None and v > entry]
        if not candidates:
            return {"source": None, "level": None, "stop": entry + FALLBACK_STOP_ATR * atr, "basis": "ATR_FALLBACK_LOWER_CONFIDENCE", "quality": 0.0, "distance_atr": FALLBACK_STOP_ATR}
        source, level, quality = min(candidates, key=lambda x: abs(entry - x[1]))
        stop = level + RISK_ATR_BUFFER * atr
    else:
        return {"source": None, "level": None, "stop": None, "basis": "NO_DIRECTION", "quality": 0.0, "distance_atr": 0.0}
    return {"source": source, "level": level, "stop": stop, "basis": "STRUCTURAL_LEVEL_PLUS_ATR_BUFFER", "quality": quality * 100.0, "distance_atr": abs(entry - stop) / max(atr, 1e-9)}


def _adverse_excursion(bars: list[dict[str, Any]], entry: float, direction: str, atr: float, stop_distance: float) -> dict[str, Any]:
    window = bars[-min(len(bars), 12):]
    if not window or atr <= 0:
        return {"state": "UNAVAILABLE", "max_adverse_excursion_atr": 0.0, "median_adverse_excursion_atr": 0.0, "survival_margin_atr": 0.0}
    adverse: list[float] = []
    for bar in window:
        if direction == "BUY": adverse.append(max(0.0, entry - _num(bar.get("low"))) / atr)
        elif direction == "SELL": adverse.append(max(0.0, _num(bar.get("high")) - entry) / atr)
    adverse = [x for x in adverse if x >= 0]
    max_ae = max(adverse) if adverse else 0.0
    med_ae = median(adverse) if adverse else 0.0
    survival = stop_distance / max(atr, 1e-9) - max_ae
    state = "ROBUST" if survival >= MIN_SURVIVAL_MARGIN_ATR else "FRAGILE" if survival >= 0 else "NON_SURVIVABLE"
    return {"state": state, "max_adverse_excursion_atr": max_ae, "median_adverse_excursion_atr": med_ae, "survival_margin_atr": survival, "window_bars": len(window)}


def _probability(e3: dict[str, Any], e4: dict[str, Any], e5: dict[str, Any], e6: dict[str, Any], e7: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    sources = [("E6", e6), ("E7", e7), ("E5", e5), ("E4", e4), ("E3", e3), ("SNAPSHOT", snapshot)]
    keys = ("historical_probability", "win_probability", "success_probability", "trade_probability", "probability", "estimated_probability")
    for source, mapping in sources:
        for key in keys:
            if key in mapping:
                raw = _num(mapping.get(key), -1.0)
                if 0.0 <= raw <= 1.0:
                    return {"state": "AVAILABLE", "value": raw, "percent": raw * 100.0, "source": f"{source}.{key}"}
                if 1.0 < raw <= 100.0:
                    return {"state": "AVAILABLE", "value": raw / 100.0, "percent": raw, "source": f"{source}.{key}"}
    return {"state": "UNAVAILABLE", "value": None, "percent": None, "source": None}


def _economics(real_rr: float, risk_distance: float, reward_distance: float, execution_cost: float, probability: dict[str, Any]) -> dict[str, Any]:
    gross_reward_r = reward_distance / max(risk_distance, 1e-9) if risk_distance > 0 else 0.0
    cost_r = execution_cost / max(risk_distance, 1e-9) if risk_distance > 0 else 0.0
    net_reward_r = max(0.0, gross_reward_r - cost_r)
    p = probability.get("value")
    if p is None:
        return {"state": "STRUCTURAL_ONLY", "probability": None, "gross_reward_r": gross_reward_r, "execution_cost_r": cost_r, "net_reward_r": net_reward_r, "expected_value_r": None, "edge": None, "edge_class": "PROBABILITY_UNAVAILABLE"}
    ev = p * net_reward_r - (1.0 - p)
    edge = ev
    if edge >= MIN_ECONOMIC_EDGE: cls = "POSITIVE_EXPECTANCY"
    elif edge >= 0.0: cls = "MARGINAL_EXPECTANCY"
    else: cls = "NEGATIVE_EXPECTANCY"
    return {"state": "QUANTIFIED", "probability": p, "gross_reward_r": gross_reward_r, "execution_cost_r": cost_r, "net_reward_r": net_reward_r, "expected_value_r": ev, "edge": edge, "edge_class": cls}


def analyze_e8(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """E8 is the independent trade-economics and survivability gate; E9 retains final authority."""
    bars = list(snapshot.get("bars") or [])
    e3, e4, e5, e6, e7 = (_evidence(upstream.get(k)) for k in ("E3", "E4", "E5", "E6", "E7"))
    base = {"architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION, "reasoning_role": "TRADE_ECONOMICS_RISK_ANALYST", "decision_authority": "E9", "trade_decision_authority": False, "closed_candle_only": True, "lookahead": False}
    if len(bars) < MIN_BARS:
        observations = [f"closed_candles={len(bars)} minimum_required={MIN_BARS}", "risk_lifecycle=UNRESOLVED", "economic_lifecycle=UNRESOLVED", "risk_gate=RISK_NOT_READY", "missing_evidence=SUFFICIENT_CLOSED_CANDLE_DATA"]
        return EngineResult("E8", NAME, False, 0.0, {**base, "state": "UNRESOLVED", "economic_state": "UNRESOLVED", "risk_lifecycle": "UNRESOLVED", "economic_lifecycle": "UNRESOLVED", "risk_gate": "RISK_NOT_READY", "trade_plan": {}, "observations": observations, "supporting_evidence": observations, "counter_evidence": ["INSUFFICIENT_CLOSED_CANDLE_DATA"], "missing_evidence": ["SUFFICIENT_CLOSED_CANDLE_DATA"], "gate_matrix": {}}, ("INSUFFICIENT_DATA",))

    direction, setup = _direction(e6), _setup(e6)
    confirmation, confirmation_trace = _confirmation(e7)
    entry, atr = _num(bars[-1].get("close")), _atr(bars)
    vol, execution, liq = _volatility(bars, atr), _execution(snapshot, atr), _liquidity(e4)
    support: list[str] = []
    counter: list[str] = []
    missing: list[str] = []
    data_valid = entry > 0 and atr > 0
    if not data_valid: counter.append("RISK_DATA_INVALID")
    if direction not in {"BUY", "SELL"}: counter.append("NO_VALID_DIRECTION")
    if setup.upper() in {"UNKNOWN", "NONE", "UNRESOLVED"}: missing.append("VALID_SETUP_THESIS")
    if confirmation != "CONFIRMED": missing.append("ENTRY_CONFIRMATION")

    levels = _levels(e3, e4, e5, bars) if data_valid and direction in {"BUY", "SELL"} else {}
    target = _dynamic_target(levels, direction, entry, atr, e4) if levels else {"source": None, "level": None, "distance": 0.0, "distance_atr": 0.0, "quality": 0.0, "credible": False, "rejection": ["NO_TARGET_INPUTS"], "candidate_trace": [], "selection_rule": "HIERARCHY_THEN_NEAREST_CREDIBLE_BARRIER"}
    stop_model = _structural_stop(direction, entry, atr, levels) if levels else {"source": None, "level": None, "stop": None, "basis": "NO_RISK_MODEL", "quality": 0.0, "distance_atr": 0.0}
    stop, structural_level, structural_source = stop_model.get("stop"), stop_model.get("level"), stop_model.get("source")
    structural_breach = bool(structural_level is not None and ((direction == "BUY" and entry <= structural_level) or (direction == "SELL" and entry >= structural_level)))
    if structural_breach: counter.append("STRUCTURAL_INVALIDATION_BREACHED")

    plan: dict[str, Any] = {}
    space = {"state": "UNAVAILABLE", "effective_available_space_atr": 0.0, "e5_available_space_atr": 0.0, "target_barrier_space_atr": 0.0, "space_consistency_delta_atr": None, "space_source": "UNAVAILABLE", "space_ok": False, "space_conflict": False}
    stop_stability = {"state": "UNAVAILABLE", "current_stop_atr": 0.0, "ratio_to_prior": None}
    survival = {"state": "UNAVAILABLE", "max_adverse_excursion_atr": 0.0, "median_adverse_excursion_atr": 0.0, "survival_margin_atr": 0.0}
    risk_distance = reward_distance = real_rr = 0.0
    target_level = None
    liquidity_r = 0.0
    opposing = False

    if data_valid and direction in {"BUY", "SELL"}:
        risk_distance = abs(entry - stop) if stop is not None else 0.0
        stop_atr = risk_distance / max(atr, 1e-9)
        stop_stability = _stop_stability(risk_distance, atr, bars)
        survival = _adverse_excursion(bars, entry, direction, atr, risk_distance)
        space = _space(e5, target, direction)
        target_level = target.get("level")
        reward_distance = abs(target_level - entry) if target_level is not None else 0.0
        real_rr = reward_distance / max(risk_distance, 1e-9) if target_level is not None and risk_distance > 0 else 0.0
        liquidity_level = levels.get("liquidity_event_level")
        opposing = liquidity_level is not None and target_level is not None and min(entry, target_level) < liquidity_level < max(entry, target_level)
        liquidity_r = abs(liquidity_level - entry) / max(risk_distance, 1e-9) if opposing and risk_distance > 0 else 0.0
        if structural_level is None: counter.append("STRUCTURAL_STOP_UNAVAILABLE")
        if stop_model.get("source") is None: counter.append("STOP_LOSS_FALLBACK_LOWER_CONFIDENCE")
        if target_level is None: missing.append("NO_USABLE_STRUCTURAL_TARGET")
        if stop_atr < MIN_STOP_ATR: counter.append("STOP_TOO_TIGHT_FOR_VOLATILITY")
        if stop_atr > MAX_STOP_ATR: counter.append("STOP_TOO_WIDE_FOR_ECONOMICS")
        if stop_stability["state"] == "UNSTABLE": counter.append("STOP_GEOMETRY_UNSTABLE")
        if survival["state"] == "NON_SURVIVABLE": counter.append("STOP_NOT_SURVIVABLE")
        elif survival["state"] == "FRAGILE": counter.append("STOP_SURVIVAL_MARGIN_THIN")
        if target_level is not None and real_rr < MIN_RR: counter.append("REAL_RR_BELOW_MINIMUM")
        if not target.get("credible"): counter.append("DYNAMIC_TARGET_NOT_USABLE")
        if target.get("distance_atr", 0.0) > MAX_TARGET_EXTENSION_ATR: counter.append("TARGET_TOO_FAR_FOR_M5_EXECUTION")
        if not space["space_ok"]: counter.append("EFFECTIVE_SPACE_BELOW_MINIMUM")
        if space["space_conflict"]: counter.append("SPACE_EVIDENCE_CONFLICT")
        if opposing:
            counter.append("OPPOSING_LIQUIDITY_ON_TARGET_PATH")
            if liq["externality"] == "EXTERNAL": counter.append("EXTERNAL_LIQUIDITY_PATH_RISK")
            if liquidity_r <= MAX_LIQUIDITY_RISK_R: counter.append("OPPOSING_LIQUIDITY_PATH_RISK")
            if liq["auction_state"] == "PENDING": counter.append("LIQUIDITY_AUCTION_NOT_TERMINALLY_CONFIRMED")
            if liq["information"] == "LOW_INFORMATION": counter.append("LOW_INFORMATION_LIQUIDITY_RISK")
        tp1 = entry + reward_distance * TP1_FRACTION if direction == "BUY" else entry - reward_distance * TP1_FRACTION
        plan = {"valid": True, "entry": entry, "direction": direction, "stop_loss": stop, "structural_stop": structural_level, "invalidation_basis": stop_model.get("basis"), "invalidation_source": structural_source, "stop_validity": "STRUCTURAL" if structural_source else "FALLBACK_LOWER_CONFIDENCE", "stop_quality": stop_model.get("quality", 0.0), "take_profit_1": tp1, "take_profit_2": target_level, "target_source": target.get("source"), "target_quality": target.get("quality", 0.0), "target_distance_atr": target.get("distance_atr", 0.0), "target_candidate_trace": target.get("candidate_trace", []), "target_rejection": target.get("rejection", []), "risk_distance": risk_distance, "risk_distance_atr": stop_atr, "reward_distance": reward_distance, "reward_distance_atr": reward_distance / max(atr, 1e-9) if reward_distance else 0.0, "available_space": reward_distance, "available_space_atr": space["effective_available_space_atr"], "e5_available_space_atr": space["e5_available_space_atr"], "target_barrier_space_atr": space["target_barrier_space_atr"], "space_consistency_delta_atr": space["space_consistency_delta_atr"], "space_source": space["space_source"], "space_state": space["state"], "real_rr": real_rr, "effective_rr": real_rr - (execution["total_cost"] / max(risk_distance, 1e-9) if risk_distance else 0.0), "rr_tp1": reward_distance * TP1_FRACTION / max(risk_distance, 1e-9) if risk_distance else 0.0, "rr_tp2": real_rr, "min_required_rr": MIN_RR, "asymmetric_payoff": real_rr >= MIN_RR, "stop_distance_atr": stop_atr, "stop_stability": stop_stability["state"], "survival_state": survival["state"], "max_adverse_excursion_atr": survival["max_adverse_excursion_atr"], "survival_margin_atr": survival["survival_margin_atr"], "risk_buffer_atr": RISK_ATR_BUFFER, "structural_breach": structural_breach, "opposing_liquidity": liquidity_level if opposing else None, "opposing_liquidity_r": liquidity_r}
        support.extend([f"entry={entry:.6f}", f"atr={atr:.6f}", f"structural_stop={structural_level:.6f}" if structural_level is not None else "structural_stop=NONE", f"final_stop={stop:.6f}" if stop is not None else "final_stop=NONE", f"risk_distance={risk_distance:.6f}", f"risk_distance_atr={stop_atr:.3f}", f"stop_validity={plan['stop_validity']}", f"target={target_level:.6f}" if target_level is not None else "target=NONE", f"target_source={target.get('source') or 'NONE'}", f"target_quality={target.get('quality', 0.0):.1f}", f"reward_distance={reward_distance:.6f}", f"reward_distance_atr={plan['reward_distance_atr']:.3f}", f"effective_space_atr={space['effective_available_space_atr']:.3f}", f"real_rr={real_rr:.3f}", f"effective_rr={plan['effective_rr']:.3f}", f"stop_stability={stop_stability['state']}", f"survival={survival['state']}", f"max_ae_atr={survival['max_adverse_excursion_atr']:.3f}", f"survival_margin_atr={survival['survival_margin_atr']:.3f}"])
    else:
        counter.append("RISK_MODEL_UNAVAILABLE")

    if vol["state"] == "EXPANSION_EXTREME": counter.append("VOLATILITY_RISK_HIGH")
    elif vol["state"] == "EXPANSION": counter.append("VOLATILITY_EXPANSION_RISK")
    if vol["atr_stability"] == "UNSTABLE": counter.append("ATR_STABILITY_RISK")
    if execution["cost_atr"] > MAX_EXECUTION_COST_ATR: counter.append("EXECUTION_COST_TOO_HIGH")
    if vol["state"] == "COMPRESSION" and plan.get("target_distance_atr", 0.0) >= 2.5: counter.append("COMPRESSION_TARGET_REALIZATION_RISK")

    probability = _probability(e3, e4, e5, e6, e7, snapshot)
    econ = _economics(real_rr, risk_distance, reward_distance, execution["total_cost"], probability)
    if econ["edge_class"] == "NEGATIVE_EXPECTANCY": counter.append("NEGATIVE_EXPECTANCY")

    critical = {"RISK_DATA_INVALID", "NO_VALID_DIRECTION", "STRUCTURAL_INVALIDATION_BREACHED", "STOP_TOO_TIGHT_FOR_VOLATILITY", "STOP_TOO_WIDE_FOR_ECONOMICS", "STOP_GEOMETRY_UNSTABLE", "STOP_NOT_SURVIVABLE", "NO_USABLE_STRUCTURAL_TARGET", "EFFECTIVE_SPACE_BELOW_MINIMUM", "REAL_RR_BELOW_MINIMUM", "OPPOSING_LIQUIDITY_PATH_RISK", "EXTERNAL_LIQUIDITY_PATH_RISK", "LIQUIDITY_AUCTION_NOT_TERMINALLY_CONFIRMED", "LOW_INFORMATION_LIQUIDITY_RISK", "VOLATILITY_RISK_HIGH", "ATR_STABILITY_RISK", "EXECUTION_COST_TOO_HIGH", "DYNAMIC_TARGET_NOT_USABLE", "TARGET_TOO_FAR_FOR_M5_EXECUTION", "SPACE_EVIDENCE_CONFLICT", "COMPRESSION_TARGET_REALIZATION_RISK", "NEGATIVE_EXPECTANCY"}
    counter, missing = list(dict.fromkeys(counter)), list(dict.fromkeys(missing))
    gate_data = data_valid
    gate_direction = direction in {"BUY", "SELL"}
    gate_setup = setup.upper() not in {"UNKNOWN", "NONE", "UNRESOLVED"}
    gate_confirmation = confirmation == "CONFIRMED"
    gate_invalidation = not structural_breach
    gate_stop = bool(plan) and MIN_STOP_ATR <= plan.get("stop_distance_atr", 99.0) <= MAX_STOP_ATR and stop_stability["state"] == "STABLE" and survival["state"] in {"ROBUST", "FRAGILE"}
    gate_target = bool(target.get("credible")) and target.get("distance_atr", 0.0) <= MAX_TARGET_EXTENSION_ATR
    gate_space = space.get("space_ok", False)
    gate_rr = bool(plan) and plan.get("effective_rr", 0.0) >= MIN_RR
    gate_execution = vol["state"] not in {"EXPANSION_EXTREME", "INVALID"} and vol["atr_stability"] == "STABLE" and execution["cost_atr"] <= MAX_EXECUTION_COST_ATR
    gate_probability = probability["state"] == "AVAILABLE"
    gate_expected_value = econ["state"] != "QUANTIFIED" or _num(econ.get("expected_value_r"), -999.0) >= MIN_ECONOMIC_EDGE
    gate_economics = gate_target and gate_space and gate_rr and gate_stop and gate_invalidation and gate_execution and gate_expected_value and not any(x in critical for x in counter) and not missing

    lifecycle = {
        "01_DATA_INTEGRITY": "PASS" if gate_data else "FAIL",
        "02_DIRECTION": "PASS" if gate_direction else "FAIL",
        "03_SETUP_CONFIRMATION": "PASS" if gate_setup and gate_confirmation else "FAIL",
        "04_STRUCTURAL_INVALIDATION": "PASS" if gate_invalidation else "FAIL",
        "05_STOP_VALIDITY": "PASS" if structural_source is not None else "CONDITIONAL",
        "06_STOP_SURVIVABILITY": "PASS" if gate_stop else "FAIL",
        "07_TARGET_HIERARCHY": "PASS" if gate_target else "FAIL",
        "08_SPACE_VALIDATION": "PASS" if gate_space else "FAIL",
        "09_EFFECTIVE_RR": "PASS" if gate_rr else "FAIL",
        "10_EXECUTION_VOLATILITY": "PASS" if gate_execution else "FAIL",
        "11_EXPECTED_VALUE": "PASS" if gate_expected_value else "FAIL",
        "12_ECONOMICS": "PASS" if gate_economics else "FAIL",
        "13_RISK_GATE": "RISK_READY" if gate_economics else "RISK_NOT_READY",
    }
    hard_failure = any(x in critical for x in counter) or bool(missing)
    state = "ATTRACTIVE" if gate_economics else "CONDITIONAL" if plan and not hard_failure else "UNATTRACTIVE" if plan else "UNRESOLVED"
    risk_ready = gate_economics
    score = 95.0 if risk_ready else 65.0 if state == "CONDITIONAL" else 30.0 if state == "UNATTRACTIVE" else 15.0

    observations = [f"direction={direction}", f"setup={setup}", f"confirmation={confirmation}", f"entry={entry:.6f}", f"atr={atr:.6f}", f"stop={stop:.6f}" if stop is not None else "stop=NONE", f"stop_validity={plan.get('stop_validity', 'NONE')}", f"risk_distance_atr={plan.get('risk_distance_atr', 0.0):.3f}", f"target={target_level:.6f}" if target_level is not None else "target=NONE", f"target_source={target.get('source') or 'NONE'}", f"target_quality={target.get('quality', 0.0):.1f}", f"target_hierarchy_rank={target.get('hierarchy_rank', 'NONE')}", f"reward_distance_atr={plan.get('reward_distance_atr', 0.0):.3f}", f"effective_space_atr={space.get('effective_available_space_atr', 0.0):.3f}", f"real_rr={real_rr:.3f}", f"effective_rr={plan.get('effective_rr', 0.0):.3f}", f"max_adverse_excursion_atr={survival.get('max_adverse_excursion_atr', 0.0):.3f}", f"survival_margin_atr={survival.get('survival_margin_atr', 0.0):.3f}", f"survival_state={survival.get('state')}", f"probability={probability.get('percent') if probability.get('percent') is not None else 'UNAVAILABLE'}", f"probability_source={probability.get('source') or 'NONE'}", f"expected_value_r={econ.get('expected_value_r') if econ.get('expected_value_r') is not None else 'UNAVAILABLE'}", f"economic_edge={econ.get('edge_class')}", f"risk_lifecycle={lifecycle['13_RISK_GATE']}", f"economic_lifecycle={state}"]
    if counter: observations.append("vetoes=" + ",".join(counter))
    if missing: observations.append("missing=" + ",".join(missing))
    reasons = tuple(counter + missing + ([] if risk_ready else ["ECONOMICS_NOT_READY"]))

    output = {
        **base,
        "state": state,
        "economic_state": state,
        "risk_lifecycle": lifecycle["13_RISK_GATE"],
        "economic_lifecycle": state,
        "risk_gate": "RISK_READY" if risk_ready else "RISK_NOT_READY",
        "direction": direction,
        "setup": setup,
        "confirmation": confirmation,
        "confirmation_trace": confirmation_trace,
        "trade_plan": plan,
        "risk_model": {"atr": atr, "atr_period": ATR_PERIOD, "volatility_state": vol["state"], "last_range_atr": vol["last_range_atr"], "expansion_ratio": vol["expansion_ratio"], "atr_stability": vol["atr_stability"], "atr_drift": vol["atr_drift"], "stop_stability": stop_stability, "survival": survival, "spread": execution["spread"], "slippage": execution["slippage"], "execution_cost_atr": execution["cost_atr"], "structure_lookback": STRUCTURE_LOOKBACK, "min_stop_atr": MIN_STOP_ATR, "max_stop_atr": MAX_STOP_ATR, "min_space_atr": MIN_SPACE_ATR, "min_rr": MIN_RR, "risk_buffer_atr": RISK_ATR_BUFFER, "max_liquidity_risk_r": MAX_LIQUIDITY_RISK_R, "max_execution_cost_atr": MAX_EXECUTION_COST_ATR},
        "structural_evidence": {**levels, "structural_breach": structural_breach, "invalidation_source": structural_source, "stop_model": stop_model},
        "liquidity_evidence": liq,
        "location_evidence": {"e5_available_space_atr_long": _num(e5.get("available_space_atr_long")), "e5_available_space_atr_short": _num(e5.get("available_space_atr_short")), "effective_available_space_atr": space.get("effective_available_space_atr", 0.0), "target_barrier_space_atr": space.get("target_barrier_space_atr", 0.0), "space_consistency_delta_atr": space.get("space_consistency_delta_atr"), "space_source": space.get("space_source"), "space_state": space.get("state"), "space_ok": space.get("space_ok", False), "space_conflict": space.get("space_conflict", False)},
        "dynamic_target": target,
        "probability_evidence": probability,
        "trade_economics": econ,
        "lifecycle": lifecycle,
        "gate_matrix": {"8A_data_integrity": "PASS" if gate_data else "FAIL", "8B_direction_validation": "PASS" if gate_direction else "FAIL", "8C_setup_confirmation_gate": "PASS" if gate_setup and gate_confirmation else "FAIL", "8D_structural_invalidation": "PASS" if gate_invalidation else "FAIL", "8E_stop_validity": "PASS" if structural_source else "CONDITIONAL", "8F_stop_survivability": "PASS" if gate_stop else "FAIL", "8G_target_hierarchy": "PASS" if gate_target else "FAIL", "8H_available_space": "PASS" if gate_space else "FAIL", "8I_effective_rr": "PASS" if gate_rr else "FAIL", "8J_volatility_execution": "PASS" if gate_execution else "FAIL", "8K_expected_value": "PASS" if gate_expected_value else "FAIL", "8L_trade_economics": state, "8M_final_risk_gate": "RISK_READY" if risk_ready else "RISK_NOT_READY"},
        "supporting_evidence": support,
        "counter_evidence": counter,
        "missing_evidence": missing,
        "observations": observations,
        "invalidation": ["closed-candle structural invalidation", "structural stop becomes economically excessive", "stop geometry becomes unstable versus recent ATR regime", "recent adverse excursion consumes the survival margin", "effective available space collapses below minimum", "space evidence materially conflicts", "effective RR falls below minimum", "opposing or external liquidity blocks the target path", "volatility makes the stop non-survivable", "execution cost becomes excessive", "entry confirmation is not proven", "target barrier is not credible or is too far for M5 execution", "quantified expected value becomes negative"],
        "professional_reasoning": {
            "entry_stop_target_chain": f"ENTRY={entry:.6f} -> INVALIDATION={structural_level if structural_level is not None else 'NONE'} -> STOP={stop if stop is not None else 'NONE'} -> TARGET={target_level if target_level is not None else 'NONE'} -> REWARD={reward_distance:.6f} -> RR={real_rr:.3f} -> EFFECTIVE_RR={plan.get('effective_rr', 0.0):.3f}",
            "structural_stop_reasoning": f"source={structural_source or 'NONE'}; quality={stop_model.get('quality', 0.0):.1f}; basis={stop_model.get('basis')}",
            "target_hierarchy_reasoning": f"selected={target.get('source') or 'NONE'} rank={target.get('hierarchy_rank', 'NONE')} quality={target.get('quality', 0.0):.1f}; hierarchy is structural first, distance second; farther targets cannot manufacture RR",
            "space_reasoning": f"effective={space.get('effective_available_space_atr', 0.0):.3f} ATR minimum={MIN_SPACE_ATR:.2f} ATR source={space.get('space_source')}",
            "stop_survivability": f"state={survival.get('state')}; max_adverse_excursion={survival.get('max_adverse_excursion_atr', 0.0):.3f} ATR; survival_margin={survival.get('survival_margin_atr', 0.0):.3f} ATR; stop={plan.get('risk_distance_atr', 0.0):.3f} ATR",
            "rr_reasoning": f"gross_reward={reward_distance:.6f} / risk={risk_distance:.6f} = {real_rr:.3f}; execution_cost_r={econ.get('execution_cost_r', 0.0):.3f}; effective_rr={plan.get('effective_rr', 0.0):.3f}; required={MIN_RR:.2f}",
            "probability_reasoning": f"state={probability.get('state')}; value={probability.get('percent') if probability.get('percent') is not None else 'UNAVAILABLE'}%; source={probability.get('source') or 'NONE'}; E8 never fabricates probability",
            "expected_value_reasoning": f"state={econ.get('state')}; expected_value_r={econ.get('expected_value_r') if econ.get('expected_value_r') is not None else 'UNAVAILABLE'}; edge={econ.get('edge_class')}",
            "economic_veto": "PASS" if risk_ready else "VETO: " + "; ".join(counter + missing + ["ECONOMICS_NOT_READY"]),
            "lifecycle": lifecycle,
            "8E_stop_validity": "Structural invalidation must be meaningful before ATR buffering; fallback is explicitly lower confidence.",
            "8F_stop_survivability": f"state={survival.get('state')}; stop_stability={stop_stability['state']}; current_stop_atr={stop_stability.get('current_stop_atr', 0.0):.3f}",
            "8G_target_hierarchy": f"selected={target.get('level', 'NONE')} source={target.get('source', 'NONE')} rank={target.get('hierarchy_rank', 'NONE')} quality={target.get('quality', 0.0):.1f}",
            "8I_effective_rr": f"real_rr={real_rr:.3f}; effective_rr={plan.get('effective_rr', 0.0):.3f}; execution_cost_atr={execution['cost_atr']:.3f}",
            "8K_expected_value": f"probability={probability.get('percent') if probability.get('percent') is not None else 'UNAVAILABLE'}%; EV_R={econ.get('expected_value_r') if econ.get('expected_value_r') is not None else 'UNAVAILABLE'}; class={econ.get('edge_class')}",
            "8M_final_risk_gate": "RISK_READY" if risk_ready else "RISK_NOT_READY",
        },
        "decision_path": "E8 validates structural risk, target hierarchy, survivability and trade economics only; E9 retains final trade authority.",
    }
    return EngineResult("E8", NAME, risk_ready, score, output, reasons)
