from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Trade Economics & Risk Brain"
QUESTION = "Is the proposed trade economically attractive and structurally survivable?"
ARCHITECTURE = "E8_PROFESSIONAL_TRADE_ECONOMICS_RISK_BRAIN_V6"
VERSION = "6.0"
MIN_BARS = 30
MIN_RR = 1.50
ATR_PERIOD = 14
RISK_ATR_BUFFER = 0.20
FALLBACK_STOP_ATR = 1.20
STRUCTURE_LOOKBACK = 20
MIN_STOP_ATR = 0.50
MAX_STOP_ATR = 3.50
MIN_SPACE_ATR = 0.75
TP1_FRACTION = 0.50
MAX_LIQUIDITY_RISK_R = 1.00
MAX_EXECUTION_COST_ATR = 0.15
MAX_LAST_RANGE_ATR = 2.50
MIN_TARGET_CLEARANCE_ATR = 0.10
MAX_TARGET_EXTENSION_ATR = 3.50
MODERATE_EXPANSION_ATR = 1.75


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
        if key in mapping:
            try:
                value = float(mapping[key])
                if value == value and value > 0:
                    return value
            except (TypeError, ValueError):
                pass
    return None


def _direction(e6: dict[str, Any]) -> str:
    t = _text(e6.get("direction", e6.get("direction_thesis")))
    if t in {"BUY", "BULLISH", "UP", "LONG", "BUYERS", "TREND_UP"}:
        return "BUY"
    if t in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS", "TREND_DOWN"}:
        return "SELL"
    return "NEUTRAL"


def _setup(e6: dict[str, Any]) -> str:
    for key in ("setup", "setup_family", "setup_type", "thesis_setup"):
        value = e6.get(key)
        if value not in (None, ""):
            return str(value)
    parts = str(e6.get("finding") or "").split()
    if len(parts) >= 2 and _text(parts[0]) in {"BUY", "SELL"}:
        return parts[1]
    return "UNKNOWN"


def _confirmation(e7: dict[str, Any]) -> tuple[str, list[str]]:
    observed: list[str] = []
    for key in ("confirmation", "confirmation_state", "trigger_state", "proof_state"):
        value = e7.get(key)
        if value not in (None, ""):
            observed.append(_text(value))
    lifecycle = e7.get("confirmation_lifecycle")
    if isinstance(lifecycle, dict):
        for key in ("confirmation", "state", "trigger", "follow_through", "invalidation"):
            value = lifecycle.get(key)
            if value not in (None, ""):
                observed.append(_text(value))
    proof = e7.get("proof_gates")
    if isinstance(proof, dict):
        for key in ("confirmation", "closed_candle_confirmation", "follow_through"):
            value = proof.get(key)
            if value in (True, "PASS", "CONFIRMED", "PROVEN", "VALID", "VALIDATED"):
                observed.append("CONFIRMED")
            elif value in (False, "FAIL", "PENDING", "UNAVAILABLE", "NOT_PROVEN"):
                observed.append("NOT_CONFIRMED")
    for key in ("confirmed", "confirmation_proven", "closed_candle_confirmed"):
        if key in e7:
            observed.append("CONFIRMED" if bool(e7[key]) else "NOT_CONFIRMED")
    reasons = [_text(x) for x in (e7.get("reason_codes") or e7.get("reasons") or [])]
    if any(x in {"PROOF_GATES_INCOMPLETE", "VALID_CLOSED_CANDLE_TRIGGER_MISSING", "TRIGGER_OBSERVED_NOT_AUTOMATIC_CONFIRMATION", "LIQUIDITY_RECLAIM_LEVEL_REQUIRED"} for x in reasons):
        return "NOT_CONFIRMED", observed + reasons
    if any(x in {"CONFIRMATION_PROVEN", "CAUSAL_FOLLOW_THROUGH_PROVEN"} for x in reasons):
        return "CONFIRMED", observed + reasons
    if any(x in {"CONFIRMED", "PROVEN", "VALIDATED"} for x in observed):
        return "CONFIRMED", observed + reasons
    return "NOT_CONFIRMED", observed + reasons


def _atr(bars: list[dict[str, Any]], period: int = ATR_PERIOD) -> float:
    if len(bars) < 2:
        return 0.0
    trs: list[float] = []
    start = max(1, len(bars) - period)
    for i in range(start, len(bars)):
        h = _num(bars[i].get("high")); l = _num(bars[i].get("low")); pc = _num(bars[i - 1].get("close"))
        if h > 0 and l >= 0 and pc > 0:
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return mean(trs) if trs else 0.0


