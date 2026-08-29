from __future__ import annotations

from statistics import mean, median
from typing import Any

from .contracts import EngineResult

NAME = "Trade Economics & Risk Brain"
QUESTION = "Is the proposed trade economically attractive and structurally survivable?"
ARCHITECTURE = "E8_PROFESSIONAL_TRADE_ECONOMICS_RISK_BRAIN_V20"
VERSION = "20.0"

MIN_BARS = 30
ATR_PERIOD = 14
MIN_RR = 1.50
MIN_STOP_ATR = 0.50
MAX_STOP_ATR = 3.50
RISK_ATR_BUFFER = 0.20
FALLBACK_STOP_ATR = 1.20
STRUCTURE_LOOKBACK = 20
MAE_LOOKBACK = 12
MIN_SPACE_ATR = 0.75
MIN_TARGET_CLEARANCE_ATR = 0.10
MAX_TARGET_EXTENSION_ATR = 3.50
TARGET_QUALITY_MIN = 70.0
SECONDARY_TARGET_QUALITY = 62.0
MIN_SURVIVAL_MARGIN_ATR = 0.15
MAX_EXECUTION_COST_ATR = 0.15
MIN_ECONOMIC_EDGE = 0.10
SPACE_CONFLICT_ATR = 0.75
MIN_PROBABILITY = 0.50
MIN_PROBABILITY_QUALITY = 70.0
MIN_PROBABILITY_SAMPLE = 30
MIN_SENSITIVITY_EV = 0.0
SENSITIVITY_ENTRY_ATR = 0.20
SENSITIVITY_STOP_ATR = 0.20
SENSITIVITY_TARGET_ATR = 0.20
PROBABILITY_STRESS = 0.03


