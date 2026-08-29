from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Trade Economics & Risk Brain"
QUESTION = "Is the proposed trade economically attractive and structurally survivable?"
ARCHITECTURE = "E8_PROFESSIONAL_TRADE_ECONOMICS_RISK_BRAIN_V4"
VERSION = "4.0"
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
    raw = e6.get("direction", e6.get("direction_thesis"))
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
    parts = finding.split()
    if len(parts) >= 2 and _text(parts[0]) in {"BUY", "SELL"}:
        return parts[1]
    return "UNKNOWN"


def _confirmation(e7: dict[str, Any]) -> tuple[str, list[str]]:
    """E7 is the confirmation authority; E8 only consumes explicit proof state."""
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
        # Do not treat a trigger observation as confirmation. Only an explicit
        # confirmation gate may make E8 regard entry as proven.
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


def _levels(e3: dict[str, Any], e4: dict[str, Any], e5: dict[str, Any], bars: list[dict[str, Any]], direction: str, entry: float) -> dict[str, Any]:
    recent = bars[-STRUCTURE_LOOKBACK:]
    highs = [_num(x.get("high")) for x in recent if _num(x.get("high")) > 0]
    lows = [_num(x.get("low")) for x in recent if _num(x.get("low")) > 0]
    hi20 = max(highs) if highs else None
    lo20 = min(lows) if lows else None

    protected_high = _first_num(e3, ("protected_high", "external_protected_high", "internal_protected_high"))
    protected_low = _first_num(e3, ("protected_low", "external_protected_low", "internal_protected_low"))
    resistance = _first_num(e5, ("next_resistance", "nearest_resistance", "resistance"))
    support = _first_num(e5, ("next_support", "nearest_support", "support"))
    event_level = _first_num(e4, ("event_level", "liquidity_level", "nearest_liquidity", "opposing_liquidity_level"))

    if direction == "BUY":
        target_candidates = [
            ("RESISTANCE", resistance),
            ("PROTECTED_HIGH", protected_high),
            ("LIQUIDITY_EVENT", event_level),
            ("STRUCTURE_HIGH_20", hi20),
        ]
        target_candidates = [(name, level) for name, level in target_candidates if level is not None and level > entry]
        target_name, target = min(target_candidates, key=lambda x: x[1]) if target_candidates else (None, None)
        structural_invalidation = protected_low if protected_low is not None and protected_low < entry else lo20 if lo20 is not None and lo20 < entry else None
    else:
        target_candidates = [
            ("SUPPORT", support),
            ("PROTECTED_LOW", protected_low),
            ("LIQUIDITY_EVENT", event_level),
            ("STRUCTURE_LOW_20", lo20),
        ]
        target_candidates = [(name, level) for name, level in target_candidates if level is not None and level < entry]
        target_name, target = max(target_candidates, key=lambda x: x[1]) if target_candidates else (None, None)
        structural_invalidation = protected_high if protected_high is not None and protected_high > entry else hi20 if hi20 is not None and hi20 > entry else None

    return {
        "protected_high": protected_high,
        "protected_low": protected_low,
        "next_resistance": resistance,
        "next_support": support,
        "liquidity_event_level": event_level,
        "structure_high_20": hi20,
        "structure_low_20": lo20,
        "structural_invalidation": structural_invalidation,
        "target_level": target,
        "target_source": target_name,
    }


def _volatility_state(bars: list[dict[str, Any]], atr: float) -> dict[str, Any]:
    if atr <= 0 or len(bars) < 2:
        return {"state": "INVALID", "last_range_atr": 0.0, "atr_ratio": 0.0}
    last_range = max(0.0, _num(bars[-1].get("high")) - _num(bars[-1].get("low")))
    previous_range = max(0.0, _num(bars[-2].get("high")) - _num(bars[-2].get("low")))
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
    return {"state": state, "last_range_atr": ratio, "expansion_ratio": expansion_ratio}


