from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Trade Economics & Risk Brain"
QUESTION = "Is the proposed trade economically attractive and structurally survivable?"
ARCHITECTURE = "E8_PROFESSIONAL_TRADE_ECONOMICS_RISK_BRAIN_V7"
VERSION = "7.0"

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
        if key not in mapping:
            continue
        try:
            value = float(mapping[key])
            if value == value and value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return None


def _direction(e6: dict[str, Any]) -> str:
    value = _text(e6.get("direction", e6.get("direction_thesis")))
    if value in {"BUY", "BULLISH", "UP", "LONG", "BUYERS", "TREND_UP"}:
        return "BUY"
    if value in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS", "TREND_DOWN"}:
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
        high = _num(bars[i].get("high"))
        low = _num(bars[i].get("low"))
        previous_close = _num(bars[i - 1].get("close"))
        if high > 0 and low >= 0 and previous_close > 0:
            trs.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return mean(trs) if trs else 0.0


def _atr_series(bars: list[dict[str, Any]], period: int = ATR_PERIOD) -> list[float]:
    trs: list[float] = []
    for i in range(1, len(bars)):
        high = _num(bars[i].get("high"))
        low = _num(bars[i].get("low"))
        previous_close = _num(bars[i - 1].get("close"))
        if high > 0 and low >= 0 and previous_close > 0:
            trs.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    if not trs:
        return []
    return [mean(trs[max(0, i - period + 1): i + 1]) for i in range(len(trs))]


def _recent_structure(bars: list[dict[str, Any]]) -> dict[str, float | None]:
    # Targets must come from already closed candles before the entry candle.
    recent = bars[-(STRUCTURE_LOOKBACK + 1):-1]
    highs = [_num(x.get("high")) for x in recent if _num(x.get("high")) > 0]
    lows = [_num(x.get("low")) for x in recent if _num(x.get("low")) > 0]
    return {
        "structure_high_20": max(highs) if highs else None,
        "structure_low_20": min(lows) if lows else None,
    }


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


def _target_candidates(levels: dict[str, Any], direction: str, entry: float) -> list[dict[str, Any]]:
    if direction == "BUY":
        raw = [
            ("RESISTANCE", levels.get("next_resistance"), 92.0),
            ("PROTECTED_HIGH", levels.get("protected_high"), 90.0),
            ("LIQUIDITY_EVENT", levels.get("liquidity_event_level"), 80.0),
            ("STRUCTURE_HIGH_20", levels.get("structure_high_20"), 70.0),
        ]
        return [{"source": s, "level": v, "base_quality": q} for s, v, q in raw if v is not None and v > entry]
    if direction == "SELL":
        raw = [
            ("SUPPORT", levels.get("next_support"), 92.0),
            ("PROTECTED_LOW", levels.get("protected_low"), 90.0),
            ("LIQUIDITY_EVENT", levels.get("liquidity_event_level"), 80.0),
            ("STRUCTURE_LOW_20", levels.get("structure_low_20"), 70.0),
        ]
        return [{"source": s, "level": v, "base_quality": q} for s, v, q in raw if v is not None and v < entry]
    return []


def _dynamic_target(
    levels: dict[str, Any],
    direction: str,
    entry: float,
    atr: float,
    e4: dict[str, Any],
) -> dict[str, Any]:
    candidates = _target_candidates(levels, direction, entry)
    candidates.sort(key=lambda x: abs(x["level"] - entry))
    trace: list[dict[str, Any]] = []
    for candidate in candidates:
        distance_atr = abs(candidate["level"] - entry) / max(atr, 1e-9)
        quality = candidate["base_quality"]
        rejection: list[str] = []
        if distance_atr < MIN_TARGET_CLEARANCE_ATR:
            rejection.append("CLEARANCE_TOO_SMALL")
        if distance_atr > MAX_TARGET_EXTENSION_ATR:
            rejection.append("EXTENSION_TOO_FAR")
        if candidate["source"] == "LIQUIDITY_EVENT":
            externality = _text(e4.get("liquidity_externality"))
            auction_state = _text(e4.get("auction_state"))
            information = _text(e4.get("auction_information"))
            if externality == "EXTERNAL":
                quality += 5.0
            elif externality == "INTERNAL":
                quality -= 10.0
            if auction_state == "PENDING":
                quality -= 20.0
                rejection.append("AUCTION_PENDING")
            if information == "LOW_INFORMATION":
                quality -= 15.0
                rejection.append("LOW_INFORMATION_LIQUIDITY")
        quality = max(0.0, min(100.0, quality))
        credible = quality >= 70.0 and not rejection
        item = {
            "source": candidate["source"],
            "level": candidate["level"],
            "distance_atr": distance_atr,
            "quality": quality,
            "credible": credible,
            "rejection": rejection,
        }
        trace.append(item)
        if credible:
            return {**item, "candidate_trace": trace}
    return {
        "source": None,
        "level": None,
        "distance_atr": 0.0,
        "quality": 0.0,
        "credible": False,
        "rejection": ["NO_CREDIBLE_OPPOSING_BARRIER"],
        "candidate_trace": trace,
    }