def _recent_structure(bars: list[dict[str, Any]]) -> dict[str, float | None]:
    recent = bars[-STRUCTURE_LOOKBACK:]
    highs = [_num(x.get("high")) for x in recent if _num(x.get("high")) > 0]
    lows = [_num(x.get("low")) for x in recent if _num(x.get("low")) > 0]
    return {"structure_high_20": max(highs) if highs else None, "structure_low_20": min(lows) if lows else None}


def _level_inputs(e3: dict[str, Any], e4: dict[str, Any], e5: dict[str, Any], bars: list[dict[str, Any]]) -> dict[str, Any]:
    recent = _recent_structure(bars)
    return {
        "protected_high": _first_num(e3, ("protected_high", "external_protected_high", "internal_protected_high")),
        "protected_low": _first_num(e3, ("protected_low", "external_protected_low", "internal_protected_low")),
        "next_resistance": _first_num(e5, ("next_resistance", "nearest_resistance", "resistance")),
        "next_support": _first_num(e5, ("next_support", "nearest_support", "support")),
        "liquidity_event_level": _first_num(e4, ("event_level", "liquidity_level", "nearest_liquidity", "opposing_liquidity_level")),
        "structure_high_20": recent["structure_high_20"],
        "structure_low_20": recent["structure_low_20"],
    }


