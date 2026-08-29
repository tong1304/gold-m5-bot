from __future__ import annotations

from statistics import mean, median
from typing import Any

from .contracts import EngineResult

NAME = "Trade Economics & Risk Brain"
QUESTION = "Is the proposed trade economically attractive and structurally survivable?"
ARCHITECTURE = "E8_PROFESSIONAL_TRADE_ECONOMICS_RISK_BRAIN_V21"
VERSION = "21.0"

# E8 is an economic/risk gate, not a setup generator.
MIN_BARS = 30
ATR_PERIOD = 14
MIN_RR = 1.50
MIN_STOP_ATR = 0.50
MAX_STOP_ATR = 3.50
RISK_ATR_BUFFER = 0.20
FALLBACK_STOP_ATR = 1.20
STRUCTURE_LOOKBACK = 20
MAE_LOOKBACK = 20
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
SENSITIVITY_ENTRY_ATR = 0.20
SENSITIVITY_STOP_ATR = 0.20
SENSITIVITY_TARGET_ATR = 0.20
SPACE_CONFLICT_ATR = 0.75


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
    return ("CONFIRMED" if any(x in {"CONFIRMED", "PROVEN", "VALIDATED"} for x in trace) else "NOT_CONFIRMED"), trace + reasons


def _atr(bars: list[dict[str, Any]], period: int = ATR_PERIOD) -> float:
    trs: list[float] = []
    start = max(1, len(bars) - period)
    for i in range(start, len(bars)):
        h, l = _num(bars[i].get("high")), _num(bars[i].get("low"))
        pc = _num(bars[i - 1].get("close"))
        if h > 0 and l >= 0 and pc > 0:
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return mean(trs) if trs else 0.0


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
        ("RESISTANCE", levels.get("next_resistance"), 92.0, 1),
        ("PROTECTED_HIGH", levels.get("protected_high"), 90.0, 2),
        ("LIQUIDITY_EVENT", levels.get("liquidity_event_level"), 80.0, 3),
        ("STRUCTURE_HIGH_20", levels.get("structure_high_20"), 70.0, 4),
    ] if direction == "BUY" else [
        ("SUPPORT", levels.get("next_support"), 92.0, 1),
        ("PROTECTED_LOW", levels.get("protected_low"), 90.0, 2),
        ("LIQUIDITY_EVENT", levels.get("liquidity_event_level"), 80.0, 3),
        ("STRUCTURE_LOW_20", levels.get("structure_low_20"), 70.0, 4),
    ] if direction == "SELL" else [])
    candidates = []
    for source, level, quality, rank in raw:
        if level is None or not (level > entry if direction == "BUY" else level < entry):
            continue
        d, da, rejection = abs(level - entry), abs(level - entry) / max(atr, 1e-9), []
        if da < MIN_TARGET_CLEARANCE_ATR:
            rejection.append("CLEARANCE_TOO_SMALL")
        if da > MAX_TARGET_EXTENSION_ATR:
            rejection.append("EXTENSION_TOO_FAR")
        if source.startswith("STRUCTURE_"):
            quality = min(quality, 62.0)
        if source == "LIQUIDITY_EVENT":
            ext, state, info = _text(e4.get("liquidity_externality")), _text(e4.get("auction_state")), _text(e4.get("auction_information"))
            if ext == "EXTERNAL": quality += 5
            elif ext == "INTERNAL": quality -= 10
            if state == "PENDING": rejection.append("AUCTION_PENDING")
            if info == "LOW_INFORMATION": rejection.append("LOW_INFORMATION_LIQUIDITY")
        quality = max(0.0, min(100.0, quality))
        candidates.append({"hierarchy_rank": rank, "source": source, "level": level, "distance": d, "distance_atr": da, "quality": quality, "credible": quality >= TARGET_QUALITY_MIN and not rejection, "rejection": rejection})
    credible = [x for x in candidates if x["credible"]]
    if not credible:
        return {"source": None, "level": None, "distance": 0.0, "distance_atr": 0.0, "quality": 0.0, "hierarchy_rank": None, "credible": False, "rejection": ["NO_CREDIBLE_OPPOSING_BARRIER"], "candidate_trace": candidates, "selection_rule": "HIERARCHY_THEN_NEAREST_CREDIBLE_BARRIER"}
    return {**min(credible, key=lambda x: (x["hierarchy_rank"], x["distance"])), "candidate_trace": candidates, "selection_rule": "HIERARCHY_THEN_NEAREST_CREDIBLE_BARRIER"}


