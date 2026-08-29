from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Trade Economics & Risk Brain"
QUESTION = "Is the proposed trade economically attractive and structurally survivable?"
ARCHITECTURE = "E8_PROFESSIONAL_TRADE_ECONOMICS_RISK_BRAIN_V5"
VERSION = "5.0"
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


def _levels(e3: dict[str, Any], e4: dict[str, Any], e5: dict[str, Any], bars: list[dict[str, Any]], direction: str, entry: float) -> dict[str, Any]:
    recent = _recent_structure(bars)
    hi20, lo20 = recent["structure_high_20"], recent["structure_low_20"]
    protected_high = _first_num(e3, ("protected_high", "external_protected_high", "internal_protected_high"))
    protected_low = _first_num(e3, ("protected_low", "external_protected_low", "internal_protected_low"))
    resistance = _first_num(e5, ("next_resistance", "nearest_resistance", "resistance"))
    support = _first_num(e5, ("next_support", "nearest_support", "support"))
    event_level = _first_num(e4, ("event_level", "liquidity_level", "nearest_liquidity", "opposing_liquidity_level"))
    if direction == "BUY":
        targets = [("RESISTANCE", resistance), ("PROTECTED_HIGH", protected_high), ("LIQUIDITY_EVENT", event_level), ("STRUCTURE_HIGH_20", hi20)]
        targets = [(n, v) for n, v in targets if v is not None and v > entry]
        target_name, target = min(targets, key=lambda x: x[1]) if targets else (None, None)
        invalidations = [("PROTECTED_LOW", protected_low), ("STRUCTURE_LOW_20", lo20)]
        invalidations = [(n, v) for n, v in invalidations if v is not None and v < entry]
        invalidation_name, structural_invalidation = max(invalidations, key=lambda x: x[1], default=(None, None))
    else:
        targets = [("SUPPORT", support), ("PROTECTED_LOW", protected_low), ("LIQUIDITY_EVENT", event_level), ("STRUCTURE_LOW_20", lo20)]
        targets = [(n, v) for n, v in targets if v is not None and v < entry]
        target_name, target = max(targets, key=lambda x: x[1]) if targets else (None, None)
        invalidations = [("PROTECTED_HIGH", protected_high), ("STRUCTURE_HIGH_20", hi20)]
        invalidations = [(n, v) for n, v in invalidations if v is not None and v > entry]
        invalidation_name, structural_invalidation = min(invalidations, key=lambda x: x[1], default=(None, None))
    return {"protected_high": protected_high, "protected_low": protected_low, "next_resistance": resistance, "next_support": support, "liquidity_event_level": event_level, "structure_high_20": hi20, "structure_low_20": lo20, "structural_invalidation": structural_invalidation, "invalidation_source": invalidation_name, "target_level": target, "target_source": target_name}


def _volatility_state(bars: list[dict[str, Any]], atr: float) -> dict[str, Any]:
    if atr <= 0 or len(bars) < 2:
        return {"state": "INVALID", "last_range_atr": 0.0, "expansion_ratio": 0.0, "atr_stability": "INVALID"}
    ranges = [max(0.0, _num(x.get("high")) - _num(x.get("low"))) for x in bars[-ATR_PERIOD:] if _num(x.get("high")) > 0]
    last_range = ranges[-1] if ranges else 0.0
    previous_range = ranges[-2] if len(ranges) >= 2 else 0.0
    ratio = last_range / atr
    expansion_ratio = last_range / max(previous_range, 1e-9)
    if ratio >= 2.50:
        state = "EXPANSION_EXTREME"
    elif ratio >= 1.75 or expansion_ratio >= 2.0:
        state = "EXPANSION"
    elif ratio <= 0.60:
        state = "COMPRESSION"
    else:
        state = "NORMAL"
    med = mean(ranges) if ranges else 0.0
    atr_stability = "STABLE" if med > 0 and 0.50 <= atr / med <= 2.00 else "UNSTABLE"
    return {"state": state, "last_range_atr": ratio, "expansion_ratio": expansion_ratio, "atr_stability": atr_stability}


def _execution_cost(snapshot: dict[str, Any], entry: float, atr: float) -> dict[str, Any]:
    spread = _first_num(snapshot, ("spread", "spread_price", "current_spread")) or 0.0
    slippage = _first_num(snapshot, ("slippage", "slippage_price", "expected_slippage")) or 0.0
    total = spread + slippage
    return {"spread": spread, "slippage": slippage, "total_cost": total, "cost_atr": total / atr if atr > 0 else float("inf"), "entry": entry}


