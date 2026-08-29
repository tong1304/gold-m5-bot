from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Trade Economics & Risk Brain"
QUESTION = "Is the proposed trade economically attractive and structurally survivable?"
ARCHITECTURE = "E8_PROFESSIONAL_TRADE_ECONOMICS_RISK_BRAIN_V3"
VERSION = "3.0"
MIN_BARS = 30
MIN_RR = 1.50
ATR_PERIOD = 14
RISK_ATR_BUFFER = 1.20
STRUCTURE_LOOKBACK = 20
MIN_STOP_ATR = 0.50
MAX_STOP_ATR = 3.50


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
                if value == value:
                    return value
            except (TypeError, ValueError):
                pass
    return None


def _direction(e6: dict[str, Any]) -> str:
    # Direction belongs to E6. E8 validates it; it never derives a new thesis.
    raw = e6.get("direction")
    if raw is None:
        raw = e6.get("direction_thesis")
    t = _text(raw)
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
    finding = str(e6.get("finding") or "")
    if finding:
        parts = finding.split()
        if len(parts) >= 2 and _text(parts[0]) in {"BUY", "SELL"}:
            return parts[1]
    return "UNKNOWN"


def _confirmation(e7: dict[str, Any]) -> tuple[str, list[str]]:
    """Read E7 conservatively across its explicit lifecycle/proof vocabulary."""
    observed: list[str] = []
    for key in ("confirmation", "confirmation_state", "lifecycle", "trigger_state", "proof_state", "state"):
        value = e7.get(key)
        if value not in (None, ""):
            observed.append(_text(value))
    for key in ("confirmed", "confirmation_proven", "trigger_valid", "closed_candle_confirmed"):
        if key in e7:
            observed.append("CONFIRMED" if bool(e7[key]) else "NOT_CONFIRMED")
    if any(x in {"CONFIRMED", "PROVEN", "CONFIRMATION_PROVEN", "VALID", "VALIDATED"} for x in observed):
        return "CONFIRMED", observed
    if any(x in {"PENDING", "INCOMPLETE", "NOT_CONFIRMED", "UNCONFIRMED", "HYPOTHESIS", "UNRESOLVED"} for x in observed):
        return "NOT_CONFIRMED", observed
    # E7's reason codes are stronger evidence than a missing optional output field.
    reasons = [_text(x) for x in (e7.get("reason_codes") or e7.get("reasons") or [])]
    if any(x in {"CONFIRMATION_PROVEN", "CAUSAL_FOLLOW_THROUGH_PROVEN"} for x in reasons):
        return "CONFIRMED", observed + reasons
    if any(x in {"PROOF_GATES_INCOMPLETE", "VALID_CLOSED_CANDLE_TRIGGER_MISSING", "LIQUIDITY_RECLAIM_LEVEL_REQUIRED"} for x in reasons):
        return "NOT_CONFIRMED", observed + reasons
    return "NOT_CONFIRMED", observed + reasons


def _atr(bars: list[dict[str, Any]], period: int = ATR_PERIOD) -> float:
    trs: list[float] = []
    start = max(1, len(bars) - period)
    for i in range(start, len(bars)):
        h = _num(bars[i].get("high")); l = _num(bars[i].get("low")); pc = _num(bars[i - 1].get("close"))
        if h > 0 and l >= 0 and pc > 0:
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return mean(trs) if trs else 0.0


def _levels(e3: dict[str, Any], e4: dict[str, Any], e5: dict[str, Any], bars: list[dict[str, Any]], direction: str) -> dict[str, Any]:
    highs = [_num(x.get("high")) for x in bars[-STRUCTURE_LOOKBACK:] if _num(x.get("high")) > 0]
    lows = [_num(x.get("low")) for x in bars[-STRUCTURE_LOOKBACK:] if _num(x.get("low")) > 0]
    hi20, lo20 = (max(highs), min(lows)) if highs and lows else (None, None)
    ph = _first_num(e3, ("protected_high", "external_protected_high", "internal_protected_high"))
    pl = _first_num(e3, ("protected_low", "external_protected_low", "internal_protected_low"))
    resistance = _first_num(e5, ("next_resistance", "nearest_resistance", "resistance"))
    support = _first_num(e5, ("next_support", "nearest_support", "support"))
    liquidity = _first_num(e4, ("event_level", "liquidity_level", "nearest_liquidity", "opposing_liquidity_level"))
    if direction == "BUY":
        candidates = [x for x in (resistance, ph, liquidity, hi20) if x is not None and x > 0]
        target = min(x for x in candidates if x > 0) if candidates else None
        stop_candidates = [x for x in (pl,) if x is not None and x > 0]
        invalidation = max(stop_candidates) if stop_candidates else lo20
    else:
        candidates = [x for x in (support, pl, liquidity, lo20) if x is not None and x > 0]
        target = max(x for x in candidates if x > 0) if candidates else None
        stop_candidates = [x for x in (ph,) if x is not None and x > 0]
        invalidation = min(stop_candidates) if stop_candidates else hi20
    return {"protected_high": ph, "protected_low": pl, "next_resistance": resistance, "next_support": support, "liquidity_level": liquidity, "structure_high_20": hi20, "structure_low_20": lo20, "nearest_opposing_level": target, "structural_invalidation": invalidation}