def _space(e5: dict[str, Any], target: dict[str, Any], direction: str) -> dict[str, Any]:
    key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short"
    e5_space = _num(e5.get(key)) if e5.get(key) is not None else 0.0
    target_space = _num(target.get("distance_atr")) if target.get("credible") else 0.0
    vals = [v for v in (e5_space, target_space) if v > 0]
    if not vals:
        return {"state": "UNAVAILABLE", "e5_available_space_atr": e5_space, "target_barrier_space_atr": target_space, "effective_available_space_atr": 0.0, "space_consistency_delta_atr": None, "space_source": "NO_USABLE_SPACE_EVIDENCE", "space_ok": False, "space_conflict": False}
    effective, delta = min(vals), abs(e5_space - target_space) if e5_space > 0 and target_space > 0 else None
    conflict = delta is not None and delta >= SPACE_CONFLICT_ATR
    state = "CONFLICTED" if conflict else ("CONSTRAINED" if effective < MIN_SPACE_ATR else "USABLE")
    return {"state": state, "e5_available_space_atr": e5_space, "target_barrier_space_atr": target_space, "effective_available_space_atr": effective, "space_consistency_delta_atr": delta, "space_source": "MIN(E5_LOCATION,TARGET_BARRIER)" if len(vals) == 2 else "AVAILABLE_EVIDENCE", "space_ok": state == "USABLE", "space_conflict": conflict}


def _stop(direction: str, entry: float, atr: float, levels: dict[str, Any]) -> dict[str, Any]:
    candidates = ([
        ("PROTECTED_LOW", levels.get("protected_low"), 100.0), ("STRUCTURE_LOW_20", levels.get("structure_low_20"), 80.0)
    ] if direction == "BUY" else [
        ("PROTECTED_HIGH", levels.get("protected_high"), 100.0), ("STRUCTURE_HIGH_20", levels.get("structure_high_20"), 80.0)
    ] if direction == "SELL" else [])
    candidates = [x for x in candidates if x[1] is not None and ((direction == "BUY" and x[1] < entry) or (direction == "SELL" and x[1] > entry))]
    if not candidates:
        fallback = entry - FALLBACK_STOP_ATR * atr if direction == "BUY" else entry + FALLBACK_STOP_ATR * atr
        return {"source": None, "level": None, "stop": fallback, "basis": "ATR_FALLBACK_LOWER_CONFIDENCE", "quality": 0.0, "candidate_trace": [], "structural": False}
    source, level, quality = min(candidates, key=lambda x: abs(entry - x[1]))
    stop = level - RISK_ATR_BUFFER * atr if direction == "BUY" else level + RISK_ATR_BUFFER * atr
    return {"source": source, "level": level, "stop": stop, "basis": "STRUCTURAL_LEVEL_PLUS_ATR_BUFFER", "quality": quality, "candidate_trace": candidates, "structural": True}


def _survival(bars: list[dict[str, Any]], entry: float, direction: str, atr: float, risk: float) -> dict[str, Any]:
    window = bars[-min(len(bars), MAE_LOOKBACK):]
    if not window or atr <= 0:
        return {"state": "UNAVAILABLE", "max_adverse_excursion_atr": None, "median_adverse_excursion_atr": None, "p95_adverse_excursion_atr": None, "survival_margin_atr": None, "window_bars": 0}
    adverse = []
    for b in window:
        adverse_price = max(0.0, entry - _num(b.get("low"))) if direction == "BUY" else max(0.0, _num(b.get("high")) - entry)
        adverse.append(adverse_price / atr)
    adverse.sort()
    p95 = adverse[min(len(adverse) - 1, int((len(adverse) - 1) * 0.95))]
    margin = risk / max(atr, 1e-9) - p95
    state = "ROBUST" if margin >= MIN_SURVIVAL_MARGIN_ATR else ("FRAGILE" if margin >= 0 else "NON_SURVIVABLE")
    return {"state": state, "max_adverse_excursion_atr": max(adverse), "median_adverse_excursion_atr": median(adverse), "p95_adverse_excursion_atr": p95, "survival_margin_atr": margin, "window_bars": len(window)}