def analyze_e8(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """E8 audits trade survivability and economics; E9 retains final authority."""
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
        return EngineResult("E8", NAME, False, 0.0, {
            **base, "state": "UNRESOLVED", "economic_state": "UNRESOLVED", "risk_gate": "RISK_NOT_READY",
            "trade_plan": {}, "supporting_evidence": [], "counter_evidence": ["INSUFFICIENT_CLOSED_CANDLE_DATA"],
            "missing_evidence": ["SUFFICIENT_RISK_SAMPLE"],
        }, ("INSUFFICIENT_DATA",))

    direction = _direction(e6)
    setup = _setup(e6)
    confirmation, confirmation_trace = _confirmation(e7)
    entry = _num(bars[-1].get("close"))
    atr = _atr(bars)
    volatility = _volatility_state(bars, atr)

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

    levels = _levels(e3, e4, e5, bars, direction, entry) if data_valid and direction in {"BUY", "SELL"} else {}
    structural = levels.get("structural_invalidation") if levels else None

    # 8D: structural invalidation first, then a small volatility buffer beyond it.
    if data_valid and direction in {"BUY", "SELL"}:
        if direction == "BUY":
            structural_stop = structural if structural is not None and structural < entry else None
            stop = structural_stop - RISK_ATR_BUFFER * atr if structural_stop is not None else entry - FALLBACK_STOP_ATR * atr
            invalidation_basis = "PROTECTED_LOW_PLUS_ATR_BUFFER" if structural_stop is not None else "ATR_FALLBACK"
        else:
            structural_stop = structural if structural is not None and structural > entry else None
            stop = structural_stop + RISK_ATR_BUFFER * atr if structural_stop is not None else entry + FALLBACK_STOP_ATR * atr
            invalidation_basis = "PROTECTED_HIGH_PLUS_ATR_BUFFER" if structural_stop is not None else "ATR_FALLBACK"

        risk = abs(entry - stop)
        stop_atr = risk / atr
        if stop_atr < MIN_STOP_ATR:
            counter.append("STOP_TOO_TIGHT_FOR_VOLATILITY")
        if stop_atr > MAX_STOP_ATR:
            counter.append("STOP_TOO_WIDE_FOR_ECONOMICS")

        target = levels.get("target_level")
        target_source = levels.get("target_source")
        if target is None:
            counter.append("NO_USABLE_STRUCTURAL_TARGET")
        else:
            space = abs(target - entry)
            space_atr = space / atr
            if space_atr < MIN_SPACE_ATR:
                counter.append("AVAILABLE_SPACE_BELOW_MINIMUM")
            reward = space
            real_rr = reward / risk if risk > 0 else 0.0
            tp1 = entry + reward * TP1_FRACTION if direction == "BUY" else entry - reward * TP1_FRACTION
            plan = {
                "valid": True,
                "entry": entry,
                "direction": direction,
                "stop_loss": stop,
                "structural_stop": structural_stop,
                "invalidation_basis": invalidation_basis,
                "take_profit_1": tp1,
                "take_profit_2": target,
                "target_source": target_source,
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
            }
            support += [
                f"entry={entry:.6f}", f"structural_stop={structural_stop if structural_stop is not None else 'NONE'}",
                f"final_stop={stop:.6f}", f"target={target:.6f}", f"target_source={target_source}",
                f"available_space_atr={space_atr:.3f}", f"real_rr={real_rr:.3f}", f"stop_distance_atr={stop_atr:.3f}",
            ]
            if real_rr < MIN_RR:
                counter.append("REAL_RR_BELOW_MINIMUM")

    # 8E: only treat liquidity as a risk obstacle when it lies strictly between
    # entry and the chosen target. A liquidity level that IS the target is not
    # double-counted as an obstacle.
    liquidity = levels.get("liquidity_event_level") if levels else None
    target = plan.get("take_profit_2")
    if liquidity is not None and target is not None:
        between = min(entry, target) < liquidity < max(entry, target)
        if between:
            liquidity_r = abs(liquidity - entry) / max(plan.get("risk_distance", atr), 1e-9)
            plan["opposing_liquidity"] = liquidity
            plan["opposing_liquidity_r"] = liquidity_r
            if liquidity_r < MIN_RR:
                counter.append("OPPOSING_LIQUIDITY_TOO_CLOSE")
        else:
            plan["opposing_liquidity"] = None
            plan["opposing_liquidity_r"] = None

    structural_location = _text(e5.get("structural_location"))
    if "SPACE_CONSTRAINED" in _text(e5.get("finding")) or "LONG_SPACE_CONSTRAINED" in " ".join(str(x) for x in (e5.get("reasons") or [])):
        counter.append("LOCATION_SPACE_CONSTRAINED")

    if volatility["state"] == "EXPANSION_EXTREME":
        counter.append("VOLATILITY_RISK_HIGH")
    elif volatility["state"] == "EXPANSION":
        # Expansion is not automatic rejection, but it makes the economics conditional.
        counter.append("VOLATILITY_EXPANSION_RISK")

    # 8F/8G explicit gate: usable space must exist beyond entry and the target
    # must be reachable before the structural economics are considered.
    space_atr = plan.get("available_space_atr", 0.0)
    space_ok = bool(plan) and space_atr >= MIN_SPACE_ATR
    target_ok = bool(plan) and plan.get("take_profit_2") is not None
    rr_ok = bool(plan) and plan.get("real_rr", 0.0) >= MIN_RR
    stop_ok = bool(plan) and MIN_STOP_ATR <= plan.get("stop_distance_atr", 0.0) <= MAX_STOP_ATR
    liquidity_ok = "OPPOSING_LIQUIDITY_TOO_CLOSE" not in counter
    volatility_ok = volatility["state"] not in {"EXPANSION_EXTREME"}

    critical = {
        "RISK_DATA_INVALID", "NO_VALID_DIRECTION", "VALID_SETUP_THESIS", "ENTRY_CONFIRMATION",
        "STOP_TOO_TIGHT_FOR_VOLATILITY", "STOP_TOO_WIDE_FOR_ECONOMICS", "NO_USABLE_STRUCTURAL_TARGET",
        "AVAILABLE_SPACE_BELOW_MINIMUM", "REAL_RR_BELOW_MINIMUM", "OPPOSING_LIQUIDITY_TOO_CLOSE",
        "LOCATION_SPACE_CONSTRAINED", "VOLATILITY_RISK_HIGH",
    }
    counter = list(dict.fromkeys(counter))
    missing = list(dict.fromkeys(missing))

    # 8J economics distinguishes an invalid trade from a merely conditional one.
    hard_failure = any(x in critical for x in counter) or bool(missing)
    economics_ready = data_valid and direction in {"BUY", "SELL"} and bool(plan) and target_ok and space_ok and rr_ok and stop_ok and liquidity_ok and volatility_ok and not missing and not any(x in critical for x in counter)

    if economics_ready:
        economic_state = "ATTRACTIVE"
    elif plan and any(x in counter for x in {"NO_USABLE_STRUCTURAL_TARGET", "AVAILABLE_SPACE_BELOW_MINIMUM", "REAL_RR_BELOW_MINIMUM", "STOP_TOO_WIDE_FOR_ECONOMICS", "STOP_TOO_TIGHT_FOR_VOLATILITY", "OPPOSING_LIQUIDITY_TOO_CLOSE"}):
        economic_state = "UNATTRACTIVE"
    elif plan:
        economic_state = "CONDITIONAL"
    else:
        economic_state = "UNRESOLVED"

    # 8K is intentionally conjunctive: no single attractive metric can override
    # a missing proof gate, structural invalidation problem, or poor execution economics.
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
            "atr": atr,
            "atr_period": ATR_PERIOD,
            "volatility_state": volatility["state"],
            "last_range_atr": volatility.get("last_range_atr", 0.0),
            "expansion_ratio": volatility.get("expansion_ratio", 0.0),
            "structure_lookback": STRUCTURE_LOOKBACK,
            "min_stop_atr": MIN_STOP_ATR,
            "max_stop_atr": MAX_STOP_ATR,
            "min_space_atr": MIN_SPACE_ATR,
            "risk_buffer_atr": RISK_ATR_BUFFER,
        },
        "structural_evidence": levels,
        "location_evidence": {
            "structural_location": structural_location,
            "e5_available_space_long_atr": _num(e5.get("available_space_atr_long")),
            "e5_available_space_short_atr": _num(e5.get("available_space_atr_short")),
        },
        "gate_matrix": {
            "8A_data_integrity": "PASS" if data_valid else "FAIL",
            "8B_direction_validation": "PASS" if direction in {"BUY", "SELL"} else "FAIL",
            "8C_setup_confirmation_gate": "PASS" if confirmation == "CONFIRMED" else "FAIL",
            "8D_structural_invalidation": "PASS" if structural is not None and plan.get("structural_stop") is not None else "PASS_FALLBACK_ATR" if plan else "FAIL",
            "8E_liquidity_risk": "PASS" if liquidity_ok else "FAIL",
            "8F_available_space": "PASS" if space_ok else "FAIL",
            "8G_dynamic_target": "PASS" if target_ok and plan.get("target_source") else "FAIL",
            "8H_real_rr": "PASS" if rr_ok else "FAIL",
            "8I_volatility_execution": "PASS" if volatility_ok and stop_ok else "FAIL",
            "8J_trade_economics": economic_state,
            "8K_final_risk_gate": "RISK_READY" if risk_ready else "RISK_NOT_READY",
        },
        "supporting_evidence": support,
        "counter_evidence": counter,
        "missing_evidence": missing,
        "invalidation": [
            "closed-candle structural invalidation",
            "structural stop becomes economically excessive",
            "available space collapses below minimum",
            "real RR falls below minimum",
            "opposing liquidity blocks the path to target",
            "volatility makes the stop non-survivable",
            "entry confirmation is not proven",
        ],
        "professional_reasoning": {
            "8A_data_integrity": "PASS" if data_valid else "FAIL",
            "8B_direction_validation": "PASS" if direction in {"BUY", "SELL"} else "FAIL",
            "8C_setup_confirmation_gate": "PASS" if confirmation == "CONFIRMED" else "FAIL",
            "8D_structural_invalidation": "Structural invalidation is the primary stop anchor; ATR is only the survival buffer." if structural is not None else "No valid protected level; ATR fallback is used and treated as lower-quality risk evidence.",
            "8E_liquidity_risk": "Liquidity is a blocker only when it materially obstructs the path from entry to target; the selected target itself is not double-counted as an obstacle.",
            "8F_available_space": f"usable_space_atr={space_atr:.3f} minimum={MIN_SPACE_ATR:.3f}",
            "8G_dynamic_target": f"target_source={plan.get('target_source', 'NONE')} tp1={plan.get('take_profit_1', 'NONE')} tp2={plan.get('take_profit_2', 'NONE')}",
            "8H_real_rr": f"real_rr={plan.get('real_rr', 0.0):.3f} minimum={MIN_RR:.3f}",
            "8I_volatility_execution": f"volatility={volatility['state']} stop_atr={plan.get('stop_distance_atr', 0.0):.3f}",
            "8J_trade_economics": economic_state,
            "8K_final_risk_gate": "RISK_READY" if risk_ready else "RISK_NOT_READY",
            "decision_path": "E8 validates survivability/economics only; E9 retains final trade authority.",
        },
    }

    reasons = () if risk_ready else tuple(counter + missing or ["ECONOMICS_NOT_READY"])
    return EngineResult("E8", NAME, risk_ready, score, output, reasons)