def _num(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if x == x else default
    except (TypeError, ValueError):
        return default


def _text(v: Any) -> str:
    return str(v or "").upper().strip()


def _evidence(e: EngineResult | None) -> dict[str, Any]:
    return dict(e.output or {}) if e else {}


def _first_num(m: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        try:
            x = float(m[key])
            if x == x and x > 0:
                return x
        except (KeyError, TypeError, ValueError):
            continue
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
    trace = []
    for key in ("confirmation", "confirmation_state", "trigger_state", "proof_state"):
        if e7.get(key) not in (None, ""):
            trace.append(_text(e7[key]))
    reasons = [_text(x) for x in (e7.get("reason_codes") or e7.get("reasons") or [])]
    if any(x in {"PROOF_GATES_INCOMPLETE", "VALID_CLOSED_CANDLE_TRIGGER_MISSING", "TRIGGER_OBSERVED_NOT_AUTOMATIC_CONFIRMATION", "LIQUIDITY_RECLAIM_LEVEL_REQUIRED"} for x in reasons):
        return "NOT_CONFIRMED", trace + reasons
    if any(x in {"CONFIRMATION_PROVEN", "CAUSAL_FOLLOW_THROUGH_PROVEN"} for x in reasons):
        return "CONFIRMED", trace + reasons
    proof = e7.get("proof_gates")
    if isinstance(proof, dict):
        for key in ("confirmation", "closed_candle_confirmation", "follow_through"):
            value = proof.get(key)
            if value is True or value in {"PASS", "CONFIRMED", "PROVEN", "VALID", "VALIDATED"}:
                trace.append("CONFIRMED")
            elif value is False or value in {"FAIL", "PENDING", "UNAVAILABLE", "NOT_PROVEN"}:
                trace.append("NOT_CONFIRMED")
    for key in ("confirmed", "confirmation_proven", "closed_candle_confirmed"):
        if key in e7:
            trace.append("CONFIRMED" if bool(e7[key]) else "NOT_CONFIRMED")
    return ("CONFIRMED" if any(x in {"CONFIRMED", "PROVEN", "VALIDATED"} for x in trace) else "NOT_CONFIRMED"), trace + reasons


def _atr(bars, period=ATR_PERIOD):
    trs = []
    start = max(1, len(bars) - period)
    for i in range(start, len(bars)):
        h, l, pc = _num(bars[i].get("high")), _num(bars[i].get("low")), _num(bars[i - 1].get("close"))
        if h > 0 and l >= 0 and pc > 0:
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return mean(trs) if trs else 0.0


def _atr_series(bars, period=ATR_PERIOD):
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = _num(bars[i].get("high")), _num(bars[i].get("low")), _num(bars[i - 1].get("close"))
        if h > 0 and l >= 0 and pc > 0:
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return [mean(trs[max(0, i - period + 1):i + 1]) for i in range(len(trs))]


def _levels(e3, e4, e5, bars):
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


def _target(levels, direction, entry, atr, e4):
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
            quality = min(quality, SECONDARY_TARGET_QUALITY)
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


def _space(e5, target, direction):
    key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short"
    e5s = _num(e5.get(key)) if e5.get(key) is not None else 0.0
    ts = _num(target.get("distance_atr")) if target.get("credible") else 0.0
    vals = [v for v in (e5s, ts) if v > 0]
    if not vals:
        return {"state": "UNAVAILABLE", "e5_available_space_atr": e5s, "target_barrier_space_atr": ts, "effective_available_space_atr": 0.0, "space_consistency_delta_atr": None, "space_source": "NO_USABLE_SPACE_EVIDENCE", "space_ok": False, "space_conflict": False}
    effective = min(vals)
    delta = abs(e5s - ts) if e5s > 0 and ts > 0 else None
    conflict = delta is not None and delta >= SPACE_CONFLICT_ATR
    state = "CONFLICTED" if conflict else "CONSTRAINED" if effective < MIN_SPACE_ATR else "USABLE"
    return {"state": state, "e5_available_space_atr": e5s, "target_barrier_space_atr": ts, "effective_available_space_atr": effective, "space_consistency_delta_atr": delta, "space_source": "MIN(E5_LOCATION,TARGET_BARRIER)" if len(vals) == 2 else "AVAILABLE_EVIDENCE", "space_ok": state == "USABLE", "space_conflict": conflict}


def _stop(direction, entry, atr, levels):
    candidates = ([
        ("PROTECTED_LOW", levels.get("protected_low"), 100.0),
        ("STRUCTURE_LOW_20", levels.get("structure_low_20"), 80.0),
    ] if direction == "BUY" else [
        ("PROTECTED_HIGH", levels.get("protected_high"), 100.0),
        ("STRUCTURE_HIGH_20", levels.get("structure_high_20"), 80.0),
    ] if direction == "SELL" else [])
    candidates = [x for x in candidates if x[1] is not None and ((direction == "BUY" and x[1] < entry) or (direction == "SELL" and x[1] > entry))]
    if not candidates:
        fallback = entry - FALLBACK_STOP_ATR * atr if direction == "BUY" else entry + FALLBACK_STOP_ATR * atr
        return {"source": None, "level": None, "stop": fallback, "basis": "ATR_FALLBACK_LOWER_CONFIDENCE", "quality": 0.0, "candidate_trace": [], "structural": False}
    source, level, quality = min(candidates, key=lambda x: abs(entry - x[1]))
    stop = level - RISK_ATR_BUFFER * atr if direction == "BUY" else level + RISK_ATR_BUFFER * atr
    return {"source": source, "level": level, "stop": stop, "basis": "STRUCTURAL_LEVEL_PLUS_ATR_BUFFER", "quality": quality, "candidate_trace": candidates, "structural": True}


def _survival(bars, entry, direction, atr, risk):
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
    return {"state": "ROBUST" if margin >= MIN_SURVIVAL_MARGIN_ATR else "FRAGILE" if margin >= 0 else "NON_SURVIVABLE", "max_adverse_excursion_atr": max(adverse), "median_adverse_excursion_atr": median(adverse), "p95_adverse_excursion_atr": p95, "survival_margin_atr": margin, "window_bars": len(window)}


def _execution(snapshot, atr):
    spread = _first_num(snapshot, ("spread", "spread_price", "current_spread")) or 0.0
    slippage = _first_num(snapshot, ("slippage", "slippage_price", "expected_slippage")) or 0.0
    total = max(0.0, spread + slippage)
    return {"spread": spread, "slippage": slippage, "total_cost": total, "cost_atr": total / atr if atr > 0 else float("inf")}


def _volatility(bars, atr):
    series = _atr_series(bars)
    if atr <= 0 or len(series) < 2:
        return {"state": "INVALID", "last_range_atr": 0.0, "expansion_ratio": 0.0, "atr_stability": "INVALID", "atr_drift": 0.0}
    lr = max(0.0, _num(bars[-1].get("high")) - _num(bars[-1].get("low")))
    pr = max(0.0, _num(bars[-2].get("high")) - _num(bars[-2].get("low")))
    recent = mean(series[-5:]) if len(series) >= 5 else mean(series)
    baseline = mean(series[-min(len(series), ATR_PERIOD):])
    drift = recent / max(baseline, 1e-9)
    state = "EXPANSION_EXTREME" if lr / atr >= 2.5 else "EXPANSION" if lr / atr >= 1.75 or lr / max(pr, 1e-9) >= 2 else "COMPRESSION" if lr / atr <= 0.6 else "NORMAL"
    return {"state": state, "last_range_atr": lr / atr, "expansion_ratio": lr / max(pr, 1e-9), "atr_stability": "STABLE" if 0.65 <= drift <= 1.5 else "UNSTABLE", "atr_drift": drift}


def _probability(*sources):
    """Select only a setup/regime-conditioned probability with auditable provenance.

    A raw probability is never treated as trustworthy merely because a field exists.
    Historical sample, explicit causal conditioning and confidence are scored separately.
    Conflicting candidates are not averaged; the strongest provenance wins.
    """
    keys = ("historical_probability", "win_probability", "success_probability", "trade_probability", "probability", "estimated_probability")
    candidates = []
    for source, data in sources:
        if not isinstance(data, dict):
            continue
        source_u = _text(source)
        for key in keys:
            if key not in data or data.get(key) in (None, ""):
                continue
            raw = _num(data.get(key), -1.0)
            if raw < 0 or raw > 100:
                continue
            p = raw if raw <= 1.0 else raw / 100.0
            sample = _first_num(data, ("sample_size", "historical_sample", "samples", "n"))
            wins = _first_num(data, ("wins", "historical_wins", "winning_trades"))
            losses = _first_num(data, ("losses", "historical_losses", "losing_trades"))
            if sample is None and wins is not None and losses is not None:
                sample = wins + losses
            confidence = _num(data.get("probability_confidence", data.get("confidence", 0.0)))
            if 0 < confidence <= 1:
                confidence *= 100.0
            historical = "histor" in key or source_u in {"BACKTEST", "HISTORY", "HISTORICAL"}
            causal_detail = data.get("causal_basis") or data.get("probability_basis")
            setup_cond = bool(data.get("setup_conditioned"))
            regime_cond = bool(data.get("regime_conditioned"))
            if causal_detail in (None, "") and setup_cond and regime_cond:
                causal_detail = "SETUP_AND_REGIME_CONDITIONED"
            explicit_causal = causal_detail not in (None, "", False)
            if source_u == "SNAPSHOT":
                historical = False
            quality = 20.0
            if historical:
                quality += 25.0
            if sample is not None:
                quality += 20.0 if sample >= 100 else 15.0 if sample >= MIN_PROBABILITY_SAMPLE else 5.0
            quality += min(15.0, max(0.0, confidence) * 0.15)
            if setup_cond:
                quality += 5.0
            if regime_cond:
                quality += 5.0
            if explicit_causal:
                quality += 10.0
            if source_u == "SNAPSHOT":
                quality -= 20.0
            quality = max(0.0, min(100.0, quality))
            candidates.append({
                "quality": quality,
                "historical": historical,
                "sample": int(sample) if sample is not None else None,
                "source": source,
                "key": key,
                "value": p,
                "confidence": confidence if confidence > 0 else None,
                "causal": explicit_causal,
                "causal_detail": causal_detail,
                "setup_conditioned": setup_cond,
                "regime_conditioned": regime_cond,
            })
    if not candidates:
        return {"state": "UNAVAILABLE", "value": None, "percent": None, "source": None, "sample_size": None, "confidence_percent": None, "quality": 0.0, "quality_state": "UNAVAILABLE", "historical_evidence": False, "causal_basis": None, "causal_detail": None, "setup_conditioned": False, "regime_conditioned": False}
    chosen = max(candidates, key=lambda x: (x["quality"], bool(x["historical"]), x["sample"] or 0, bool(x["causal"])))
    quality = chosen["quality"]
    return {
        "state": "AVAILABLE",
        "value": chosen["value"],
        "percent": chosen["value"] * 100.0,
        "source": f"{chosen['source']}.{chosen['key']}",
        "sample_size": chosen["sample"],
        "confidence_percent": chosen["confidence"],
        "quality": quality,
        "quality_state": "STRONG" if quality >= 80 else "ADEQUATE" if quality >= MIN_PROBABILITY_QUALITY else "WEAK",
        "historical_evidence": chosen["historical"],
        "causal_basis": "EXPLICIT" if chosen["causal"] else "UNPROVEN",
        "causal_detail": chosen["causal_detail"],
        "setup_conditioned": chosen["setup_conditioned"],
        "regime_conditioned": chosen["regime_conditioned"],
    }


def _economics(risk, reward, execution_cost, probability):
    """Compute net expectancy after execution cost; never infer EV from missing P."""
    p = probability.get("value") if isinstance(probability, dict) else None
    if risk <= 0 or reward <= 0:
        return {"state": "UNRESOLVED", "probability": p, "gross_reward_r": 0.0, "execution_cost_r": 0.0, "effective_reward_r": 0.0, "effective_rr": 0.0, "break_even_probability": None, "probability_edge": None, "expected_value_r": None, "expected_value_price": None, "edge_class": "UNRESOLVED", "asymmetry": "INVALID", "asymmetry_ratio": None, "payoff_skew_r": None}
    gross = reward / risk
    cost_r = max(0.0, execution_cost) / risk
    effective = max(0.0, gross - cost_r)
    be = 1.0 / (1.0 + effective) if effective > 0 else 1.0
    if p is None:
        return {"state": "UNQUANTIFIED", "probability": None, "gross_reward_r": gross, "execution_cost_r": cost_r, "effective_reward_r": effective, "effective_rr": effective, "break_even_probability": be, "probability_edge": None, "expected_value_r": None, "expected_value_price": None, "edge_class": "PROBABILITY_UNAVAILABLE", "asymmetry": "UNQUANTIFIED", "asymmetry_ratio": effective, "payoff_skew_r": None}
    p = max(0.0, min(1.0, _num(p)))
    net_reward_price = max(0.0, reward - max(0.0, execution_cost))
    ev_r = p * effective - (1.0 - p)
    ev_price = p * net_reward_price - (1.0 - p) * risk
    edge = p - be
    asym = "STRONG" if effective >= 2.0 else "POSITIVE" if effective >= MIN_RR else "WEAK"
    edge_class = "POSITIVE_EXPECTANCY" if ev_r >= MIN_ECONOMIC_EDGE and edge > 0 else "MARGINAL_EXPECTANCY" if ev_r >= 0 else "NEGATIVE_EXPECTANCY"
    return {"state": "QUANTIFIED", "probability": p, "gross_reward_r": gross, "execution_cost_r": cost_r, "effective_reward_r": effective, "effective_rr": effective, "break_even_probability": be, "probability_edge": edge, "expected_value_r": ev_r, "expected_value_price": ev_price, "edge_class": edge_class, "asymmetry": asym, "asymmetry_ratio": effective, "payoff_skew_r": ev_r}


def _sensitivity(entry, stop, target, atr, direction, probability, cost):
    """Stress execution geometry and probability together; worst case must remain viable."""
    p = probability.get("value") if isinstance(probability, dict) else None
    if p is None or atr <= 0 or stop is None or target is None or direction not in {"BUY", "SELL"}:
        return {"state": "UNAVAILABLE", "scenarios": [], "worst_ev_r": None, "worst_effective_rr": None, "worst_probability": None, "fragility": "UNAVAILABLE", "scenario_count": 0}
    p = max(0.0, min(1.0, _num(p)))
    cases = (
        ("BASELINE", 0, 0, 0, 0.0),
        ("ENTRY_WORST", 1, 0, 0, PROBABILITY_STRESS),
        ("ENTRY_BEST", -1, 0, 0, 0.0),
        ("STOP_WORST", 0, 1, 0, PROBABILITY_STRESS),
        ("STOP_BEST", 0, -1, 0, 0.0),
        ("TARGET_WORST", 0, 0, -1, PROBABILITY_STRESS),
        ("TARGET_BEST", 0, 0, 1, 0.0),
        ("COMBINED_WORST", 1, 1, -1, PROBABILITY_STRESS * 1.5),
    )
    scenarios = []
    for name, es, ss, ts, ps in cases:
        en = entry + (es * SENSITIVITY_ENTRY_ATR * atr if direction == "BUY" else -es * SENSITIVITY_ENTRY_ATR * atr)
        st = stop - (ss * SENSITIVITY_STOP_ATR * atr if direction == "BUY" else -ss * SENSITIVITY_STOP_ATR * atr)
        tp = target - (ts * SENSITIVITY_TARGET_ATR * atr if direction == "BUY" else -ts * SENSITIVITY_TARGET_ATR * atr)
        valid = (st < en < tp) if direction == "BUY" else (tp < en < st)
        risk = abs(en - st)
        reward = abs(tp - en)
        p_case = max(0.0, min(1.0, p - max(0.0, ps)))
        if not valid or risk <= 0 or reward <= 0:
            scenarios.append({"scenario": name, "valid_geometry": False, "risk_atr": risk / atr, "reward_atr": reward / atr, "effective_rr": 0.0, "probability": p_case, "expected_value_r": None})
            continue
        effective_rr = max(0.0, reward / risk - max(0.0, cost) / risk)
        ev = p_case * effective_rr - (1.0 - p_case)
        scenarios.append({"scenario": name, "valid_geometry": True, "risk_atr": risk / atr, "reward_atr": reward / atr, "effective_rr": effective_rr, "probability": p_case, "expected_value_r": ev})
    valid_evs = [x["expected_value_r"] for x in scenarios if x["expected_value_r"] is not None]
    worst = min(valid_evs) if valid_evs else None
    worst_rr = min((x["effective_rr"] for x in scenarios), default=None)
    worst_p = min((x["probability"] for x in scenarios), default=None)
    robust = bool(scenarios) and worst is not None and worst >= MIN_SENSITIVITY_EV and all(x["valid_geometry"] for x in scenarios) and (worst_rr is not None and worst_rr >= MIN_RR)
    return {"state": "ROBUST" if robust else "FRAGILE", "scenarios": scenarios, "worst_ev_r": worst, "worst_effective_rr": worst_rr, "worst_probability": worst_p, "fragility": "ROBUST" if robust else "ECONOMICS_SENSITIVITY_FRAGILE", "scenario_count": len(scenarios), "probability_stress_rule": "ADVERSE_SCENARIOS_HAIRCUT_P_BY_3_PERCENTAGE_POINTS", "worst_case_rule": "MIN_SCENARIO_EV_AND_NO_GEOMETRY_BREAK_AND_MIN_RR"}


def _risk_budget(snapshot, risk):
    """Convert an explicit account risk budget into size without ever exceeding it."""
    budget = _first_num(snapshot, ("risk_budget", "max_risk_cash", "max_risk_amount"))
    pct = _first_num(snapshot, ("risk_percent", "risk_pct", "max_risk_percent"))
    capital = _first_num(snapshot, ("capital", "account_equity", "equity"))
    if budget is None and pct is not None and capital is not None:
        budget = capital * pct / 100.0
    if budget is None:
        return {"state": "UNSPECIFIED", "budget": None, "risk_distance": risk, "utilization": None, "position_size": None, "sizing_state": "NOT_COMPUTABLE", "reason": "NO_RISK_BUDGET", "remaining_budget": None}
    if budget <= 0 or risk <= 0:
        return {"state": "INVALID", "budget": budget, "risk_distance": risk, "utilization": None, "position_size": None, "sizing_state": "INVALID_RISK_BUDGET", "reason": "NON_POSITIVE_BUDGET_OR_RISK", "remaining_budget": budget}
    point_value = _first_num(snapshot, ("point_value", "contract_value_per_price_unit", "value_per_price_unit", "unit_value"))
    if point_value is None:
        return {"state": "DEFINED_NOT_SIZED", "budget": budget, "risk_distance": risk, "utilization": None, "position_size": None, "sizing_state": "MISSING_POINT_VALUE", "reason": "POSITION_SIZE_REQUIRES_INSTRUMENT_VALUE_PER_PRICE_UNIT", "remaining_budget": budget}
    risk_per_unit = risk * point_value
    if risk_per_unit <= 0:
        return {"state": "INVALID", "budget": budget, "risk_distance": risk, "risk_per_unit": risk_per_unit, "utilization": None, "position_size": None, "sizing_state": "INVALID_UNIT_RISK", "reason": "NON_POSITIVE_UNIT_RISK", "remaining_budget": budget}
    size = max(0.0, budget / risk_per_unit)
    actual_risk = size * risk_per_unit
    utilization = actual_risk / budget if budget > 0 else None
    return {"state": "WITHIN_BUDGET" if utilization is not None and utilization <= 1.0 + 1e-9 else "OVER_BUDGET", "budget": budget, "risk_distance": risk, "point_value": point_value, "risk_per_unit": risk_per_unit, "actual_risk": actual_risk, "utilization": utilization, "position_size": size, "sizing_state": "COMPUTABLE" if size > 0 else "INVALID_SIZE", "reason": "RISK_BUDGET_DIVIDED_BY_UNIT_RISK", "remaining_budget": max(0.0, budget - actual_risk)}


def analyze_e8(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """E8 validates Probability -> EV -> Asymmetry -> Sensitivity -> Risk Budget; E9 retains final authority."""
    bars = list(snapshot.get("bars") or [])
    e3, e4, e5, e6, e7 = (_evidence(upstream.get(k)) for k in ("E3", "E4", "E5", "E6", "E7"))
    base = {"architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION, "reasoning_role": "TRADE_ECONOMICS_RISK_ANALYST", "decision_authority": "E9", "trade_decision_authority": False, "closed_candle_only": True, "lookahead": False}
    if len(bars) < MIN_BARS:
        return EngineResult("E8", NAME, False, 0.0, {**base, "state": "UNRESOLVED", "economic_state": "UNRESOLVED", "risk_gate": "RISK_NOT_READY", "trade_plan": {}, "observations": [f"closed_candles={len(bars)} minimum_required={MIN_BARS}"], "counter_evidence": ["INSUFFICIENT_CLOSED_CANDLE_DATA"], "missing_evidence": ["SUFFICIENT_CLOSED_CANDLE_DATA"], "gate_matrix": {}}, ("INSUFFICIENT_DATA",))

    direction, setup = _direction(e6), _setup(e6)
    confirmation, confirmation_trace = _confirmation(e7)
    entry, atr = _num(bars[-1].get("close")), _atr(bars)
    data_valid = entry > 0 and atr > 0
    levels = _levels(e3, e4, e5, bars) if data_valid and direction in {"BUY", "SELL"} else {}
    target = _target(levels, direction, entry, atr, e4) if levels else {"source": None, "level": None, "distance": 0.0, "distance_atr": 0.0, "quality": 0.0, "hierarchy_rank": None, "credible": False, "rejection": ["NO_LEVEL_MODEL"], "candidate_trace": [], "selection_rule": "UNAVAILABLE"}
    stop_model = _stop(direction, entry, atr, levels) if levels else {"source": None, "level": None, "stop": None, "quality": 0.0, "candidate_trace": [], "basis": "UNAVAILABLE", "structural": False}
    stop, structural_stop = stop_model.get("stop"), stop_model.get("level")
    structural_breach = bool(structural_stop is not None and ((direction == "BUY" and entry <= structural_stop) or (direction == "SELL" and entry >= structural_stop)))
    execution, volatility = _execution(snapshot, atr), _volatility(bars, atr)
    probability = _probability(("E6", e6), ("E7", e7), ("E5", e5), ("E4", e4), ("E3", e3), ("SNAPSHOT", snapshot))
    risk = abs(entry - stop) if stop is not None else 0.0
    reward = abs(target["level"] - entry) if target.get("level") is not None else 0.0
    stop_atr = risk / max(atr, 1e-9) if risk else 0.0
    real_rr = reward / risk if risk > 0 and reward > 0 else 0.0
    survival = _survival(bars, entry, direction, atr, risk) if risk else {"state": "UNAVAILABLE"}
    space = _space(e5, target, direction) if levels else {"state": "UNAVAILABLE", "effective_available_space_atr": 0.0, "space_ok": False, "space_conflict": False}
    economics = _economics(risk, reward, execution["total_cost"], probability)
    sensitivity = _sensitivity(entry, stop, target.get("level"), atr, direction, probability, execution["total_cost"])
    risk_budget = _risk_budget(snapshot, risk)

    counter, missing = [], []
    if not data_valid: counter.append("RISK_DATA_INVALID")
    if direction not in {"BUY", "SELL"}: counter.append("NO_VALID_DIRECTION")
    if setup.upper() in {"UNKNOWN", "NONE", "UNRESOLVED"}: missing.append("VALID_SETUP_THESIS")
    if confirmation != "CONFIRMED": missing.append("ENTRY_CONFIRMATION")
    if structural_breach: counter.append("STRUCTURAL_INVALIDATION_BREACHED")
    if not stop_model.get("structural"): counter.append("STRUCTURAL_STOP_UNAVAILABLE")
    if stop_atr < MIN_STOP_ATR: counter.append("STOP_TOO_TIGHT_FOR_VOLATILITY")
    if stop_atr > MAX_STOP_ATR: counter.append("STOP_TOO_WIDE_FOR_ECONOMICS")
    if survival.get("state") == "NON_SURVIVABLE": counter.append("STOP_NOT_SURVIVABLE")
    elif survival.get("state") == "FRAGILE": counter.append("STOP_SURVIVAL_MARGIN_THIN")
    if not target.get("credible"): counter.append("NO_USABLE_STRUCTURAL_TARGET")
    if real_rr < MIN_RR: counter.append("REAL_RR_BELOW_MINIMUM")
    if not space["space_ok"]: counter.append("EFFECTIVE_SPACE_BELOW_MINIMUM")
    if space["space_conflict"]: counter.append("SPACE_EVIDENCE_CONFLICT")
    if volatility["state"] == "EXPANSION_EXTREME": counter.append("VOLATILITY_RISK_HIGH")
    elif volatility["state"] == "EXPANSION": counter.append("VOLATILITY_EXPANSION_RISK")
    if volatility["atr_stability"] == "UNSTABLE": counter.append("ATR_STABILITY_RISK")
    if execution["cost_atr"] > MAX_EXECUTION_COST_ATR: counter.append("EXECUTION_COST_TOO_HIGH")

    if probability["state"] != "AVAILABLE":
        counter.append("PROBABILITY_UNQUANTIFIED")
    else:
        if probability.get("value") is None or _num(probability.get("value"), -1) < MIN_PROBABILITY: counter.append("PROBABILITY_BELOW_MINIMUM")
        if _num(probability.get("quality"), 0) < MIN_PROBABILITY_QUALITY: counter.append("PROBABILITY_QUALITY_WEAK")
        sample = probability.get("sample_size")
        if sample is None or _num(sample, 0) < MIN_PROBABILITY_SAMPLE: counter.append("PROBABILITY_SAMPLE_INSUFFICIENT")
        if not probability.get("historical_evidence"): counter.append("PROBABILITY_NOT_CAUSALLY_GROUNDED")
        if probability.get("causal_basis") != "EXPLICIT": counter.append("PROBABILITY_CAUSAL_BASIS_WEAK")
        if not probability.get("setup_conditioned") or not probability.get("regime_conditioned"): counter.append("PROBABILITY_CONDITIONING_INCOMPLETE")

    probability_gate = (
        probability["state"] == "AVAILABLE"
        and probability.get("value") is not None
        and _num(probability.get("value"), 0) >= MIN_PROBABILITY
        and _num(probability.get("quality"), 0) >= MIN_PROBABILITY_QUALITY
        and _num(probability.get("sample_size"), 0) >= MIN_PROBABILITY_SAMPLE
        and bool(probability.get("historical_evidence"))
        and probability.get("causal_basis") == "EXPLICIT"
        and bool(probability.get("setup_conditioned"))
        and bool(probability.get("regime_conditioned"))
    )
    if not probability_gate: counter.append("EV_INPUT_PROBABILITY_NOT_TRUSTWORTHY")
    if economics["edge_class"] == "NEGATIVE_EXPECTANCY": counter.append("NEGATIVE_EXPECTANCY")
    if economics["state"] != "QUANTIFIED": counter.append("EXPECTED_VALUE_UNQUANTIFIED")
    elif _num(economics.get("expected_value_r"), -999) < MIN_ECONOMIC_EDGE: counter.append("ECONOMIC_EDGE_BELOW_MINIMUM")
    if economics.get("probability_edge") is None or _num(economics.get("probability_edge"), -1) <= 0: counter.append("PROBABILITY_EDGE_NOT_POSITIVE")
    if _num(economics.get("effective_rr"), -999) < MIN_RR: counter.append("EFFECTIVE_RR_BELOW_MINIMUM")
    if economics.get("asymmetry") in {"WEAK", "INVALID", "UNQUANTIFIED"}: counter.append("ASYMMETRIC_PAYOFF_INSUFFICIENT")
    if sensitivity["state"] != "ROBUST": counter.append("ECONOMICS_SENSITIVITY_FRAGILE")
    if sensitivity.get("worst_ev_r") is None: counter.append("SENSITIVITY_EV_UNQUANTIFIED")
    elif _num(sensitivity.get("worst_ev_r"), -999) < MIN_SENSITIVITY_EV: counter.append("WORST_CASE_EV_NEGATIVE")
    if sensitivity.get("worst_effective_rr") is None: counter.append("WORST_CASE_ASYMMETRY_UNQUANTIFIED")
    elif _num(sensitivity.get("worst_effective_rr"), -999) < MIN_RR: counter.append("WORST_CASE_ASYMMETRY_INSUFFICIENT")
    if risk_budget["state"] == "INVALID": counter.append("RISK_BUDGET_INVALID")
    if risk_budget["state"] == "UNSPECIFIED": missing.append("RISK_BUDGET_REQUIRED")
    if risk_budget["state"] == "DEFINED_NOT_SIZED": counter.append("POSITION_SIZE_NOT_COMPUTABLE")

    gate = {
        "DATA_INTEGRITY": data_valid,
        "DIRECTION": direction in {"BUY", "SELL"},
        "SETUP_THESIS": setup.upper() not in {"UNKNOWN", "NONE", "UNRESOLVED"},
        "ENTRY_CONFIRMATION": confirmation == "CONFIRMED",
        "STRUCTURAL_INVALIDATION": not structural_breach,
        "STRUCTURAL_STOP": bool(stop_model.get("structural")),
        "SURVIVAL": survival.get("state") == "ROBUST",
        "TARGET_HIERARCHY": bool(target.get("credible")),
        "SPACE": space["space_ok"],
        "RR": real_rr >= MIN_RR,
        "PROBABILITY": probability_gate,
        "EXPECTED_VALUE": probability_gate and economics["state"] == "QUANTIFIED" and _num(economics.get("expected_value_r"), -999) >= MIN_ECONOMIC_EDGE and _num(economics.get("probability_edge"), -999) > 0,
        "ASYMMETRY": economics.get("asymmetry") in {"POSITIVE", "STRONG"} and _num(economics.get("effective_rr"), -999) >= MIN_RR,
        "SENSITIVITY": sensitivity["state"] == "ROBUST" and _num(sensitivity.get("worst_ev_r"), -999) >= MIN_SENSITIVITY_EV and _num(sensitivity.get("worst_effective_rr"), -999) >= MIN_RR,
        "RISK_BUDGET": risk_budget["state"] == "WITHIN_BUDGET" and risk_budget.get("sizing_state") == "COMPUTABLE" and _num(risk_budget.get("position_size"), 0) > 0,
    }
    ready = all(gate.values())
    lifecycle = {f"{i:02d}_{name}": "PASS" if value else "FAIL" for i, (name, value) in enumerate(gate.items(), 1)}
    final_key = f"{len(gate)+1:02d}_FINAL_RISK_GATE"
    lifecycle[final_key] = "RISK_READY" if ready else "RISK_NOT_READY"
    counter, missing = list(dict.fromkeys(counter)), list(dict.fromkeys(missing))
    score = 100.0 if ready else max(0.0, 100.0 - 4.0 * len(counter) - 3.0 * len(missing))
    state = "ATTRACTIVE" if ready else "UNRESOLVED"
    p_pct = probability.get("percent")
    ev_r = economics.get("expected_value_r")
    ev_price = economics.get("expected_value_price")
    be = economics.get("break_even_probability")
    observations = [
        f"direction={direction}", f"setup={setup}", f"confirmation={confirmation}", f"entry={entry:.6f}", f"atr={atr:.6f}",
        f"risk_distance_atr={stop_atr:.3f}", f"target={target.get('level') if target.get('level') is not None else 'NONE'}",
        f"real_rr={real_rr:.3f}", f"effective_rr={_num(economics.get('effective_rr'), 0):.3f}",
        f"probability={p_pct:.2f}%" if p_pct is not None else "probability=UNAVAILABLE",
        f"probability_quality={_num(probability.get('quality'), 0):.1f}", f"probability_sample={probability.get('sample_size')}",
        f"probability_historical={probability.get('historical_evidence')}", f"probability_causal_basis={probability.get('causal_basis')}",
        f"probability_setup_conditioned={probability.get('setup_conditioned')}", f"probability_regime_conditioned={probability.get('regime_conditioned')}",
        f"expected_value_r={ev_r if ev_r is not None else 'UNAVAILABLE'}", f"break_even_probability={be*100:.2f}%" if be is not None else "break_even_probability=UNAVAILABLE",
        f"probability_edge={economics.get('probability_edge')}", f"asymmetry={economics.get('asymmetry')}",
        f"sensitivity={sensitivity.get('state')}", f"worst_sensitivity_ev_r={sensitivity.get('worst_ev_r')}",
        f"worst_sensitivity_rr={sensitivity.get('worst_effective_rr')}", f"risk_budget_state={risk_budget.get('state')}",
        f"position_size={risk_budget.get('position_size')}",
    ]
    if counter: observations.append("vetoes=" + ",".join(counter))
    if missing: observations.append("missing=" + ",".join(missing))
    trade_plan = {
        "valid": data_valid and direction in {"BUY", "SELL"}, "entry": entry, "direction": direction, "stop_loss": stop, "structural_stop": structural_stop,
        "invalidation_basis": stop_model.get("basis"), "invalidation_source": stop_model.get("source"), "stop_validity": "STRUCTURAL" if stop_model.get("structural") else "FALLBACK_LOWER_CONFIDENCE",
        "stop_quality": stop_model.get("quality", 0), "target": target.get("level"), "target_source": target.get("source"), "target_quality": target.get("quality", 0),
        "target_hierarchy_rank": target.get("hierarchy_rank"), "target_distance_atr": target.get("distance_atr", 0), "target_candidate_trace": target.get("candidate_trace", []),
        "target_rejection": target.get("rejection", []), "risk_distance": risk, "risk_distance_atr": stop_atr, "reward_distance": reward,
        "reward_distance_atr": reward / max(atr, 1e-9), "real_rr": real_rr, "effective_rr": economics.get("effective_rr", 0), "break_even_probability": be,
        "probability": probability.get("value"), "probability_percent": p_pct, "probability_source": probability.get("source"), "probability_quality": probability.get("quality"),
        "probability_sample_size": probability.get("sample_size"), "probability_historical_evidence": probability.get("historical_evidence"), "probability_causal_basis": probability.get("causal_basis"),
        "expected_value_r": ev_r, "expected_value_price": ev_price, "probability_edge": economics.get("probability_edge"), "economic_edge": economics.get("edge_class"),
        "asymmetry": economics.get("asymmetry"), "asymmetry_ratio": economics.get("asymmetry_ratio"), "sensitivity": sensitivity, "risk_budget": risk_budget,
        "max_adverse_excursion_atr": survival.get("max_adverse_excursion_atr"), "p95_adverse_excursion_atr": survival.get("p95_adverse_excursion_atr"),
        "survival_margin_atr": survival.get("survival_margin_atr"), "survival_state": survival.get("state"),
    }
    causal = f"SETUP={setup}->CONFIRMATION={confirmation}->ENTRY={entry:.6f}->STOP={stop if stop is not None else 'NONE'}->TARGET={target.get('level') if target.get('level') is not None else 'NONE'}->REAL_RR={real_rr:.3f}->P={p_pct if p_pct is not None else 'NA'}->EV_R={ev_r if ev_r is not None else 'NA'}->ASYMMETRY={economics.get('asymmetry')}->WORST_EV_R={sensitivity.get('worst_ev_r')}->WORST_RR={sensitivity.get('worst_effective_rr')}->SENSITIVITY={sensitivity.get('state')}->RISK_BUDGET={risk_budget.get('state')}->POSITION_SIZE={risk_budget.get('position_size')}"
    output = {
        **base, "state": state, "economic_state": state, "risk_gate": lifecycle[final_key], "direction": direction, "setup": setup,
        "confirmation": confirmation, "confirmation_trace": confirmation_trace, "trade_plan": trade_plan,
        "structural_evidence": {**levels, "structural_breach": structural_breach, "stop_model": stop_model}, "dynamic_target": target,
        "location_evidence": space, "risk_model": {"atr": atr, "atr_period": ATR_PERIOD, "volatility": volatility, "execution": execution, "survival": survival},
        "probability_evidence": probability, "trade_economics": economics, "sensitivity_analysis": sensitivity, "risk_budget": risk_budget,
        "gate_matrix": gate, "lifecycle": lifecycle, "counter_evidence": counter, "missing_evidence": missing, "observations": observations,
        "professional_reasoning": {
            "causal_chain": causal,
            "economic_reasoning": f"P={p_pct if p_pct is not None else 'UNAVAILABLE'}%;Effective_RR={economics.get('effective_rr')};BE_P={be};EV_R={ev_r};ProbabilityEdge={economics.get('probability_edge')};Asymmetry={economics.get('asymmetry')};WorstSensitivityEV={sensitivity.get('worst_ev_r')};WorstSensitivityRR={sensitivity.get('worst_effective_rr')}",
            "probability_reasoning": f"source={probability.get('source')};quality={probability.get('quality')};sample={probability.get('sample_size')};historical={probability.get('historical_evidence')};causal_basis={probability.get('causal_basis')};causal_detail={probability.get('causal_detail')};setup_conditioned={probability.get('setup_conditioned')};regime_conditioned={probability.get('regime_conditioned')}",
            "risk_budget_reasoning": f"state={risk_budget.get('state')};budget={risk_budget.get('budget')};risk_distance={risk};point_value={risk_budget.get('point_value')};risk_per_unit={risk_budget.get('risk_per_unit')};position_size={risk_budget.get('position_size')};utilization={risk_budget.get('utilization')}",
            "sensitivity_reasoning": f"state={sensitivity.get('state')};worst_ev_r={sensitivity.get('worst_ev_r')};worst_rr={sensitivity.get('worst_effective_rr')};worst_probability={sensitivity.get('worst_probability')};scenarios={sensitivity.get('scenario_count')}",
            "causal_risk_reasoning": ";".join(counter + missing) if (counter or missing) else "NO_RISK_VETO",
            "risk_veto": "PASS" if ready else "VETO: " + ";".join(counter + missing + ["ECONOMICS_NOT_READY"]),
        },
        "decision_path": "E8 validates Probability -> EV -> Asymmetry -> Sensitivity -> Risk Budget plus structural survivability; E9 retains final trade authority.",
    }
    return EngineResult("E8", NAME, ready, score, output, tuple(counter + missing + ([] if ready else ["ECONOMICS_NOT_READY"])))