def _execution(snapshot: dict[str, Any], atr: float) -> dict[str, Any]:
    spread = _first_num(snapshot, ("spread", "spread_price", "current_spread")) or 0.0
    slippage = _first_num(snapshot, ("slippage", "slippage_price", "expected_slippage")) or 0.0
    total = max(0.0, spread + slippage)
    return {"spread": spread, "slippage": slippage, "total_cost": total, "cost_atr": total / atr if atr > 0 else float("inf")}


def _probability(e7: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    for source in (e7, snapshot):
        for key in ("historical_probability", "win_probability", "probability", "estimated_probability"):
            if key in source:
                p = _num(source.get(key), -1.0)
                if p > 1.0: p /= 100.0
                if 0.0 < p <= 1.0:
                    q = _num(source.get("probability_quality"), 0.0)
                    n = int(_num(source.get("probability_sample"), 0.0))
                    trusted = q >= MIN_PROBABILITY_QUALITY and n >= MIN_PROBABILITY_SAMPLE
                    return {"state": "TRUSTED" if trusted else "UNTRUSTED", "probability": p, "quality": q, "sample": n, "source": key, "stress_probability": max(0.0, p - PROBABILITY_STRESS), "trusted": trusted}
    return {"state": "UNQUANTIFIED", "probability": None, "quality": None, "sample": None, "source": None, "stress_probability": None, "trusted": False}


def _economic(rr: float, p: dict[str, Any], cost_atr: float, survival: dict[str, Any], space: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if rr < MIN_RR: reasons.append("REAL_RR_BELOW_MINIMUM")
    if cost_atr > MAX_EXECUTION_COST_ATR: reasons.append("EXECUTION_COST_TOO_HIGH")
    if survival["state"] in {"NON_SURVIVABLE", "UNAVAILABLE"}: reasons.append("STRUCTURAL_SURVIVAL_NOT_PROVEN")
    if survival["state"] == "FRAGILE": reasons.append("SURVIVAL_FRAGILE")
    if space["state"] in {"UNAVAILABLE", "CONFLICTED"}: reasons.append("EFFECTIVE_SPACE_UNRELIABLE")
    elif space["effective_available_space_atr"] < MIN_SPACE_ATR: reasons.append("EFFECTIVE_SPACE_BELOW_MINIMUM")
    ev = None
    if p.get("trusted") and p.get("stress_probability") is not None:
        prob = p["stress_probability"]
        effective_reward = max(0.0, rr - cost_atr)
        effective_risk = 1.0 + cost_atr
        ev = prob * effective_reward - (1.0 - prob) * effective_risk
        if ev < MIN_ECONOMIC_EDGE: reasons.append("PROBABILITY_EDGE_NOT_POSITIVE")
    else:
        reasons.append("PROBABILITY_EDGE_NOT_TRUSTWORTHY")
    if not p.get("trusted"):
        state = "NOT_EVALUABLE"
    elif any(x in reasons for x in ("REAL_RR_BELOW_MINIMUM", "EFFECTIVE_SPACE_BELOW_MINIMUM", "STRUCTURAL_SURVIVAL_NOT_PROVEN", "EFFECTIVE_SPACE_UNRELIABLE")):
        state = "ECONOMICALLY_INVALID"
    elif reasons:
        state = "FRAGILE"
    else:
        state = "ECONOMICALLY_ACCEPTABLE"
    return {"state": state, "expected_value_r": ev, "economic_edge_r": ev, "rr_used": rr, "stress_probability": p.get("stress_probability"), "reasons": reasons}


def _sensitivity(direction: str, entry: float, stop: float, target: float, atr: float, probability: dict[str, Any], cost_atr: float) -> dict[str, Any]:
    p = probability.get("stress_probability")
    if atr <= 0 or p is None: return {"state": "UNQUANTIFIED"}
    def ev(e: float, s: float, t: float) -> float:
        r = abs(t - e) / max(abs(e - s), 1e-9)
        return p * max(0.0, r - cost_atr) - (1.0 - p) * (1.0 + cost_atr)
    entry_worse = entry + (SENSITIVITY_ENTRY_ATR * atr if direction == "BUY" else -SENSITIVITY_ENTRY_ATR * atr)
    stop_worse = stop - (SENSITIVITY_STOP_ATR * atr if direction == "BUY" else -SENSITIVITY_STOP_ATR * atr)
    target_worse = target - (SENSITIVITY_TARGET_ATR * atr if direction == "BUY" else -SENSITIVITY_TARGET_ATR * atr)
    vals = [ev(entry_worse, stop, target), ev(entry, stop_worse, target), ev(entry, stop, target_worse)]
    return {"state": "ROBUST" if min(vals) >= 0 else "FRAGILE", "base": ev(entry, stop, target), "entry_worse": vals[0], "stop_worse": vals[1], "target_worse": vals[2], "worst_case": min(vals)}


def analyze_e8(snapshot: dict[str, Any], results: dict[str, EngineResult]) -> EngineResult:
    bars = list(snapshot.get("bars") or [])
    e3, e4, e5, e6, e7 = (_evidence(results, k) for k in ("E3", "E4", "E5", "E6", "E7"))
    reasons: list[str] = []
    direction, setup = _direction(e6), _setup(e6)
    confirmation, confirmation_trace = _confirmation(e7)
    if len(bars) < MIN_BARS:
        reasons.append("INSUFFICIENT_BARS")
        output = {"engine_id": "E8", "role": "TRADE_ECONOMICS_RISK_ANALYST", "question": QUESTION, "architecture": ARCHITECTURE, "version": VERSION, "finding": "UNRESOLVED", "direction": direction, "setup": setup, "confirmation": confirmation, "economic_state": "NOT_EVALUABLE", "gate_passed": False, "risk_ready": False, "observations": [f"valid_candles={len(bars)}"], "reasons": reasons, "reason_codes": reasons}
        return EngineResult("E8", NAME, False, 0.0, output, tuple(reasons))
    atr = _atr(bars)
    entry = _num(snapshot.get("price") or snapshot.get("close") or bars[-1].get("close"))
    if atr <= 0 or entry <= 0 or direction == "NEUTRAL":
        reasons.append("INVALID_ECONOMIC_INPUTS" if atr <= 0 or entry <= 0 else "DIRECTION_UNRESOLVED")
        output = {"engine_id": "E8", "role": "TRADE_ECONOMICS_RISK_ANALYST", "question": QUESTION, "architecture": ARCHITECTURE, "version": VERSION, "finding": "UNRESOLVED", "direction": direction, "setup": setup, "entry": entry, "atr14": atr, "confirmation": confirmation, "economic_state": "NOT_EVALUABLE", "gate_passed": False, "risk_ready": False, "observations": [], "reasons": reasons, "reason_codes": reasons}
        return EngineResult("E8", NAME, False, 0.0, output, tuple(reasons))
    levels = _levels(e3, e4, e5, bars)
    target = _target(levels, direction, entry, atr, e4)
    stop_plan = _stop(direction, entry, atr, levels)
    stop = stop_plan["stop"]
    risk_price = abs(entry - stop)
    risk_atr = risk_price / atr
    if risk_atr < MIN_STOP_ATR: reasons.append("STOP_TOO_TIGHT")
    if risk_atr > MAX_STOP_ATR: reasons.append("STOP_TOO_WIDE")
    target_valid = bool(target.get("credible") and target.get("level") is not None)
    if not target_valid: reasons.append("NO_USABLE_STRUCTURAL_TARGET")
    reward_price = abs(_num(target.get("level")) - entry) if target_valid else 0.0
    rr = reward_price / max(risk_price, 1e-9) if target_valid and risk_price > 0 else 0.0
    space = _space(e5, target, direction)
    if space["state"] == "CONFLICTED": reasons.append("SPACE_CONFLICT")
    execution = _execution(snapshot, atr)
    survival = _survival(bars, entry, direction, atr, risk_price)
    probability = _probability(e7, snapshot)
    economics = _economic(rr, probability, execution["cost_atr"], survival, space)
    sensitivity = _sensitivity(direction, entry, stop, _num(target.get("level")), atr, probability, execution["cost_atr"]) if target_valid else {"state": "UNQUANTIFIED"}
    if confirmation != "CONFIRMED": reasons.append("ENTRY_CONFIRMATION")
    reasons.extend(x for x in economics["reasons"] if x not in reasons)
    if sensitivity.get("state") == "FRAGILE": reasons.append("ECONOMICS_SENSITIVITY_FRAGILE")
    hard_fail = any(x in reasons for x in {"NO_USABLE_STRUCTURAL_TARGET", "REAL_RR_BELOW_MINIMUM", "EFFECTIVE_SPACE_BELOW_MINIMUM", "SPACE_CONFLICT", "STOP_TOO_TIGHT", "STOP_TOO_WIDE", "STRUCTURAL_SURVIVAL_NOT_PROVEN", "EXECUTION_COST_TOO_HIGH", "ENTRY_CONFIRMATION"})
    risk_ready = (confirmation == "CONFIRMED" and target_valid and MIN_STOP_ATR <= risk_atr <= MAX_STOP_ATR and rr >= MIN_RR and space["space_ok"] and survival["state"] == "ROBUST" and execution["cost_atr"] <= MAX_EXECUTION_COST_ATR and probability["trusted"] and economics["state"] == "ECONOMICALLY_ACCEPTABLE" and sensitivity.get("state") == "ROBUST" and not hard_fail)
    if risk_ready:
        finding, gate, confidence = "ECONOMICALLY_ACCEPTABLE", True, min(1.0, 0.5 + max(0.0, economics["economic_edge_r"] or 0.0) * 0.25)
    elif economics["state"] == "NOT_EVALUABLE":
        finding, gate, confidence = "UNRESOLVED", False, 0.0
    else:
        finding, gate, confidence = ("ECONOMICALLY_INVALID" if hard_fail or economics["state"] == "ECONOMICALLY_INVALID" else "FRAGILE"), False, 0.25
    observations = [f"bars={len(bars)}", f"atr14={atr:.6f}", f"entry={entry:.8f}", f"risk_atr={risk_atr:.6f}", f"rr={rr:.6f}", f"target={target.get('source') or 'NONE'}", f"space={space['state']}", f"survival={survival['state']}", f"execution_cost_atr={execution['cost_atr']:.6f}", f"probability={probability.get('probability') if probability.get('probability') is not None else 'UNQUANTIFIED'}", f"economic_state={economics['state']}", f"sensitivity={sensitivity.get('state', 'UNQUANTIFIED')}"]
    trade_plan = {"valid": risk_ready, "direction": direction, "setup": setup, "entry": entry, "stop": stop if risk_ready else None, "target": target.get("level") if risk_ready else None, "risk_price": risk_price, "risk_atr": risk_atr, "reward_price": reward_price, "rr": rr, "target_source": target.get("source"), "stop_source": stop_plan.get("source"), "economic_state": economics["state"], "expected_value_r": economics["expected_value_r"]}
    output = {"engine_id": "E8", "role": "TRADE_ECONOMICS_RISK_ANALYST", "question": QUESTION, "architecture": ARCHITECTURE, "version": VERSION, "finding": finding, "direction": direction, "setup": setup, "confirmation": confirmation, "confirmation_trace": confirmation_trace, "entry": entry, "atr14": atr, "risk_atr": risk_atr, "rr": rr, "real_rr": rr, "target": target, "stop_plan": stop_plan, "space": space, "survival": survival, "execution": execution, "probability": probability, "economics": economics, "sensitivity": sensitivity, "economic_state": economics["state"], "risk_ready": risk_ready, "gate_passed": gate, "trade_plan": trade_plan, "observations": observations, "reasons": reasons, "reason_codes": reasons, "confidence": confidence, "professional_rule": "E8_ECONOMICS_ONLY_E9_FINAL_AUTHORITY"}
    return EngineResult("E8", NAME, gate, confidence * 100.0, output, tuple(reasons))