def _directional_candidates(levels: dict[str, Any], direction: str, entry: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if direction == "BUY":
        targets = [
            ("RESISTANCE", levels.get("next_resistance"), 92.0),
            ("PROTECTED_HIGH", levels.get("protected_high"), 90.0),
            ("LIQUIDITY_EVENT", levels.get("liquidity_event_level"), 80.0),
            ("STRUCTURE_HIGH_20", levels.get("structure_high_20"), 65.0),
        ]
        invalidations = [("PROTECTED_LOW", levels.get("protected_low")), ("STRUCTURE_LOW_20", levels.get("structure_low_20"))]
        target_candidates = [{"source": n, "level": v, "quality": q} for n, v, q in targets if v is not None and v > entry]
        invalid_candidates = [{"source": n, "level": v} for n, v in invalidations if v is not None and v < entry]
    elif direction == "SELL":
        targets = [
            ("SUPPORT", levels.get("next_support"), 92.0),
            ("PROTECTED_LOW", levels.get("protected_low"), 90.0),
            ("LIQUIDITY_EVENT", levels.get("liquidity_event_level"), 80.0),
            ("STRUCTURE_LOW_20", levels.get("structure_low_20"), 65.0),
        ]
        invalidations = [("PROTECTED_HIGH", levels.get("protected_high")), ("STRUCTURE_HIGH_20", levels.get("structure_high_20"))]
        target_candidates = [{"source": n, "level": v, "quality": q} for n, v, q in targets if v is not None and v < entry]
        invalid_candidates = [{"source": n, "level": v} for n, v in invalidations if v is not None and v > entry]
    else:
        return [], []
    target_candidates.sort(key=lambda x: x["level"] if direction == "BUY" else -x["level"])
    invalid_candidates.sort(key=lambda x: x["level"], reverse=direction == "BUY")
    return target_candidates, invalid_candidates


def _dynamic_target(levels: dict[str, Any], direction: str, entry: float, atr: float, e4: dict[str, Any]) -> dict[str, Any]:
    candidates, _ = _directional_candidates(levels, direction, entry)
    for candidate in candidates:
        distance_atr = abs(candidate["level"] - entry) / max(atr, 1e-9)
        if distance_atr < MIN_TARGET_CLEARANCE_ATR:
            continue
        quality = candidate["quality"]
        if candidate["source"] == "LIQUIDITY_EVENT":
            externality = _text(e4.get("liquidity_externality"))
            auction_state = _text(e4.get("auction_state"))
            information = _text(e4.get("auction_information"))
            if externality == "EXTERNAL": quality += 5.0
            if auction_state == "PENDING": quality -= 15.0
            if information == "LOW_INFORMATION": quality -= 10.0
        candidate["distance_atr"] = distance_atr
        candidate["quality"] = max(0.0, min(100.0, quality))
        if candidate["quality"] >= 70.0:
            candidate["credible"] = True
            return candidate
    return {"source": None, "level": None, "quality": 0.0, "distance_atr": 0.0, "credible": False}


def _volatility_state(bars: list[dict[str, Any]], atr: float) -> dict[str, Any]:
    if atr <= 0 or len(bars) < 2:
        return {"state": "INVALID", "last_range_atr": 0.0, "expansion_ratio": 0.0, "atr_stability": "INVALID", "atr_drift": 0.0}
    ranges = [max(0.0, _num(x.get("high")) - _num(x.get("low"))) for x in bars[-ATR_PERIOD:] if _num(x.get("high")) > 0]
    last_range = ranges[-1] if ranges else 0.0
    previous_range = ranges[-2] if len(ranges) >= 2 else 0.0
    ratio = last_range / atr
    expansion_ratio = last_range / max(previous_range, 1e-9)
    if ratio >= MAX_LAST_RANGE_ATR:
        state = "EXPANSION_EXTREME"
    elif ratio >= MODERATE_EXPANSION_ATR or expansion_ratio >= 2.0:
        state = "EXPANSION"
    elif ratio <= 0.60:
        state = "COMPRESSION"
    else:
        state = "NORMAL"
    short_atr = mean(ranges[-5:]) if len(ranges) >= 5 else mean(ranges) if ranges else 0.0
    atr_drift = short_atr / max(atr, 1e-9)
    med = mean(ranges) if ranges else 0.0
    atr_stability = "STABLE" if med > 0 and 0.50 <= atr / med <= 2.00 and 0.60 <= atr_drift <= 1.60 else "UNSTABLE"
    return {"state": state, "last_range_atr": ratio, "expansion_ratio": expansion_ratio, "atr_stability": atr_stability, "atr_drift": atr_drift}


def _execution_cost(snapshot: dict[str, Any], entry: float, atr: float) -> dict[str, Any]:
    spread = _first_num(snapshot, ("spread", "spread_price", "current_spread")) or 0.0
    slippage = _first_num(snapshot, ("slippage", "slippage_price", "expected_slippage")) or 0.0
    total = spread + slippage
    return {"spread": spread, "slippage": slippage, "total_cost": total, "cost_atr": total / atr if atr > 0 else float("inf"), "entry": entry}


def _e4_liquidity_quality(e4: dict[str, Any]) -> dict[str, Any]:
    return {
        "liquidity_quality": _first_num(e4, ("liquidity_quality",)) or 0.0,
        "auction_quality": _first_num(e4, ("auction_quality",)) or 0.0,
        "proximity": _text(e4.get("liquidity_proximity")),
        "externality": _text(e4.get("liquidity_externality")),
        "auction_state": _text(e4.get("auction_state")),
        "information": _text(e4.get("auction_information")),
    }


def _has_structural_breach(bars: list[dict[str, Any]], direction: str, structural: float | None) -> bool:
    if structural is None or not bars:
        return False
    close = _num(bars[-1].get("close"))
    return close <= structural if direction == "BUY" else close >= structural if direction == "SELL" else False


def analyze_e8(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """E8 validates trade survivability/economics; E9 remains the final trade authority."""
    bars = list(snapshot.get("bars") or [])
    e3, e4, e5, e6, e7 = (_evidence(upstream.get(k)) for k in ("E3", "E4", "E5", "E6", "E7"))
    base = {
        "architecture": ARCHITECTURE,
        "version": VERSION,
        "question": QUESTION,
        "reasoning_role": "TRADE_ECONOMICS_RISK_ANALYST",
        "decision_authority": "E9",
        "trade_decision_authority": False,
        "closed_candle_only": True,
        "lookahead": False,
    }
    if len(bars) < MIN_BARS:
        return EngineResult("E8", NAME, False, 0.0, {**base, "state": "UNRESOLVED", "economic_state": "UNRESOLVED", "risk_gate": "RISK_NOT_READY", "trade_plan": {}, "supporting_evidence": [], "counter_evidence": ["INSUFFICIENT_CLOSED_CANDLE_DATA"], "missing_evidence": ["SUFFICIENT_RISK_SAMPLE"]}, ("INSUFFICIENT_DATA",))

    direction, setup = _direction(e6), _setup(e6)
    confirmation, confirmation_trace = _confirmation(e7)
    entry, atr = _num(bars[-1].get("close")), _atr(bars)
    volatility = _volatility_state(bars, atr)
    execution = _execution_cost(snapshot, entry, atr)
    liquidity_quality = _e4_liquidity_quality(e4)
    support: list[str] = []
    counter: list[str] = []
    missing: list[str] = []
    plan: dict[str, Any] = {}

    data_valid = entry > 0 and atr > 0
    if not data_valid: counter.append("RISK_DATA_INVALID")
    if direction not in {"BUY", "SELL"}: counter.append("NO_VALID_DIRECTION")
    if setup.upper() in {"UNKNOWN", "NONE", "UNRESOLVED"}: missing.append("VALID_SETUP_THESIS")
    if confirmation != "CONFIRMED": missing.append("ENTRY_CONFIRMATION")

    levels = _level_inputs(e3, e4, e5, bars) if data_valid and direction in {"BUY", "SELL"} else {}
    candidates, invalidations = _directional_candidates(levels, direction, entry) if levels else ([], [])
    structural = invalidations[0]["level"] if invalidations else None
    structural_source = invalidations[0]["source"] if invalidations else None
    structural_breached = _has_structural_breach(bars, direction, structural)
    if structural_breached: counter.append("STRUCTURAL_INVALIDATION_BREACHED")

    target_meta = _dynamic_target(levels, direction, entry, atr, e4) if levels else {"source": None, "level": None, "quality": 0.0, "distance_atr": 0.0, "credible": False}
    target = target_meta.get("level")

    if data_valid and direction in {"BUY", "SELL"}:
        if direction == "BUY":
            structural_stop = structural if structural is not None and structural < entry else None
            stop = structural_stop - RISK_ATR_BUFFER * atr if structural_stop is not None else entry - FALLBACK_STOP_ATR * atr
        else:
            structural_stop = structural if structural is not None and structural > entry else None
            stop = structural_stop + RISK_ATR_BUFFER * atr if structural_stop is not None else entry + FALLBACK_STOP_ATR * atr
        risk = abs(entry - stop)
        stop_atr = risk / atr if atr > 0 else float("inf")
        if stop_atr < MIN_STOP_ATR: counter.append("STOP_TOO_TIGHT_FOR_VOLATILITY")
        if stop_atr > MAX_STOP_ATR: counter.append("STOP_TOO_WIDE_FOR_ECONOMICS")
        if target is None:
            counter.append("NO_USABLE_STRUCTURAL_TARGET")
        else:
            space = abs(target - entry)
            space_atr = space / atr if atr > 0 else 0.0
            if space_atr < MIN_SPACE_ATR: counter.append("AVAILABLE_SPACE_BELOW_MINIMUM")
            reward = space
            real_rr = reward / risk if risk > 0 else 0.0
            tp1 = entry + reward * TP1_FRACTION if direction == "BUY" else entry - reward * TP1_FRACTION
            plan = {
                "valid": True,
                "entry": entry,
                "direction": direction,
                "stop_loss": stop,
                "structural_stop": structural_stop,
                "invalidation_basis": "STRUCTURAL_LEVEL_PLUS_ATR_BUFFER" if structural_stop is not None else "ATR_FALLBACK_LOWER_CONFIDENCE",
                "invalidation_source": structural_source,
                "take_profit_1": tp1,
                "take_profit_2": target,
                "target_source": target_meta.get("source"),
                "target_quality": target_meta.get("quality", 0.0),
                "target_distance_atr": target_meta.get("distance_atr", space_atr),
                "risk_distance": risk,
                "reward_distance": reward,
                "available_space": space,
                "available_space_atr": space_atr,
                "real_rr": real_rr,
                "rr_tp1": (reward * TP1_FRACTION) / risk if risk > 0 else 0.0,
                "rr_tp2": real_rr,
                "asymmetric_payoff": real_rr >= MIN_RR,
                "rr_minimum": MIN_RR,
                "stop_distance_atr": stop_atr,
                "risk_buffer_atr": RISK_ATR_BUFFER,
                "structural_breach": structural_breached,
            }
            support += [f"entry={entry:.6f}", f"structural_stop={structural_stop if structural_stop is not None else 'NONE'}", f"final_stop={stop:.6f}", f"target={target:.6f}", f"target_source={target_meta.get('source')}", f"target_quality={target_meta.get('quality', 0.0):.1f}", f"available_space_atr={space_atr:.3f}", f"real_rr={real_rr:.3f}", f"stop_distance_atr={stop_atr:.3f}"]
            if real_rr < MIN_RR: counter.append("REAL_RR_BELOW_MINIMUM")

    # 8E — liquidity matters when it can obstruct the actual entry -> target path.
    liquidity = levels.get("liquidity_event_level") if levels else None
    target = plan.get("take_profit_2")
    liquidity_on_path = liquidity is not None and target is not None and min(entry, target) < liquidity < max(entry, target)
    if liquidity_on_path:
        liquidity_r = abs(liquidity - entry) / max(plan.get("risk_distance", atr), 1e-9)
        plan["opposing_liquidity"], plan["opposing_liquidity_r"] = liquidity, liquidity_r
        if liquidity_r <= MAX_LIQUIDITY_RISK_R: counter.append("OPPOSING_LIQUIDITY_PATH_RISK")
        if liquidity_quality["externality"] == "EXTERNAL": counter.append("EXTERNAL_LIQUIDITY_PATH_RISK")
        elif liquidity_quality["externality"] == "INTERNAL": support.append("internal_liquidity_has_lower_weight")
        if liquidity_quality["auction_state"] == "PENDING": counter.append("LIQUIDITY_AUCTION_NOT_TERMINALLY_CONFIRMED")
        if liquidity_quality["information"] == "LOW_INFORMATION": counter.append("LOW_INFORMATION_LIQUIDITY_EVENT")
    else:
        plan["opposing_liquidity"], plan["opposing_liquidity_r"] = None, None

    # 8F — space is the smallest credible opposing distance, reconciled with E5.
    e5_long = _num(e5.get("available_space_atr_long"))
    e5_short = _num(e5.get("available_space_atr_short"))
    e5_space = e5_long if direction == "BUY" else e5_short if direction == "SELL" else 0.0
    computed_space = plan.get("available_space_atr", 0.0)
    nearest_barrier_atr = candidates[0]["level"] - entry if direction == "BUY" and candidates else entry - candidates[0]["level"] if direction == "SELL" and candidates else 0.0
    nearest_barrier_atr = nearest_barrier_atr / max(atr, 1e-9) if nearest_barrier_atr else 0.0
    plan["nearest_credible_barrier_atr"] = nearest_barrier_atr
    if e5_space > 0:
        plan["e5_available_space_atr"] = e5_space
        plan["space_consistency_delta_atr"] = computed_space - e5_space
        effective_space = min(computed_space, e5_space) if computed_space > 0 else e5_space
    else:
        effective_space = computed_space
    plan["effective_available_space_atr"] = effective_space
    if effective_space < MIN_SPACE_ATR: counter.append("EFFECTIVE_SPACE_BELOW_MINIMUM")
    if computed_space > 0 and e5_space > 0 and abs(computed_space - e5_space) >= 0.75: counter.append("SPACE_EVIDENCE_CONFLICT")
    e5_reasons = [_text(x) for x in (e5.get("reasons") or [])]
    if "SPACE_CONSTRAINED" in _text(e5.get("finding")) or "LONG_SPACE_CONSTRAINED" in e5_reasons or "SHORT_SPACE_CONSTRAINED" in e5_reasons:
        counter.append("LOCATION_SPACE_CONSTRAINED")

    # 8G — dynamic target must be the first credible barrier; never manufacture RR by skipping a real barrier.
    target_ok = bool(plan) and target is not None and target_meta.get("credible") and effective_space >= MIN_TARGET_CLEARANCE_ATR
    if not target_ok: counter.append("DYNAMIC_TARGET_NOT_USABLE")
    if plan.get("target_source") in {"STRUCTURE_HIGH_20", "STRUCTURE_LOW_20"}: counter.append("TARGET_QUALITY_LOW")
    if plan.get("target_distance_atr", 0.0) > MAX_TARGET_EXTENSION_ATR: counter.append("TARGET_TOO_FAR_FOR_M5_EXECUTION")

    # 8I — execution risk is assessed from current range, ATR drift and explicit costs.
    if volatility["state"] == "EXPANSION_EXTREME" or volatility["last_range_atr"] > MAX_LAST_RANGE_ATR:
        counter.append("VOLATILITY_RISK_HIGH")
    elif volatility["state"] == "EXPANSION":
        counter.append("VOLATILITY_EXPANSION_RISK")
    if volatility["atr_stability"] == "UNSTABLE": counter.append("ATR_STABILITY_RISK")
    if execution["cost_atr"] > MAX_EXECUTION_COST_ATR: counter.append("EXECUTION_COST_TOO_HIGH")
    if volatility["state"] == "COMPRESSION" and plan.get("target_distance_atr", 0.0) >= 2.5:
        counter.append("COMPRESSION_TARGET_REALIZATION_RISK")

    space_ok = bool(plan) and effective_space >= MIN_SPACE_ATR and "SPACE_EVIDENCE_CONFLICT" not in counter and "LOCATION_SPACE_CONSTRAINED" not in counter
    rr_ok = bool(plan) and plan.get("real_rr", 0.0) >= MIN_RR
    stop_ok = bool(plan) and MIN_STOP_ATR <= plan.get("stop_distance_atr", 0.0) <= MAX_STOP_ATR
    liquidity_ok = not any(x in counter for x in {"OPPOSING_LIQUIDITY_PATH_RISK", "EXTERNAL_LIQUIDITY_PATH_RISK", "LIQUIDITY_AUCTION_NOT_TERMINALLY_CONFIRMED", "LOW_INFORMATION_LIQUIDITY_EVENT"})
    volatility_ok = volatility["state"] not in {"EXPANSION_EXTREME"} and volatility["atr_stability"] == "STABLE" and "COMPRESSION_TARGET_REALIZATION_RISK" not in counter
    execution_ok = execution["cost_atr"] <= MAX_EXECUTION_COST_ATR

    critical = {
        "RISK_DATA_INVALID", "NO_VALID_DIRECTION", "VALID_SETUP_THESIS", "ENTRY_CONFIRMATION", "STRUCTURAL_INVALIDATION_BREACHED",
        "STOP_TOO_TIGHT_FOR_VOLATILITY", "STOP_TOO_WIDE_FOR_ECONOMICS", "NO_USABLE_STRUCTURAL_TARGET", "AVAILABLE_SPACE_BELOW_MINIMUM",
        "EFFECTIVE_SPACE_BELOW_MINIMUM", "SPACE_EVIDENCE_CONFLICT", "REAL_RR_BELOW_MINIMUM", "OPPOSING_LIQUIDITY_PATH_RISK",
        "EXTERNAL_LIQUIDITY_PATH_RISK", "LOCATION_SPACE_CONSTRAINED", "VOLATILITY_RISK_HIGH", "ATR_STABILITY_RISK",
        "EXECUTION_COST_TOO_HIGH", "DYNAMIC_TARGET_NOT_USABLE", "TARGET_QUALITY_LOW", "TARGET_TOO_FAR_FOR_M5_EXECUTION",
        "LIQUIDITY_AUCTION_NOT_TERMINALLY_CONFIRMED", "LOW_INFORMATION_LIQUIDITY_EVENT", "COMPRESSION_TARGET_REALIZATION_RISK",
    }
    counter, missing = list(dict.fromkeys(counter)), list(dict.fromkeys(missing))
    hard_failure = any(x in critical for x in counter) or bool(missing)
    economics_ready = data_valid and direction in {"BUY", "SELL"} and bool(plan) and target_ok and space_ok and rr_ok and stop_ok and liquidity_ok and volatility_ok and execution_ok and not hard_failure
    if economics_ready: economic_state = "ATTRACTIVE"
    elif plan and any(x in counter for x in critical): economic_state = "UNATTRACTIVE"
    elif plan: economic_state = "CONDITIONAL"
    else: economic_state = "UNRESOLVED"
    risk_ready = economics_ready
    score = 95.0 if risk_ready else 65.0 if economic_state == "CONDITIONAL" else 30.0 if economic_state == "UNATTRACTIVE" else 15.0

    output = {
        **base,
        "state": economic_state,
        "economic_state": economic_state,
        "risk_gate": "RISK_READY" if risk_ready else "RISK_NOT_READY",
        "direction": direction,
        "setup": setup,
        "confirmation": confirmation,
        "confirmation_trace": confirmation_trace,
        "trade_plan": plan,
        "risk_model": {
            "atr": atr, "atr_period": ATR_PERIOD, "volatility_state": volatility["state"], "last_range_atr": volatility["last_range_atr"],
            "expansion_ratio": volatility["expansion_ratio"], "atr_stability": volatility["atr_stability"], "atr_drift": volatility["atr_drift"],
            "spread": execution["spread"], "slippage": execution["slippage"], "execution_cost_atr": execution["cost_atr"],
            "structure_lookback": STRUCTURE_LOOKBACK, "min_stop_atr": MIN_STOP_ATR, "max_stop_atr": MAX_STOP_ATR,
            "min_space_atr": MIN_SPACE_ATR, "risk_buffer_atr": RISK_ATR_BUFFER, "max_liquidity_risk_r": MAX_LIQUIDITY_RISK_R,
            "max_execution_cost_atr": MAX_EXECUTION_COST_ATR,
        },
        "structural_evidence": {**levels, "structural_breached": structural_breached, "invalidation_source": structural_source},
        "liquidity_evidence": liquidity_quality,
        "location_evidence": {
            "structural_location": _text(e5.get("structural_location")),
            "e5_available_space_long_atr": e5_long,
            "e5_available_space_short_atr": e5_short,
            "effective_available_space_atr": effective_space,
            "nearest_credible_barrier_atr": nearest_barrier_atr,
        },
        "gate_matrix": {
            "8A_data_integrity": "PASS" if data_valid else "FAIL",
            "8B_direction_validation": "PASS" if direction in {"BUY", "SELL"} else "FAIL",
            "8C_setup_confirmation_gate": "PASS" if confirmation == "CONFIRMED" else "FAIL",
            "8D_structural_invalidation": "FAIL" if structural_breached else "PASS" if structural is not None and plan.get("structural_stop") is not None else "PASS_FALLBACK_ATR" if plan else "FAIL",
            "8E_liquidity_risk": "PASS" if liquidity_ok else "FAIL",
            "8F_available_space": "PASS" if space_ok else "FAIL",
            "8G_dynamic_target": "PASS" if target_ok and "TARGET_QUALITY_LOW" not in counter else "FAIL",
            "8H_real_rr": "PASS" if rr_ok else "FAIL",
            "8I_volatility_execution": "PASS" if volatility_ok and execution_ok and stop_ok else "FAIL",
            "8J_trade_economics": economic_state,
            "8K_final_risk_gate": "RISK_READY" if risk_ready else "RISK_NOT_READY",
        },
        "supporting_evidence": support,
        "counter_evidence": counter,
        "missing_evidence": missing,
        "invalidation": [
            "closed-candle structural invalidation", "structural stop becomes economically excessive", "effective available space collapses below minimum",
            "real RR falls below minimum", "opposing or external liquidity blocks the path to target", "volatility makes the stop non-survivable",
            "execution cost becomes excessive", "entry confirmation is not proven", "target barrier is not credible or is too far for M5",
        ],
        "professional_reasoning": {
            "8A_data_integrity": "PASS" if data_valid else "FAIL",
            "8B_direction_validation": "PASS" if direction in {"BUY", "SELL"} else "FAIL",
            "8C_setup_confirmation_gate": "PASS" if confirmation == "CONFIRMED" else "FAIL",
            "8D_structural_invalidation": "The protected structural boundary is thesis invalidation; ATR is only the survival buffer.",
            "8E_liquidity_risk": "Liquidity is a risk only when it can obstruct the actual entry-to-target path; external and low-information liquidity receive higher risk weight.",
            "8F_available_space": f"computed_space_atr={computed_space:.3f} e5_space_atr={e5_space:.3f} effective_space_atr={effective_space:.3f} nearest_barrier_atr={nearest_barrier_atr:.3f} minimum={MIN_SPACE_ATR:.3f}",
            "8G_dynamic_target": f"first_credible_target={plan.get('take_profit_2', 'NONE')} source={plan.get('target_source', 'NONE')} quality={plan.get('target_quality', 0.0):.1f}; farther targets are never used to manufacture RR across a nearer credible barrier.",
            "8H_real_rr": f"real_rr={plan.get('real_rr', 0.0):.3f} minimum={MIN_RR:.3f}",
            "8I_volatility_execution": f"volatility={volatility['state']} last_range_atr={volatility['last_range_atr']:.3f} atr_drift={volatility['atr_drift']:.3f} atr_stability={volatility['atr_stability']} stop_atr={plan.get('stop_distance_atr', 0.0):.3f} execution_cost_atr={execution['cost_atr']:.3f}",
            "8J_trade_economics": economic_state,
            "8K_final_risk_gate": "RISK_READY" if risk_ready else "RISK_NOT_READY",
            "decision_path": "E8 validates survivability/economics only; E9 retains final trade authority.",
        },
    }
    reasons = () if risk_ready else tuple(counter + missing or ["ECONOMICS_NOT_READY"])
    return EngineResult("E8", NAME, risk_ready, score, output, reasons)