def _space_analysis(
    e5: dict[str, Any],
    target_meta: dict[str, Any],
    entry: float,
    atr: float,
    direction: str,
) -> dict[str, Any]:
    e5_space = _num(e5.get("available_space_atr_long" if direction == "BUY" else "available_space_atr_short"))
    target_space = _num(target_meta.get("distance_atr")) if target_meta.get("credible") else 0.0
    barrier_space = target_space if target_space > 0 else float("inf")
    candidates = [x for x in (e5_space, barrier_space) if x > 0 and x != float("inf")]
    effective = min(candidates) if candidates else 0.0
    consistency_delta = abs(e5_space - target_space) if e5_space > 0 and target_space > 0 else None
    return {
        "e5_available_space_atr": e5_space,
        "target_barrier_space_atr": target_space,
        "effective_available_space_atr": effective,
        "space_consistency_delta_atr": consistency_delta,
        "space_source": "MIN(E5_LOCATION, CREDIBLE_OPPOSING_BARRIER)" if candidates else "NO_CREDIBLE_SPACE",
        "minimum_required_atr": MIN_SPACE_ATR,
        "space_ok": effective >= MIN_SPACE_ATR,
        "entry": entry,
    }


def _volatility_state(bars: list[dict[str, Any]], atr: float) -> dict[str, Any]:
    series = _atr_series(bars)
    if atr <= 0 or len(series) < 2:
        return {
            "state": "INVALID",
            "last_range_atr": 0.0,
            "expansion_ratio": 0.0,
            "atr_stability": "INVALID",
            "atr_drift": 0.0,
        }
    last_range = max(0.0, _num(bars[-1].get("high")) - _num(bars[-1].get("low")))
    previous_range = max(0.0, _num(bars[-2].get("high")) - _num(bars[-2].get("low")))
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
    recent_atr = mean(series[-5:]) if len(series) >= 5 else mean(series)
    baseline_atr = mean(series[-min(len(series), ATR_PERIOD):])
    atr_drift = recent_atr / max(baseline_atr, 1e-9)
    atr_stability = "STABLE" if 0.65 <= atr_drift <= 1.50 else "UNSTABLE"
    return {
        "state": state,
        "last_range_atr": ratio,
        "expansion_ratio": expansion_ratio,
        "atr_stability": atr_stability,
        "atr_drift": atr_drift,
    }