def analyze_e8(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """E8 independently audits survivability/economics; E9 retains final trade authority."""
    bars = list(snapshot.get("bars") or [])
    e3, e4, e5, e6, e7 = (_evidence(upstream.get(k)) for k in ("E3", "E4", "E5", "E6", "E7"))
    base = {"architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION, "reasoning_role": "TRADE_ECONOMICS_RISK_ANALYST", "decision_authority": "E9", "trade_decision_authority": False, "closed_candle_only": True, "lookahead": False}
    if len(bars) < MIN_BARS:
        return EngineResult("E8", NAME, False, 0.0, {**base, "state": "UNRESOLVED", "economic_state": "UNRESOLVED", "risk_gate": "RISK_NOT_READY", "trade_plan": {}, "supporting_evidence": [], "counter_evidence": ["INSUFFICIENT_CLOSED_CANDLE_DATA"], "missing_evidence": ["SUFFICIENT_RISK_SAMPLE"]}, ("INSUFFICIENT_DATA",))

    direction = _direction(e6)
    setup = _setup(e6)
    confirmation, confirmation_trace = _confirmation(e7)
    atr = _atr(bars)
    entry = _num(bars[-1].get("close"))
    counter: list[str] = []
    missing: list[str] = []
    support: list[str] = []
    levels = _levels(e3, e4, e5, bars, direction) if direction in {"BUY", "SELL"} else {}
    plan: dict[str, Any] = {}

    if atr <= 0 or entry <= 0: counter.append("RISK_DATA_INVALID")
    if direction not in {"BUY", "SELL"}: counter.append("NO_VALID_DIRECTION")
    if confirmation != "CONFIRMED": missing.append("ENTRY_CONFIRMATION")
    if setup.upper() in {"UNKNOWN", "NONE", "UNRESOLVED"}: missing.append("VALID_SETUP_THESIS")

    if direction in {"BUY", "SELL"} and atr > 0 and entry > 0:
        structural = levels.get("structural_invalidation")
        if direction == "BUY":
            if structural is not None and structural < entry:
                stop = min(structural, entry - RISK_ATR_BUFFER * atr)
            else:
                stop = entry - RISK_ATR_BUFFER * atr
        else:
            if structural is not None and structural > entry:
                stop = max(structural, entry + RISK_ATR_BUFFER * atr)
            else:
                stop = entry + RISK_ATR_BUFFER * atr
        risk = abs(entry - stop)
        stop_atr = risk / atr
        if stop_atr < MIN_STOP_ATR: counter.append("STOP_TOO_TIGHT_FOR_VOLATILITY")
        if stop_atr > MAX_STOP_ATR: counter.append("STOP_TOO_WIDE_FOR_ECONOMICS")
        target = levels.get("nearest_opposing_level")
        if target is None or (direction == "BUY" and target <= entry) or (direction == "SELL" and target >= entry):
            counter.append("NO_USABLE_STRUCTURAL_TARGET")
        else:
            reward = abs(target - entry)
            rr = reward / risk if risk > 0 else 0.0
            tp1 = entry + reward * 0.50 if direction == "BUY" else entry - reward * 0.50
            plan = {"valid": True, "entry": entry, "stop_loss": stop, "take_profit_1": tp1, "take_profit_2": target, "risk_distance": risk, "reward_distance": reward, "real_rr": rr, "rr_tp2": rr, "structural_space_r": rr, "rr_minimum": MIN_RR, "target_type": "STRUCTURAL_OR_LIQUIDITY", "target_level": target, "structural_invalidation": structural, "stop_distance_atr": stop_atr, "risk_buffer_atr": RISK_ATR_BUFFER}
            support += [f"atr={atr:.6f}", f"risk_distance={risk:.6f}", f"reward_distance={reward:.6f}", f"real_rr={rr:.3f}", f"stop_distance_atr={stop_atr:.3f}"]
            if rr < MIN_RR: counter.append("REAL_RR_BELOW_MINIMUM")

    liq = levels.get("liquidity_level") if levels else None
    target = plan.get("take_profit_2")
    if liq is not None and target is not None and min(entry, target) < liq < max(entry, target):
        distance_r = abs(liq - entry) / max(plan.get("risk_distance", atr), 1e-9)
        if distance_r < MIN_RR: counter.append("OPPOSING_LIQUIDITY_TOO_CLOSE")

    location = _text(e5.get("structural_location"))
    if "SPACE_CONSTRAINED" in _text(e5.get("finding")): counter.append("LOCATION_SPACE_CONSTRAINED")

    last_range = max(0.0, _num(bars[-1].get("high")) - _num(bars[-1].get("low")))
    volatility_ratio = last_range / atr if atr > 0 else 999.0
    if volatility_ratio >= 2.5: counter.append("VOLATILITY_RISK_HIGH")

    critical = {"RISK_DATA_INVALID", "NO_VALID_DIRECTION", "ENTRY_CONFIRMATION", "VALID_SETUP_THESIS", "STOP_TOO_TIGHT_FOR_VOLATILITY", "STOP_TOO_WIDE_FOR_ECONOMICS", "NO_USABLE_STRUCTURAL_TARGET", "REAL_RR_BELOW_MINIMUM", "OPPOSING_LIQUIDITY_TOO_CLOSE", "LOCATION_SPACE_CONSTRAINED", "VOLATILITY_RISK_HIGH"}
    counter = list(dict.fromkeys(counter)); missing = list(dict.fromkeys(missing))
    risk_ready = bool(plan) and not missing and not any(x in critical for x in counter)
    if risk_ready: economic = "ATTRACTIVE"
    elif plan and any(x in counter for x in {"REAL_RR_BELOW_MINIMUM", "NO_USABLE_STRUCTURAL_TARGET", "STOP_TOO_WIDE_FOR_ECONOMICS", "STOP_TOO_TIGHT_FOR_VOLATILITY"}): economic = "UNATTRACTIVE"
    elif plan: economic = "CONDITIONAL"
    else: economic = "UNRESOLVED"
    gate = risk_ready and confirmation == "CONFIRMED" and direction in {"BUY", "SELL"}
    score = 95.0 if gate else 65.0 if economic == "CONDITIONAL" else 30.0 if economic == "UNATTRACTIVE" else 15.0
    output = {**base, "state": economic, "economic_state": economic, "risk_gate": "RISK_READY" if gate else "RISK_NOT_READY", "direction": direction, "setup": setup, "confirmation": confirmation, "confirmation_trace": confirmation_trace, "trade_plan": plan, "risk_model": {"atr": atr, "atr_period": ATR_PERIOD, "last_range_atr": volatility_ratio, "structure_lookback": STRUCTURE_LOOKBACK, "min_stop_atr": MIN_STOP_ATR, "max_stop_atr": MAX_STOP_ATR}, "structural_evidence": levels, "location_evidence": {"structural_location": location}, "supporting_evidence": support, "counter_evidence": counter, "missing_evidence": missing, "invalidation": ["closed-candle structural invalidation", "real RR below minimum", "opposing liquidity blocks target", "available space collapses", "volatility becomes materially abnormal"], "professional_reasoning": {"8A_data_integrity": "PASS" if "RISK_DATA_INVALID" not in counter else "FAIL", "8B_direction_validation": "PASS" if direction in {"BUY", "SELL"} else "FAIL", "8C_setup_confirmation_gate": "PASS" if confirmation == "CONFIRMED" else "FAIL", "8D_structural_invalidation": "PASS" if levels.get("structural_invalidation") is not None else "FAIL", "8E_liquidity_risk": "PASS" if "OPPOSING_LIQUIDITY_TOO_CLOSE" not in counter else "FAIL", "8F_available_space": "PASS" if plan.get("structural_space_r", 0) >= MIN_RR else "FAIL", "8G_dynamic_target": "PASS" if plan.get("target_type") == "STRUCTURAL_OR_LIQUIDITY" else "FAIL", "8H_real_rr": "PASS" if plan.get("real_rr", 0) >= MIN_RR else "FAIL", "8I_volatility_execution": "PASS" if not any(x in counter for x in {"VOLATILITY_RISK_HIGH", "STOP_TOO_TIGHT_FOR_VOLATILITY", "STOP_TOO_WIDE_FOR_ECONOMICS"}) else "FAIL", "8J_trade_economics": economic, "8K_final_risk_gate": "RISK_READY" if gate else "RISK_NOT_READY", "decision_path": "E8 validates risk/economics; E9 retains final trade authority."}}
    reasons = () if gate else tuple(counter + missing or ["ECONOMICS_NOT_READY"])
    return EngineResult("E8", NAME, gate, score, output, reasons)