def _e4_liquidity_quality(e4: dict[str, Any]) -> dict[str, Any]:
    return {"liquidity_quality": _first_num(e4, ("liquidity_quality",)) or 0.0, "auction_quality": _first_num(e4, ("auction_quality",)) or 0.0, "proximity": _text(e4.get("liquidity_proximity")), "externality": _text(e4.get("liquidity_externality")), "auction_state": _text(e4.get("auction_state")), "information": _text(e4.get("auction_information"))}


def _has_structural_breach(bars: list[dict[str, Any]], direction: str, structural: float | None) -> bool:
    if structural is None or not bars:
        return False
    close = _num(bars[-1].get("close"))
    return close <= structural if direction == "BUY" else close >= structural if direction == "SELL" else False


def analyze_e8(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """E8 validates survivability/economics; E9 remains final trade authority."""
    bars = list(snapshot.get("bars") or [])
    e3, e4, e5, e6, e7 = (_evidence(upstream.get(k)) for k in ("E3", "E4", "E5", "E6", "E7"))
    base = {"architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION, "reasoning_role": "TRADE_ECONOMICS_RISK_ANALYST", "decision_authority": "E9", "trade_decision_authority": False, "closed_candle_only": True, "lookahead": False}
    if len(bars) < MIN_BARS:
        return EngineResult("E8", NAME, False, 0.0, {**base, "state": "UNRESOLVED", "economic_state": "UNRESOLVED", "risk_gate": "RISK_NOT_READY", "trade_plan": {}, "supporting_evidence": [], "counter_evidence": ["INSUFFICIENT_CLOSED_CANDLE_DATA"], "missing_evidence": ["SUFFICIENT_RISK_SAMPLE"]}, ("INSUFFICIENT_DATA",))

    direction, setup = _direction(e6), _setup(e6)
    confirmation, confirmation_trace = _confirmation(e7)
    entry, atr = _num(bars[-1].get("close")), _atr(bars)
    volatility, execution, liquidity_quality = _volatility_state(bars, atr), _execution_cost(snapshot, entry, atr), _e4_liquidity_quality(e4)
    support: list[str] = []; counter: list[str] = []; missing: list[str] = []; plan: dict[str, Any] = {}

    data_valid = entry > 0 and atr > 0
    if not data_valid: counter.append("RISK_DATA_INVALID")
    if direction not in {"BUY", "SELL"}: counter.append("NO_VALID_DIRECTION")
    if setup.upper() in {"UNKNOWN", "NONE", "UNRESOLVED"}: missing.append("VALID_SETUP_THESIS")
    if confirmation != "CONFIRMED": missing.append("ENTRY_CONFIRMATION")

    levels = _levels(e3, e4, e5, bars, direction, entry) if data_valid and direction in {"BUY", "SELL"} else {}
    structural = levels.get("structural_invalidation") if levels else None
    structural_breached = _has_structural_breach(bars, direction, structural)
    if structural_breached: counter.append("STRUCTURAL_INVALIDATION_BREACHED")

    if data_valid and direction in {"BUY", "SELL"}:
        if direction == "BUY":
            structural_stop = structural if structural is not None and structural < entry else None
            stop = structural_stop - RISK_ATR_BUFFER * atr if structural_stop is not None else entry - FALLBACK_STOP_ATR * atr
        else:
            structural_stop = structural if structural is not None and structural > entry else None
            stop = structural_stop + RISK_ATR_BUFFER * atr if structural_stop is not None else entry + FALLBACK_STOP_ATR * atr
        risk = abs(entry - stop); stop_atr = risk / atr
        if stop_atr < MIN_STOP_ATR: counter.append("STOP_TOO_TIGHT_FOR_VOLATILITY")
        if stop_atr > MAX_STOP_ATR: counter.append("STOP_TOO_WIDE_FOR_ECONOMICS")
        target, target_source = levels.get("target_level"), levels.get("target_source")
        if target is None:
            counter.append("NO_USABLE_STRUCTURAL_TARGET")
        else:
            space = abs(target - entry); space_atr = space / atr
            if space_atr < MIN_SPACE_ATR: counter.append("AVAILABLE_SPACE_BELOW_MINIMUM")
            reward = space; real_rr = reward / risk if risk > 0 else 0.0
            tp1 = entry + reward * TP1_FRACTION if direction == "BUY" else entry - reward * TP1_FRACTION
            plan = {"valid": True, "entry": entry, "direction": direction, "stop_loss": stop, "structural_stop": structural_stop, "invalidation_basis": "STRUCTURAL_LEVEL_PLUS_ATR_BUFFER" if structural_stop is not None else "ATR_FALLBACK_LOWER_CONFIDENCE", "invalidation_source": levels.get("invalidation_source"), "take_profit_1": tp1, "take_profit_2": target, "target_source": target_source, "risk_distance": risk, "reward_distance": reward, "available_space": space, "available_space_atr": space_atr, "real_rr": real_rr, "rr_tp1": (reward * TP1_FRACTION) / risk if risk > 0 else 0.0, "rr_tp2": real_rr, "asymmetric_payoff": real_rr >= MIN_RR, "rr_minimum": MIN_RR, "stop_distance_atr": stop_atr, "risk_buffer_atr": RISK_ATR_BUFFER, "structural_breach": structural_breached}
            support += [f"entry={entry:.6f}", f"structural_stop={structural_stop if structural_stop is not None else 'NONE'}", f"final_stop={stop:.6f}", f"target={target:.6f}", f"target_source={target_source}", f"available_space_atr={space_atr:.3f}", f"real_rr={real_rr:.3f}", f"stop_distance_atr={stop_atr:.3f}"]
            if real_rr < MIN_RR: counter.append("REAL_RR_BELOW_MINIMUM")

    # 8E: only liquidity that can actually interfere with the path is a blocker.
    liquidity = levels.get("liquidity_event_level") if levels else None
    target = plan.get("take_profit_2")
    liquidity_on_path = liquidity is not None and target is not None and min(entry, target) < liquidity < max(entry, target)
    if liquidity_on_path:
        liquidity_r = abs(liquidity - entry) / max(plan.get("risk_distance", atr), 1e-9)
        plan["opposing_liquidity"], plan["opposing_liquidity_r"] = liquidity, liquidity_r
        if liquidity_r <= MAX_LIQUIDITY_RISK_R: counter.append("OPPOSING_LIQUIDITY_PATH_RISK")
        if liquidity_quality["externality"] == "EXTERNAL": counter.append("EXTERNAL_LIQUIDITY_PATH_RISK")
        elif liquidity_quality["externality"] == "INTERNAL": support.append("internal_liquidity_has_lower_weight")
    else:
        plan["opposing_liquidity"], plan["opposing_liquidity_r"] = None, None
    # Pending/low-information auction is material only when the event is the target/path barrier.
    if liquidity_on_path and liquidity_quality["auction_state"] == "PENDING": counter.append("LIQUIDITY_AUCTION_NOT_TERMINALLY_CONFIRMED")
    if liquidity_on_path and liquidity_quality["information"] == "LOW_INFORMATION": counter.append("LOW_INFORMATION_LIQUIDITY_EVENT")

    # 8F: reconcile E5's directional free-space estimate with E8's own structural path.
    e5_long, e5_short = _num(e5.get("available_space_atr_long")), _num(e5.get("available_space_atr_short"))
    e5_space = e5_long if direction == "BUY" else e5_short if direction == "SELL" else 0.0
    computed_space = plan.get("available_space_atr", 0.0)
    if e5_space > 0:
        plan["e5_available_space_atr"] = e5_space
        plan["space_consistency_delta_atr"] = computed_space - e5_space
        effective_space = min(computed_space, e5_space) if computed_space > 0 else e5_space
    else:
        effective_space = computed_space
    plan["effective_available_space_atr"] = effective_space
    if effective_space < MIN_SPACE_ATR: counter.append("EFFECTIVE_SPACE_BELOW_MINIMUM")
    if effective_space > 0 and computed_space > 0 and abs(computed_space - effective_space) >= 1.0: counter.append("SPACE_EVIDENCE_CONFLICT")
    e5_reasons = [_text(x) for x in (e5.get("reasons") or [])]
    if "SPACE_CONSTRAINED" in _text(e5.get("finding")) or "LONG_SPACE_CONSTRAINED" in e5_reasons or "SHORT_SPACE_CONSTRAINED" in e5_reasons: counter.append("LOCATION_SPACE_CONSTRAINED")

    # 8G: target is the first credible opposing barrier; never skip a nearer barrier to manufacture RR.
    target_ok = bool(plan) and plan.get("take_profit_2") is not None and effective_space >= MIN_TARGET_CLEARANCE_ATR
    if not target_ok: counter.append("DYNAMIC_TARGET_NOT_USABLE")
    if plan.get("target_source") in {"STRUCTURE_HIGH_20", "STRUCTURE_LOW_20"}: counter.append("TARGET_QUALITY_LOW")

    # 8I: execution must survive current-candle expansion, ATR instability and explicit costs.
    if volatility["state"] == "EXPANSION_EXTREME" or volatility["last_range_atr"] > MAX_LAST_RANGE_ATR: counter.append("VOLATILITY_RISK_HIGH")
    elif volatility["state"] == "EXPANSION": counter.append("VOLATILITY_EXPANSION_RISK")
    if volatility["atr_stability"] == "UNSTABLE": counter.append("ATR_STABILITY_RISK")
    if execution["cost_atr"] > MAX_EXECUTION_COST_ATR: counter.append("EXECUTION_COST_TOO_HIGH")

    space_ok = bool(plan) and effective_space >= MIN_SPACE_ATR
    rr_ok = bool(plan) and plan.get("real_rr", 0.0) >= MIN_RR
    stop_ok = bool(plan) and MIN_STOP_ATR <= plan.get("stop_distance_atr", 0.0) <= MAX_STOP_ATR
    liquidity_ok = not any(x in counter for x in {"OPPOSING_LIQUIDITY_PATH_RISK", "EXTERNAL_LIQUIDITY_PATH_RISK", "LIQUIDITY_AUCTION_NOT_TERMINALLY_CONFIRMED", "LOW_INFORMATION_LIQUIDITY_EVENT"})
    volatility_ok = volatility["state"] not in {"EXPANSION_EXTREME"} and volatility["atr_stability"] == "STABLE"
    execution_ok = execution["cost_atr"] <= MAX_EXECUTION_COST_ATR

    critical = {"RISK_DATA_INVALID", "NO_VALID_DIRECTION", "VALID_SETUP_THESIS", "ENTRY_CONFIRMATION", "STRUCTURAL_INVALIDATION_BREACHED", "STOP_TOO_TIGHT_FOR_VOLATILITY", "STOP_TOO_WIDE_FOR_ECONOMICS", "NO_USABLE_STRUCTURAL_TARGET", "AVAILABLE_SPACE_BELOW_MINIMUM", "EFFECTIVE_SPACE_BELOW_MINIMUM", "SPACE_EVIDENCE_CONFLICT", "REAL_RR_BELOW_MINIMUM", "OPPOSING_LIQUIDITY_PATH_RISK", "EXTERNAL_LIQUIDITY_PATH_RISK", "LOCATION_SPACE_CONSTRAINED", "VOLATILITY_RISK_HIGH", "ATR_STABILITY_RISK", "EXECUTION_COST_TOO_HIGH", "DYNAMIC_TARGET_NOT_USABLE", "TARGET_QUALITY_LOW", "LIQUIDITY_AUCTION_NOT_TERMINALLY_CONFIRMED", "LOW_INFORMATION_LIQUIDITY_EVENT"}
    counter, missing = list(dict.fromkeys(counter)), list(dict.fromkeys(missing))
    hard_failure = any(x in critical for x in counter) or bool(missing)
    economics_ready = data_valid and direction in {"BUY", "SELL"} and bool(plan) and target_ok and space_ok and rr_ok and stop_ok and liquidity_ok and volatility_ok and execution_ok and not missing and not hard_failure
    if economics_ready: economic_state = "ATTRACTIVE"
    elif plan and any(x in counter for x in critical): economic_state = "UNATTRACTIVE"
    elif plan: economic_state = "CONDITIONAL"
    else: economic_state = "UNRESOLVED"
    risk_ready = economics_ready
    score = 95.0 if risk_ready else 65.0 if economic_state == "CONDITIONAL" else 30.0 if economic_state == "UNATTRACTIVE" else 15.0

    output = {**base, "state": economic_state, "economic_state": economic_state, "risk_gate": "RISK_READY" if risk_ready else "RISK_NOT_READY", "direction": direction, "setup": setup, "confirmation": confirmation, "confirmation_trace": confirmation_trace, "trade_plan": plan, "risk_model": {"atr": atr, "atr_period": ATR_PERIOD, "volatility_state": volatility["state"], "last_range_atr": volatility.get("last_range_atr", 0.0), "expansion_ratio": volatility.get("expansion_ratio", 0.0), "atr_stability": volatility.get("atr_stability"), "spread": execution["spread"], "slippage": execution["slippage"], "execution_cost_atr": execution["cost_atr"], "structure_lookback": STRUCTURE_LOOKBACK, "min_stop_atr": MIN_STOP_ATR, "max_stop_atr": MAX_STOP_ATR, "min_space_atr": MIN_SPACE_ATR, "risk_buffer_atr": RISK_ATR_BUFFER, "max_liquidity_risk_r": MAX_LIQUIDITY_RISK_R, "max_execution_cost_atr": MAX_EXECUTION_COST_ATR}, "structural_evidence": {**levels, "structural_breached": structural_breached}, "liquidity_evidence": liquidity_quality, "location_evidence": {"structural_location": _text(e5.get("structural_location")), "e5_available_space_long_atr": e5_long, "e5_available_space_short_atr": e5_short, "effective_available_space_atr": effective_space}, "gate_matrix": {"8A_data_integrity": "PASS" if data_valid else "FAIL", "8B_direction_validation": "PASS" if direction in {"BUY", "SELL"} else "FAIL", "8C_setup_confirmation_gate": "PASS" if confirmation == "CONFIRMED" else "FAIL", "8D_structural_invalidation": "FAIL" if structural_breached else "PASS" if structural is not None and plan.get("structural_stop") is not None else "PASS_FALLBACK_ATR" if plan else "FAIL", "8E_liquidity_risk": "PASS" if liquidity_ok else "FAIL", "8F_available_space": "PASS" if space_ok and "SPACE_EVIDENCE_CONFLICT" not in counter else "FAIL", "8G_dynamic_target": "PASS" if target_ok and plan.get("target_source") and "TARGET_QUALITY_LOW" not in counter else "FAIL", "8H_real_rr": "PASS" if rr_ok else "FAIL", "8I_volatility_execution": "PASS" if volatility_ok and execution_ok and stop_ok else "FAIL", "8J_trade_economics": economic_state, "8K_final_risk_gate": "RISK_READY" if risk_ready else "RISK_NOT_READY"}, "supporting_evidence": support, "counter_evidence": counter, "missing_evidence": missing, "invalidation": ["closed-candle structural invalidation", "structural stop becomes economically excessive", "effective available space collapses below minimum", "real RR falls below minimum", "opposing or external liquidity blocks the path to target", "volatility makes the stop non-survivable", "execution cost becomes excessive", "entry confirmation is not proven"], "professional_reasoning": {"8A_data_integrity": "PASS" if data_valid else "FAIL", "8B_direction_validation": "PASS" if direction in {"BUY", "SELL"} else "FAIL", "8C_setup_confirmation_gate": "PASS" if confirmation == "CONFIRMED" else "FAIL", "8D_structural_invalidation": "The protected structural boundary is the thesis invalidation; ATR is only a survival buffer. A closed candle beyond it invalidates the trade thesis.", "8E_liquidity_risk": "Liquidity is evaluated only when it can obstruct the entry-to-target path; internal liquidity carries lower weight than external liquidity.", "8F_available_space": f"computed_space_atr={computed_space:.3f} e5_space_atr={e5_space:.3f} effective_space_atr={effective_space:.3f} minimum={MIN_SPACE_ATR:.3f}", "8G_dynamic_target": f"first_credible_target={plan.get('take_profit_2', 'NONE')} source={plan.get('target_source', 'NONE')}; farther targets are not used to manufacture RR across a nearer barrier.", "8H_real_rr": f"real_rr={plan.get('real_rr', 0.0):.3f} minimum={MIN_RR:.3f}", "8I_volatility_execution": f"volatility={volatility['state']} atr_stability={volatility['atr_stability']} stop_atr={plan.get('stop_distance_atr', 0.0):.3f} execution_cost_atr={execution['cost_atr']:.3f}", "8J_trade_economics": economic_state, "8K_final_risk_gate": "RISK_READY" if risk_ready else "RISK_NOT_READY", "decision_path": "E8 validates survivability/economics only; E9 retains final trade authority."}}
    reasons = () if risk_ready else tuple(counter + missing or ["ECONOMICS_NOT_READY"])
    return EngineResult("E8", NAME, risk_ready, score, output, reasons)