def _execution_cost(snapshot: dict[str, Any], entry: float, atr: float) -> dict[str, Any]:
    spread = _first_num(snapshot, ("spread", "spread_price", "current_spread")) or 0.0
    slippage = _first_num(snapshot, ("slippage", "slippage_price", "expected_slippage")) or 0.0
    total = spread + slippage
    return {
        "spread": spread,
        "slippage": slippage,
        "total_cost": total,
        "cost_atr": total / atr if atr > 0 else float("inf"),
        "entry": entry,
    }


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
    if direction == "BUY":
        return close <= structural
    if direction == "SELL":
        return close >= structural
    return False


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
        return EngineResult(
            "E8", NAME, False, 0.0,
            {**base, "state": "UNRESOLVED", "economic_state": "UNRESOLVED", "risk_gate": "RISK_NOT_READY", "trade_plan": {}, "supporting_evidence": [], "counter_evidence": ["INSUFFICIENT_CLOSED_CANDLE_DATA"], "missing_evidence": ["SUFFICIENT_RISK_SAMPLE"]},
            ("INSUFFICIENT_DATA",),
        )

    direction, setup = _direction(e6), _setup(e6)
    confirmation, confirmation_trace = _confirmation(e7)
    entry = _num(bars[-1].get("close"))
    atr = _atr(bars)
    volatility = _volatility_state(bars, atr)
    execution = _execution_cost(snapshot, entry, atr)
    liquidity_quality = _e4_liquidity_quality(e4)
    support: list[str] = []
    counter: list[str] = []
    missing: list[str] = []
    plan: dict[str, Any] = {}

    data_valid = entry > 0 and atr > 0
    if not data_valid:
        counter.append("RISK_DATA_INVALID")
    if direction not in {"BUY", "SELL"}:
        counter.append("NO_VALID_DIRECTION")
    if setup.upper() in {"UNKNOWN", "NONE", "UNRESOLVED"}:
        missing.append("VALID_SETUP_THESIS")
    if confirmation != "CONFIRMED":
        missing.append("ENTRY_CONFIRMATION")

    levels = _level_inputs(e3, e4, e5, bars) if data_valid and direction in {"BUY", "SELL"} else {}
    target_meta = _dynamic_target(levels, direction, entry, atr, e4) if levels else {
        "source": None, "level": None, "distance_atr": 0.0, "quality": 0.0, "credible": False, "rejection": ["NO_TARGET_INPUTS"], "candidate_trace": [],
    }

    candidates = _target_candidates(levels, direction, entry) if levels else []
    invalidations = []
    if direction == "BUY":
        invalidations = [
            ("PROTECTED_LOW", levels.get("protected_low")),
            ("STRUCTURE_LOW_20", levels.get("structure_low_20")),
        ]
    elif direction == "SELL":
        invalidations = [
            ("PROTECTED_HIGH", levels.get("protected_high")),
            ("STRUCTURE_HIGH_20", levels.get("structure_high_20")),
        ]
    invalid_candidates = [(name, level) for name, level in invalidations if level is not None and ((direction == "BUY" and level < entry) or (direction == "SELL" and level > entry))]
    invalid_candidates.sort(key=lambda x: abs(entry - x[1]))
    structural_source = invalid_candidates[0][0] if invalid_candidates else None
    structural_level = invalid_candidates[0][1] if invalid_candidates else None
    structural_breach = _has_structural_breach(bars, direction, structural_level)
    if structural_breach:
        counter.append("STRUCTURAL_INVALIDATION_BREACHED")

    if direction in {"BUY", "SELL"} and data_valid:
        if direction == "BUY":
            structural_stop = structural_level if structural_level is not None and structural_level < entry else None
            stop = structural_stop - RISK_ATR_BUFFER * atr if structural_stop is not None else entry - FALLBACK_STOP_ATR * atr
        else:
            structural_stop = structural_level if structural_level is not None and structural_level > entry else None
            stop = structural_stop + RISK_ATR_BUFFER * atr if structural_stop is not None else entry + FALLBACK_STOP_ATR * atr
        risk = abs(entry - stop)
        stop_atr = risk / atr if atr > 0 else float("inf")
        space = _space_analysis(e5, target_meta, entry, atr, direction)
        target = target_meta.get("level")
        if target is None:
            missing.append("NO_USABLE_STRUCTURAL_TARGET")
        target_distance = abs(target - entry) if target is not None else 0.0
        real_rr = target_distance / risk if target is not None and risk > 0 else 0.0
        liquidity_level = levels.get("liquidity_event_level")
        opposing_liquidity_on_path = liquidity_level is not None and target is not None and min(entry, target) < liquidity_level < max(entry, target)
        liquidity_r = abs(liquidity_level - entry) / max(risk, 1e-9) if opposing_liquidity_on_path else 0.0
        if opposing_liquidity_on_path:
            plan_liquidity_reason = "OPPOSING_LIQUIDITY_ON_TARGET_PATH"
            counter.append(plan_liquidity_reason)
            if liquidity_r <= MAX_LIQUIDITY_R_R:
                counter.append("OPPOSING_LIQUIDITY_PATH_RISK")
            if liquidity_quality["externality"] == "EXTERNAL":
                counter.append("EXTERNAL_LIQUIDITY_PATH_RISK")
            elif liquidity_quality["externality"] == "INTERNAL":
                support.append("INTERNAL_LIQUIDITY_LOWER_WEIGHT")
            if liquidity_quality["auction_state"] == "PENDING":
                counter.append("LIQUIDITY_AUCTION_NOT_TERMINALLY_CONFIRMED")
            if liquidity_quality["information"] == "LOW_INFORMATION":
                counter.append("LOW_INFORMATION_LIQUIDITY_RISK")
        if stop_atr < MIN_STOP_ATR:
            counter.append("STOP_TOO_TIGHT_FOR_VOLATILITY")
        if stop_atr > MAX_STOP_ATR:
            counter.append("STOP_TOO_WIDE_FOR_ECONOMICS")
        if target is not None and real_rr < MIN_RR:
            counter.append("REAL_RR_BELOW_MINIMUM")
        if not target_meta.get("credible"):
            counter.append("DYNAMIC_TARGET_NOT_USABLE")
        if target_meta.get("source") in {"STRUCTURE_HIGH_20", "STRUCTURE_LOW_20"}:
            counter.append("TARGET_IS_SECONDARY_STRUCTURE")
        if target_meta.get("distance_atr", 0.0) > MAX_TARGET_EXTENSION_ATR:
            counter.append("TARGET_TOO_FAR_FOR_M5_EXECUTION")
        if space["effective_available_space_atr"] < MIN_SPACE_ATR:
            counter.append("EFFECTIVE_SPACE_BELOW_MINIMUM")
        if space["space_consistency_delta_atr"] is not None and space["space_consistency_delta_atr"] >= 0.75:
            counter.append("SPACE_EVIDENCE_CONFLICT")

        plan = {
            "valid": True,
            "entry": entry,
            "direction": direction,
            "stop_loss": stop,
            "structural_stop": structural_stop,
            "invalidation_basis": "STRUCTURAL_LEVEL_PLUS_ATR_BUFFER" if structural_stop is not None else "ATR_FALLBACK_LOWER_CONFIDENCE",
            "invalidation_source": structural_source,
            "take_profit_1": entry + target_distance * TP1_FRACTION if direction == "BUY" else entry - target_distance * TP1_FRACTION,
            "take_profit_2": target,
            "target_source": target_meta.get("source"),
            "target_quality": target_meta.get("quality", 0.0),
            "target_distance_atr": target_meta.get("distance_atr", 0.0),
            "target_candidate_trace": target_meta.get("candidate_trace", []),
            "risk_distance": risk,
            "reward_distance": target_distance,
            "available_space": target_distance,
            "available_space_atr": space["effective_available_space_atr"],
            "e5_available_space_atr": space["e5_available_space_atr"],
            "target_barrier_space_atr": space["target_barrier_space_atr"],
            "space_consistency_delta_atr": space["space_consistency_delta_atr"],
            "real_rr": real_rr,
            "rr_tp1": (target_distance * TP1_FRACTION) / risk if risk > 0 else 0.0,
            "rr_tp2": real_rr,
            "asymmetric_payoff": real_rr >= MIN_RR,
            "stop_distance_atr": stop_atr,
            "risk_buffer_atr": RISK_ATR_BUFFER,
            "structural_breach": structural_breach,
            "opposing_liquidity": liquidity_level if opposing_liquidity_on_path else None,
            "opposing_liquidity_r": liquidity_r,
        }
        support.extend([
            f"entry={entry:.6f}",
            f"structural_stop={structural_stop:.6f}" if structural_stop is not None else "structural_stop=NONE",
            f"final_stop={stop:.6f}",
            f"target={target:.6f}" if target is not None else "target=NONE",
            f"target_source={target_meta.get('source')}",
            f"target_quality={target_meta.get('quality', 0.0):.1f}",
            f"effective_space_atr={space['effective_available_space_atr']:.3f}",
            f"real_rr={real_rr:.3f}",
            f"stop_distance_atr={stop_atr:.3f}",
        ])
    else:
        space = {"effective_available_space_atr": 0.0, "e5_available_space_atr": 0.0, "target_barrier_space_atr": 0.0, "space_consistency_delta_atr": None, "space_source": "UNAVAILABLE", "minimum_required_atr": MIN_SPACE_ATR, "space_ok": False, "entry": entry}
        counter.append("RISK_MODEL_UNAVAILABLE")

    # 8I: execution is not a cosmetic score; it can veto an otherwise attractive setup.
    if volatility["state"] == "EXPANSION_EXTREME":
        counter.append("VOLATILITY_RISK_HIGH")
    elif volatility["state"] == "EXPANSION":
        counter.append("VOLATILITY_EXPANSION_RISK")
    if volatility["atr_stability"] == "UNSTABLE":
        counter.append("ATR_STABILITY_RISK")
    if execution["cost_atr"] > MAX_EXECUTION_COST_ATR:
        counter.append("EXECUTION_COST_TOO_HIGH")
    if volatility["state"] == "COMPRESSION" and plan.get("target_distance_atr", 0.0) >= 2.5:
        counter.append("COMPRESSION_TARGET_REALIZATION_RISK")

    # Hard gates: E8 is allowed to say risk is not ready, never to overrule E9's authority.
    critical = {
        "RISK_DATA_INVALID", "NO_VALID_DIRECTION", "VALID_SETUP_THESIS", "ENTRY_CONFIRMATION",
        "STRUCTURAL_INVALIDATION_BREACHED", "STOP_TOO_TIGHT_FOR_VOLATILITY", "STOP_TOO_WIDE_FOR_ECONOMICS",
        "NO_USABLE_STRUCTURAL_TARGET", "EFFECTIVE_SPACE_BELOW_MINIMUM", "REAL_RR_BELOW_MINIMUM",
        "OPPOSING_LIQUIDITY_PATH_RISK", "EXTERNAL_LIQUIDITY_PATH_RISK", "LIQUIDITY_AUCTION_NOT_TERMINALLY_CONFIRMED",
        "LOW_INFORMATION_LIQUIDITY_RISK", "VOLATILITY_RISK_HIGH", "ATR_STABILITY_RISK", "EXECUTION_COST_TOO_HIGH",
        "DYNAMIC_TARGET_NOT_USABLE", "TARGET_TOO_FAR_FOR_M5_EXECUTION", "SPACE_EVIDENCE_CONFLICT",
        "COMPRESSION_TARGET_REALIZATION_RISK",
    }
    counter = list(dict.fromkeys(counter))
    missing = list(dict.fromkeys(missing))
    hard_failure = any(reason in critical for reason in counter) or bool(missing)

    economic_ready = (
        data_valid
        and direction in {"BUY", "SELL"}
        and bool(plan)
        and bool(plan.get("valid"))
        and target_meta.get("credible")
        and plan.get("real_rr", 0.0) >= MIN_RR
        and plan.get("stop_distance_atr", float("inf")) >= MIN_STOP_ATR
        and plan.get("stop_distance_atr", float("inf")) <= MAX_STOP_ATR
        and space.get("effective_available_space_atr", 0.0) >= MIN_SPACE_ATR
        and not structural_breach
        and volatility["state"] not in {"EXPANSION_EXTREME", "INVALID"}
        and volatility["atr_stability"] == "STABLE"
        and execution["cost_atr"] <= MAX_EXECUTION_COST_ATR
        and not any(reason in critical for reason in counter)
        and not missing
    )
    if economic_ready:
        economic_state = "ATTRACTIVE"
    elif plan and not hard_failure:
        economic_state = "CONDITIONAL"
    elif plan:
        economic_state = "UNATTRACTIVE"
    else:
        economic_state = "UNRESOLVED"

    risk_ready = economic_ready
    score = 95.0 if risk_ready else 65.0 if economic_state == "CONDITIONAL" else 30.0 if economic_state == "UNATTRACTIVE" else 15.0
    reasons = tuple() if risk_ready else tuple(counter + missing + ["ECONOMICS_NOT_READY"])

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
            "atr": atr,
            "atr_period": ATR_PERIOD,
            "volatility_state": volatility["state"],
            "last_range_atr": volatility["last_range_atr"],
            "expansion_ratio": volatility["expansion_ratio"],
            "atr_stability": volatility["atr_stability"],
            "atr_drift": volatility["atr_drift"],
            "spread": execution["spread"],
            "slippage": execution["slippage"],
            "execution_cost_atr": execution["cost_atr"],
            "structure_lookback": STRUCTURE_LOOKBACK,
            "min_stop_atr": MIN_STOP_ATR,
            "max_stop_atr": MAX_STOP_ATR,
            "min_space_atr": MIN_SPACE_ATR,
            "min_rr": MIN_RR,
            "risk_buffer_atr": RISK_ATR_BUFFER,
            "max_liquidity_risk_r": MAX_LIQUIDITY_R_R,
            "max_execution_cost_atr": MAX_EXECUTION_COST_ATR,
        },
        "structural_evidence": {
            **levels,
            "structural_breach": structural_breach,
            "invalidation_source": structural_source,
        },
        "liquidity_evidence": liquidity_quality,
        "location_evidence": {
            "e5_available_space_atr_long": _num(e5.get("available_space_atr_long")),
            "e5_available_space_atr_short": _num(e5.get("available_space_atr_short")),
            "effective_available_space_atr": space.get("effective_available_space_atr", 0.0),
            "target_barrier_space_atr": space.get("target_barrier_space_atr", 0.0),
            "space_consistency_delta_atr": space.get("space_consistency_delta_atr"),
            "space_source": space.get("space_source"),
        },
        "dynamic_target": target_meta,
        "gate_matrix": {
            "8A_data_integrity": "PASS" if data_valid else "FAIL",
            "8B_direction_validation": "PASS" if direction in {"BUY", "SELL"} else "FAIL",
            "8C_setup_confirmation_gate": "PASS" if confirmation == "CONFIRMED" else "FAIL",
            "8D_structural_invalidation": "FAIL" if structural_breach else "PASS",
            "8E_liquidity_risk": "PASS" if not any(x in counter for x in {"OPPOSING_LIQUIDITY_PATH_RISK", "EXTERNAL_LIQUIDITY_PATH_RISK", "LIQUIDITY_AUCTION_NOT_TERMINALLY_CONFIRMED", "LOW_INFORMATION_LIQUIDITY_RISK"}) else "FAIL",
            "8F_available_space": "PASS" if space.get("space_ok") and "SPACE_EVIDENCE_CONFLICT" not in counter else "FAIL",
            "8G_dynamic_target": "PASS" if target_meta.get("credible") and "TARGET_TOO_FAR_FOR_M5_EXECUTION" not in counter else "FAIL",
            "8H_real_rr": "PASS" if plan.get("real_rr", 0.0) >= MIN_RR else "FAIL",
            "8I_volatility_execution": "PASS" if volatility["state"] not in {"EXPANSION_EXTREME", "INVALID"} and volatility["atr_stability"] == "STABLE" and execution["cost_atr"] <= MAX_EXECUTION_COST_ATR else "FAIL",
            "8J_trade_economics": economic_state,
            "8K_final_risk_gate": "RISK_READY" if risk_ready else "RISK_NOT_READY",
        },
        "supporting_evidence": support,
        "counter_evidence": counter,
        "missing_evidence": missing,
        "invalidation": [
            "closed-candle structural invalidation",
            "structural stop becomes economically excessive",
            "effective available space collapses below minimum",
            "real RR falls below minimum",
            "opposing or external liquidity blocks the target path",
            "volatility makes the stop non-survivable",
            "execution cost becomes excessive",
            "entry confirmation is not proven",
            "target barrier is not credible or is too far for M5 execution",
        ],
        "professional_reasoning": {
            "8A_data_integrity": "PASS" if data_valid else "FAIL",
            "8B_direction_validation": "PASS" if direction in {"BUY", "SELL"} else "FAIL",
            "8C_setup_confirmation_gate": "PASS" if confirmation == "CONFIRMED" else "FAIL",
            "8D_structural_invalidation": "Protected structure defines invalidation; ATR is only the survival buffer.",
            "8E_liquidity_risk": "Liquidity is a path risk only when it can obstruct the actual entry-to-target route; internal pending liquidity is lower-information than confirmed external liquidity.",
            "8F_available_space": f"effective_space_atr={space.get('effective_available_space_atr', 0.0):.3f}; E5 and the selected opposing barrier are reconciled instead of trusting either source blindly.",
            "8G_dynamic_target": f"selected_target={plan.get('take_profit_2', 'NONE')} source={plan.get('target_source', 'NONE')} quality={plan.get('target_quality', 0.0):.1f}; farther targets are never used to manufacture RR.",
            "8H_real_rr": f"real_rr={plan.get('real_rr', 0.0):.3f} minimum={MIN_RR:.2f}",
            "8I_volatility_execution": f"volatility={volatility['state']} last_range_atr={volatility['last_range_atr']:.3f} atr_drift={volatility['atr_drift']:.3f} execution_cost_atr={execution['cost_atr']:.3f}",
            "8J_trade_economics": economic_state,
            "8K_final_risk_gate": "RISK_READY" if risk_ready else "RISK_NOT_READY",
        },
        "decision_path": "E8 validates survivability/economics only; E9 retains final trade authority.",
    }
    return EngineResult("E8", NAME, risk_ready, score, output, reasons)
