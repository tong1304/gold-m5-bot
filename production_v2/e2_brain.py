from __future__ import annotations

from statistics import mean
from typing import Any

QUESTION = "What opportunity is the market offering right now?"
MIN_BARS = 80
ARCHITECTURE = "E2_PROFESSIONAL_OPPORTUNITY_CORE_V2"


def _bars(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    bars = snapshot.get("bars") or []
    return [b for b in bars if isinstance(b, dict) and all(k in b for k in ("open", "high", "low", "close"))]


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs: list[float] = []
    prev = float(bars[0]["close"])
    for b in bars[-period:]:
        h, l, c = float(b["high"]), float(b["low"]), float(b["close"])
        trs.append(max(h - l, abs(h - prev), abs(l - prev)))
        prev = c
    return mean(trs) if trs else 0.0


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    value = values[0]
    for x in values[1:]:
        value = alpha * x + (1.0 - alpha) * value
    return value


def _direction(value: Any) -> str:
    v = str(value or "NEUTRAL").upper().strip()
    if v in {"UP", "BULLISH", "BUY", "LONG", "TREND_UP"}:
        return "UP"
    if v in {"DOWN", "BEARISH", "SELL", "SHORT", "TREND_DOWN"}:
        return "DOWN"
    return "NEUTRAL"


def _e1_context(snapshot: dict[str, Any]) -> dict[str, Any]:
    value = snapshot.get("E1_result") or {}
    return value if isinstance(value, dict) else {}


def _pivots(bars: list[dict[str, Any]], wing: int = 2) -> tuple[list[float], list[float]]:
    highs, lows = [], []
    for i in range(wing, len(bars) - wing):
        window = bars[i - wing:i + wing + 1]
        hi, lo = float(bars[i]["high"]), float(bars[i]["low"])
        if hi >= max(float(x["high"]) for x in window):
            highs.append(hi)
        if lo <= min(float(x["low"]) for x in window):
            lows.append(lo)
    return highs, lows


def _unavailable() -> dict[str, Any]:
    return {
        "state": "UNAVAILABLE", "architecture": ARCHITECTURE, "sub_engines_active": False,
        "reasoning_mode": "SINGLE_PROFESSIONAL_CORE", "question": QUESTION,
        "thesis": "Insufficient closed-candle history; no opportunity thesis is formed.",
        "regime": "UNRESOLVED", "direction": "NEUTRAL", "phase": "UNRESOLVED", "opportunity": "NONE",
        "opportunity_state": "WAIT", "opportunity_maturity": "UNPROVEN", "quality": "UNPROVEN",
        "opportunity_quality": "LOW", "opportunity_decision": "WAIT", "edge_assessment": "NO_EDGE",
        "alignment_with_e1": "INCONCLUSIVE", "independence": "E2_FIRST_E1_CROSS_CHECK",
        "auction_state": "UNKNOWN", "auction_phase": "TRANSITION", "location_context": "UNKNOWN",
        "regime_confidence": 0.0, "confidence": 0.0, "opportunity_score": 0.0,
        "acceptance_quality": "UNPROVEN", "timing_state": "WAIT", "decision_factors": [],
        "observations": [], "evidence": [], "evidence_map": {},
        "counter_evidence": ["insufficient closed-candle history"], "counter_evidence_severity": "THESIS_INVALIDATION",
        "missing_evidence": [f"{MIN_BARS} valid closed candles"], "invalidation_evidence": [],
        "why_not_trade": ["insufficient market data"],
        "counterfactual": ["without sufficient history, no directional thesis is trustworthy"],
        "decision": None, "entry": None, "trigger": None, "risk": None, "gate": None,
        "trade_decision_authority": "E9_ONLY", "reason_codes": ["INSUFFICIENT_MARKET_DATA"],
        "professional_reasoning": {"question": QUESTION, "conclusion": "NO_OPPORTUNITY_THESIS",
            "why_now": "Insufficient evidence.", "expected_path": "Wait for sufficient closed-candle history.",
            "required_evidence": [f"{MIN_BARS} valid closed candles"], "invalidation_conditions": ["data insufficiency"],
            "timing": "WAIT", "opportunity_quality": "LOW", "opportunity_decision": "WAIT", "edge_assessment": "NO_EDGE",
            "independent_thesis": True, "e1_used_as": "CROSS_CHECK_ONLY", "entry_authorized": False},
    }


def _quality(structure: float, acceptance: float, pullback: float, location: float, space: float,
             efficiency: float, volatility: float, rejection: float, extension: float) -> float:
    return max(0.0, min(1.0, 0.20 * structure + 0.16 * acceptance + 0.16 * pullback + 0.12 * location
        + 0.12 * space + 0.10 * efficiency + 0.08 * volatility - 0.16 * rejection - 0.18 * extension))


def analyze_e2(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Independent professional opportunity brain. E1 is cross-check evidence only; E2 never authorizes trades."""
    bs = _bars(snapshot)
    if len(bs) < MIN_BARS:
        return _unavailable()

    h = [float(b["high"]) for b in bs]; l = [float(b["low"]) for b in bs]
    c = [float(b["close"]) for b in bs]; o = [float(b["open"]) for b in bs]
    last = c[-1]; atr = max(_atr(bs), 1e-12)
    ema20, ema50 = _ema(c, 20), _ema(c, 50)
    ema20_prev, ema50_prev = _ema(c[:-5], 20), _ema(c[:-5], 50)
    ema_gap = (ema20 - ema50) / atr
    ema20_slope = (ema20 - ema20_prev) / atr; ema50_slope = (ema50 - ema50_prev) / atr
    ranges = [max(float(b["high"]) - float(b["low"]), 0.0) for b in bs]
    avg20 = max(mean(ranges[-20:]), 1e-12); vol_ratio = mean(ranges[-5:]) / avg20
    slope5 = (c[-1] - c[-6]) / atr; slope20 = (c[-1] - c[-21]) / atr; slope40 = (c[-1] - c[-41]) / atr
    travelled12 = max(sum(ranges[-12:]), 1e-12); efficiency12 = abs(c[-1] - c[-13]) / travelled12
    hi20, lo20 = max(h[-21:-1]), min(l[-21:-1]); hi40, lo40 = max(h[-41:-1]), min(l[-41:-1])
    width40 = max(hi40 - lo40, 1e-12); pos40 = max(0.0, min(1.0, (last - lo40) / width40))
    pos20 = max(0.0, min(1.0, (last - lo20) / max(hi20 - lo20, 1e-12)))
    ph, pl = _pivots(bs)
    hh = len(ph) >= 2 and ph[-1] > ph[-2]; lh = len(ph) >= 2 and ph[-1] < ph[-2]
    hl = len(pl) >= 2 and pl[-1] > pl[-2]; ll = len(pl) >= 2 and pl[-1] < pl[-2]
    bull_structure, bear_structure = hh and hl, lh and ll
    up_evidence = sum((ema_gap > 0.35, ema20_slope > 0.08, ema50_slope > -0.05, slope5 > 0.20, slope20 > 0.45, bull_structure, efficiency12 >= 0.30))
    down_evidence = sum((ema_gap < -0.35, ema20_slope < -0.08, ema50_slope < 0.05, slope5 < -0.20, slope20 < -0.45, bear_structure, efficiency12 >= 0.30))
    span = max(h[-1] - l[-1], 1e-12); body = abs(last - o[-1]) / span; close_pos = (last - l[-1]) / span
    upper_wick = (h[-1] - max(o[-1], last)) / span; lower_wick = (min(o[-1], last) - l[-1]) / span
    broke_up, broke_down = last > hi20, last < lo20
    swept_up, swept_down = h[-1] > hi20 and last <= hi20, l[-1] < lo20 and last >= lo20
    accepted_up = broke_up and close_pos >= 0.65 and body >= 0.45
    accepted_down = broke_down and close_pos <= 0.35 and body >= 0.45
    rejected_up = swept_up and close_pos <= 0.45 and upper_wick >= 0.20
    rejected_down = swept_down and close_pos >= 0.55 and lower_wick >= 0.20
    displacement_up = body >= 0.60 and close_pos >= 0.75 and span >= 1.25 * avg20
    displacement_down = body >= 0.60 and close_pos <= 0.25 and span >= 1.25 * avg20
    impulse_up = (c[-8] - c[-16]) / atr >= 1.00 and c[-8] > c[-16]
    impulse_down = (c[-16] - c[-8]) / atr >= 1.00 and c[-8] < c[-16]
    impulse_high, impulse_low = max(h[-8:-2]), min(l[-8:-2])
    retrace_up = max(0.0, (impulse_high - last) / max(impulse_high - impulse_low, atr))
    retrace_down = max(0.0, (last - impulse_low) / max(impulse_high - impulse_low, atr))
    pullback_up = impulse_up and 0.20 <= retrace_up <= 0.65 and last > lo20 and ema20 >= ema50 and (lower_wick >= 0.15 or close_pos >= 0.55 or c[-1] >= c[-2])
    pullback_down = impulse_down and 0.20 <= retrace_down <= 0.65 and last < hi20 and ema20 <= ema50 and (upper_wick >= 0.15 or close_pos <= 0.45 or c[-1] <= c[-2])
    compressed, expanding = vol_ratio < 0.72, vol_ratio > 1.28
    balanced = abs(slope20) < 0.65 and efficiency12 < 0.30 and width40 / atr < 8.5

    if accepted_up and accepted_down:
        base_regime, base_direction, auction_state = "TRANSITION", "NEUTRAL", "TWO_SIDED_ACCEPTANCE"
    elif accepted_up and not rejected_up:
        base_regime, base_direction, auction_state = "BREAKOUT", "UP", "ACCEPTANCE_UP"
    elif accepted_down and not rejected_down:
        base_regime, base_direction, auction_state = "BREAKOUT", "DOWN", "ACCEPTANCE_DOWN"
    elif rejected_up and not rejected_down and pos40 >= 0.70:
        base_regime, base_direction, auction_state = "MEAN_REVERSION", "DOWN", "FAILED_AUCTION_HIGH"
    elif rejected_down and not rejected_up and pos40 <= 0.30:
        base_regime, base_direction, auction_state = "MEAN_REVERSION", "UP", "FAILED_AUCTION_LOW"
    elif up_evidence >= 5 and up_evidence > down_evidence + 1:
        base_regime, base_direction, auction_state = "TREND", "UP", "DIRECTIONAL_AUCTION_UP"
    elif down_evidence >= 5 and down_evidence > up_evidence + 1:
        base_regime, base_direction, auction_state = "TREND", "DOWN", "DIRECTIONAL_AUCTION_DOWN"
    elif balanced or (compressed and abs(up_evidence - down_evidence) <= 2):
        base_regime, base_direction, auction_state = "RANGE", "NEUTRAL", "BALANCED_AUCTION"
    else:
        base_regime, base_direction, auction_state = "TRANSITION", "NEUTRAL", "UNCOMMITTED_AUCTION"

    # E2's hierarchy: identify market intent first, then opportunities, then vetoes, then conditional paths.
    candidates: list[dict[str, Any]] = []
    def add(name: str, direction: str, regime: str, structure: bool, acceptance: bool, rejection: bool, pullback: bool, displacement: bool) -> None:
        space = max((hi40 - last) / atr, 0.0) if direction == "UP" else max((last - lo40) / atr, 0.0)
        location = (0.10 <= pos40 <= 0.75) if direction == "UP" else (0.25 <= pos40 <= 0.90)
        extended = (pos40 >= 0.92) if direction == "UP" else (pos40 <= 0.08)
        vetoes: list[str] = []
        if not location: vetoes.append("LOCATION_NOT_ADVANTAGEOUS")
        if space < 1.0: vetoes.append("INSUFFICIENT_OPPOSING_SPACE")
        if extended: vetoes.append("OVEREXTENDED_LOCATION")
        if rejection and direction == "UP" and pos40 >= 0.70: vetoes.append("FAILED_UPSIDE_AUCTION")
        if rejection and direction == "DOWN" and pos40 <= 0.30: vetoes.append("FAILED_DOWNSIDE_AUCTION")
        if name == "BREAKOUT_CONTINUATION" and not acceptance: vetoes.append("NO_ACCEPTANCE")
        q = _quality(float(structure), float(acceptance or displacement), float(pullback), float(location), max(0.0, min(1.0, space / 3.0)), max(0.0, min(1.0, efficiency12 / 0.55)), 1.0 if 0.75 <= vol_ratio <= 1.55 else 0.35, float(rejection), float(extended))
        candidates.append({"name": name, "direction": direction, "regime": regime, "structure": structure, "acceptance": acceptance,
            "rejection": rejection, "pullback": pullback, "displacement": displacement, "quality": q, "space_atr": space,
            "location_ok": location, "extended": bool(extended), "vetoes": vetoes, "eligible": not vetoes})

    if up_evidence >= 4:
        add("TREND_PULLBACK_CONTINUATION", "UP", "TREND", bull_structure, accepted_up, rejected_up, pullback_up, displacement_up)
        add("TREND_CONTINUATION", "UP", "TREND", bull_structure, accepted_up, rejected_up, False, displacement_up)
    if down_evidence >= 4:
        add("TREND_PULLBACK_CONTINUATION", "DOWN", "TREND", bear_structure, accepted_down, rejected_down, pullback_down, displacement_down)
        add("TREND_CONTINUATION", "DOWN", "TREND", bear_structure, accepted_down, rejected_down, False, displacement_down)
    if accepted_up: add("BREAKOUT_CONTINUATION", "UP", "BREAKOUT", bull_structure, True, rejected_up, False, displacement_up)
    if accepted_down: add("BREAKOUT_CONTINUATION", "DOWN", "BREAKOUT", bear_structure, True, rejected_down, False, displacement_down)
    if rejected_down and pos40 <= 0.30: add("LIQUIDITY_REVERSAL", "UP", "MEAN_REVERSION", bull_structure, False, True, False, displacement_up)
    if rejected_up and pos40 >= 0.70: add("LIQUIDITY_REVERSAL", "DOWN", "MEAN_REVERSION", bear_structure, False, True, False, displacement_down)

    eligible = [x for x in candidates if x["eligible"]]
    eligible.sort(key=lambda x: (float(x["quality"]), float(x["space_atr"]), bool(x["structure"])), reverse=True)
    rejected = [x for x in candidates if not x["eligible"]]
    rejected.sort(key=lambda x: float(x["quality"]), reverse=True)
    best, second = (eligible[0] if eligible else None), (eligible[1] if len(eligible) > 1 else None)
    ambiguity = bool(best and second and best["direction"] != second["direction"] and abs(float(best["quality"]) - float(second["quality"])) < 0.12)

    # Professional intent: separate what is happening from what is tradable.
    if accepted_up and not rejected_up: intent = "BUY_SIDE_REPRICING"
    elif accepted_down and not rejected_down: intent = "SELL_SIDE_REPRICING"
    elif rejected_up and pos40 >= 0.70: intent = "FAILED_HIGH_AUCTION"
    elif rejected_down and pos40 <= 0.30: intent = "FAILED_LOW_AUCTION"
    elif bull_structure and not bear_structure: intent = "UPSIDE_CONTROL_WITHOUT_ACCEPTANCE"
    elif bear_structure and not bull_structure: intent = "DOWNSIDE_CONTROL_WITHOUT_ACCEPTANCE"
    elif balanced: intent = "TWO_SIDED_BALANCE"
    else: intent = "UNCOMMITTED_AUCTION"

    if ambiguity:
        direction, regime, opportunity, phase, auction_state = "NEUTRAL", "TRANSITION", "WAIT_FOR_REPRICING", "AMBIGUOUS", "COMPETING_HYPOTHESES"
    elif best:
        direction, regime, opportunity = best["direction"], best["regime"], best["name"]
        phase = "PULLBACK" if opportunity == "TREND_PULLBACK_CONTINUATION" and best["pullback"] else "ACCEPTANCE" if opportunity == "BREAKOUT_CONTINUATION" else "REJECTION" if opportunity == "LIQUIDITY_REVERSAL" else "EXPANSION" if best["displacement"] else "DEVELOPING"
    else:
        direction, regime = "NEUTRAL", base_regime
        opportunity = "WAIT_FOR_RANGE_EDGE" if regime == "RANGE" else "WAIT_FOR_REPRICING"
        phase = "BALANCED" if regime == "RANGE" else "TRANSITION"

    location = "EDGE_LOW" if pos40 <= 0.20 else "EDGE_HIGH" if pos40 >= 0.80 else "MID_RANGE"
    opposing_space_atr = max((hi40 - last) / atr, 0.0) if direction == "UP" else max((last - lo40) / atr, 0.0) if direction == "DOWN" else 0.0
    invalidation_distance_atr = max((last - lo40) / atr, 0.0) if direction == "UP" else max((hi40 - last) / atr, 0.0) if direction == "DOWN" else 0.0
    space_ok = opposing_space_atr >= 1.0
    overextended = (direction == "UP" and pos40 >= 0.92) or (direction == "DOWN" and pos40 <= 0.08)

    counter: list[str] = []; missing: list[str] = []; invalidation: list[str] = []
    if ambiguity: counter.append("competing directional hypotheses are too close; no decisive edge")
    if direction == "UP":
        if ema20 < ema50 and not pullback_up: counter.append("short-term value structure opposes upside thesis")
        if regime == "TREND" and not bull_structure: counter.append("bullish swing sequence is not fully established")
        if rejected_up: counter.append("upside auction shows rejection")
    elif direction == "DOWN":
        if ema20 > ema50 and not pullback_down: counter.append("short-term value structure opposes downside thesis")
        if regime == "TREND" and not bear_structure: counter.append("bearish swing sequence is not fully established")
        if rejected_down: counter.append("downside auction shows rejection")
    if not space_ok and direction != "NEUTRAL": counter.append("opposing liquidity is too close")
    if overextended: counter.append("price is materially extended")

    if opportunity == "TREND_PULLBACK_CONTINUATION":
        if not (pullback_up or pullback_down): missing.append("controlled pullback with directional holding/rejection")
        missing.append("follow-through after pullback")
    elif opportunity == "TREND_CONTINUATION":
        if not (accepted_up or accepted_down or displacement_up or displacement_down): missing.append("fresh acceptance or displacement before continuation")
        missing.append("follow-through")
    elif opportunity == "BREAKOUT_CONTINUATION":
        if not expanding: missing.append("volatility expansion and sustained acceptance")
        missing.append("follow-through beyond the broken range")
    elif opportunity == "LIQUIDITY_REVERSAL": missing.append("rejection must hold and rotate back into value")
    elif opportunity == "WAIT_FOR_RANGE_EDGE": missing.append("meaningful range-edge interaction and rejection")
    else: missing.append("clear directional commitment / repricing")

    if direction == "UP" and rejected_up and pos40 >= 0.80: invalidation.append("upside acceptance failed at a high-value area")
    if direction == "DOWN" and rejected_down and pos40 <= 0.20: invalidation.append("downside acceptance failed at a low-value area")
    if direction == "UP" and down_evidence >= up_evidence + 2: invalidation.append("independent downside evidence dominates")
    if direction == "DOWN" and up_evidence >= down_evidence + 2: invalidation.append("independent upside evidence dominates")

    e1 = _e1_context(snapshot); e1_direction = _direction(e1.get("directional_pressure") or e1.get("direction"))
    e1_state = str(e1.get("market_state") or e1.get("state") or "UNRESOLVED").upper()
    alignment = "INCONCLUSIVE" if direction == "NEUTRAL" or e1_direction == "NEUTRAL" else "ALIGNED" if direction == e1_direction else "CONFLICT"
    if alignment == "CONFLICT": counter.append("E1 directional evidence conflicts with the independent E2 thesis")

    best_quality = float(best["quality"]) if best else 0.0
    directional_strength = max(up_evidence, down_evidence) / 7.0
    counter_penalty = min(0.45, 0.08 * len(counter)); missing_penalty = min(0.25, 0.06 * len(missing))
    confidence = max(0.0, min(1.0, 0.50 * best_quality + 0.30 * directional_strength + 0.20 - counter_penalty - missing_penalty + (0.04 if alignment == "ALIGNED" else -0.04 if alignment == "CONFLICT" else 0.0)))
    opportunity_score = max(0.0, min(1.0, 0.68 * best_quality + 0.32 * confidence))

    if invalidation: maturity, opportunity_state, quality = "INVALIDATED", "INVALIDATED", "REJECTED"
    elif direction == "NEUTRAL": maturity, opportunity_state, quality = "WAITING", "WAIT", "UNPROVEN"
    elif counter or missing: maturity, opportunity_state, quality = "DEVELOPING", "DEVELOPING", "STRONG_CONTEXT" if opportunity_score >= 0.70 else "DEVELOPING"
    else: maturity, opportunity_state, quality = "MATURE_CONTEXT", "CONTEXT_READY", "STRONG" if opportunity_score >= 0.78 else "DEVELOPING"
    timing = "MISSED" if invalidation else "WAIT" if direction == "NEUTRAL" else "LATE" if overextended else "READY_FOR_CONFIRMATION" if missing else "DEVELOPING"
    opportunity_quality = "HIGH" if opportunity_score >= 0.78 and not counter else "MEDIUM" if opportunity_score >= 0.55 else "LOW"
    acceptance_quality = "CONFIRMED" if accepted_up or accepted_down else "STRONG" if displacement_up or displacement_down else "UNPROVEN"

    if invalidation or direction == "NEUTRAL": opportunity_decision, edge = ("NO_OPPORTUNITY", "NO_EDGE") if invalidation else ("WAIT", "NO_EDGE")
    elif overextended or not space_ok or counter or missing: opportunity_decision, edge = "WATCH", "EDGE_CONDITIONAL"
    elif opportunity_score >= 0.72: opportunity_decision, edge = "ACTIONABLE_BIAS", "EDGE_PRESENT"
    else: opportunity_decision, edge = "WATCH", "EDGE_CONDITIONAL"

    # Conditional opportunity map: E2 forecasts branches, not entries.
    conditional_paths = []
    if direction != "NEUTRAL":
        conditional_paths.append({"if": "supporting structure + acceptance/holding persist", "then": f"{direction}_THESIS_STRENGTHENS", "status": "FAVORABLE"})
        conditional_paths.append({"if": "opposing structure becomes dominant", "then": "CURRENT_THESIS_INVALIDATED", "status": "INVALIDATION"})
    if regime in {"RANGE", "TRANSITION"}:
        conditional_paths.append({"if": "price reaches favorable range edge and rejection holds", "then": "RANGE_ROTATION_OPPORTUNITY_DEVELOPS", "status": "WATCH"})
        conditional_paths.append({"if": "price accepts beyond the range boundary with expansion", "then": "BREAKOUT_REPRICING_OPPORTUNITY_DEVELOPS", "status": "WATCH"})
    if rejected_up and pos40 >= 0.70:
        conditional_paths.append({"if": "high rejection holds and price returns into value", "then": "DOWN_REVERSAL_OPPORTUNITY_DEVELOPS", "status": "WATCH"})
    if rejected_down and pos40 <= 0.30:
        conditional_paths.append({"if": "low rejection holds and price returns into value", "then": "UP_REVERSAL_OPPORTUNITY_DEVELOPS", "status": "WATCH"})

    why_not_trade = []
    if direction == "NEUTRAL": why_not_trade.append("no decisive directional opportunity is established")
    if ambiguity: why_not_trade.append("competing hypotheses are too close to justify commitment")
    if overextended: why_not_trade.append("late location: price is too extended for immediate participation")
    if direction != "NEUTRAL" and not space_ok: why_not_trade.append("insufficient opposing space for a favorable path")
    why_not_trade.extend(f"missing: {x}" for x in missing); why_not_trade.extend(f"counter-evidence: {x}" for x in counter); why_not_trade.extend(f"invalidated: {x}" for x in invalidation)
    if not why_not_trade: why_not_trade.append("E2 provides context only; downstream engines must validate confirmation and trade economics")
    counterfactual = (["if supporting structure fails and downside evidence dominates, abandon the upside thesis"] if direction == "UP" else ["if opposing structure is reclaimed and upside evidence dominates, abandon the downside thesis"] if direction == "DOWN" else ["if one side gains sustained acceptance and follow-through, replace neutrality with that directional thesis"])
    expected_path = {"TREND_PULLBACK_CONTINUATION": "impulse -> controlled pullback -> holding/rejection -> confirmation -> continuation", "TREND_CONTINUATION": "directional pressure -> acceptance/displacement -> confirmation -> follow-through", "BREAKOUT_CONTINUATION": "breakout -> acceptance beyond range -> expansion -> follow-through", "LIQUIDITY_REVERSAL": "liquidity sweep -> rejection holds -> return into value -> reversal follow-through", "WAIT_FOR_RANGE_EDGE": "range edge interaction -> rejection/acceptance decision -> rotation or breakout", "WAIT_FOR_REPRICING": "clear directional commitment -> acceptance -> follow-through"}.get(opportunity, "repricing -> clear directional commitment -> opportunity maturity")

    candidate_summary = [{"name": x["name"], "direction": x["direction"], "quality": round(float(x["quality"]), 4), "space_atr": round(float(x["space_atr"]), 4), "eligible": bool(x["eligible"]), "vetoes": x["vetoes"]} for x in candidates[:8]]
    observations = [f"ema_gap_atr={ema_gap:.3f}", f"ema20_slope_atr={ema20_slope:.3f}", f"ema50_slope_atr={ema50_slope:.3f}", f"slope5_atr={slope5:.3f}", f"slope20_atr={slope20:.3f}", f"volatility_ratio={vol_ratio:.3f}", f"efficiency12={efficiency12:.3f}", f"up_evidence={up_evidence}/7", f"down_evidence={down_evidence}/7", f"position_40={pos40:.3f}", f"position_20={pos20:.3f}", f"retrace_up={retrace_up:.3f}", f"retrace_down={retrace_down:.3f}", f"opposing_space_atr={opposing_space_atr:.3f}", f"intent={intent}", f"eligible_candidates={len(eligible)}", f"vetoed_candidates={len(rejected)}"]
    decision_factors = [f"independent_regime={regime}", f"independent_direction={direction}", f"auction_intent={intent}", f"auction_state={auction_state}", f"opportunity={opportunity}", f"phase={phase}", f"location={location}", f"best_candidate_quality={best_quality:.3f}", f"candidate_count={len(candidates)}", f"alignment_with_e1={alignment}", f"timing={timing}", f"opportunity_score={opportunity_score:.3f}", f"decision={opportunity_decision}"]
    thesis = f"Independent E2 thesis: {regime}/{direction} creates {opportunity} at {phase}; thesis is {maturity.lower()} and requires downstream confirmation."
    reasoning = {"question": QUESTION, "conclusion": thesis, "why_now": f"{auction_state}; intent={intent}; {location}; opposing space={opposing_space_atr:.2f} ATR", "expected_path": expected_path, "required_evidence": list(dict.fromkeys(missing)), "invalidation_conditions": list(invalidation) or ["opposing structure becomes dominant", "auction invalidates the expected path"], "timing": timing, "opportunity_quality": opportunity_quality, "opportunity_decision": opportunity_decision, "edge_assessment": edge, "candidate_comparison": candidate_summary, "conditional_paths": conditional_paths, "counter_evidence_count": len(counter), "counter_evidence": counter, "why_not_trade": why_not_trade, "counterfactual": counterfactual, "independent_thesis": True, "e1_used_as": "CROSS_CHECK_ONLY", "entry_authorized": False}
    reason_codes = []
    if invalidation: reason_codes.append("THESIS_INVALIDATED")
    if alignment == "CONFLICT": reason_codes.append("E1_E2_DIRECTION_CONFLICT")
    if ambiguity: reason_codes.append("COMPETING_HYPOTHESES")
    if missing: reason_codes.append("MISSING_OPPORTUNITY_CONFIRMATION")
    if counter: reason_codes.append("COUNTER_EVIDENCE_PRESENT")
    if any(x["vetoes"] for x in candidates): reason_codes.append("HARD_VETO_PRESENT")
    if conditional_paths: reason_codes.append("CONDITIONAL_OPPORTUNITY_MAP")
    if opportunity not in {"WAIT_FOR_REPRICING", "WAIT_FOR_RANGE_EDGE"} and not invalidation and direction != "NEUTRAL": reason_codes.append("OPPORTUNITY_THESIS_ESTABLISHED")
    if not reason_codes: reason_codes.append("NO_ACTIONABLE_OPPORTUNITY")

    return {"state": "OPPORTUNITY_ANALYSIS_COMPLETE", "architecture": ARCHITECTURE, "sub_engines_active": False, "reasoning_mode": "SINGLE_PROFESSIONAL_CORE", "question": QUESTION, "thesis": thesis, "regime": regime, "direction": direction, "phase": phase, "opportunity": opportunity, "opportunity_state": opportunity_state, "opportunity_maturity": maturity, "quality": quality, "opportunity_quality": opportunity_quality, "opportunity_score": round(opportunity_score, 4), "opportunity_decision": opportunity_decision, "edge_assessment": edge, "alignment_with_e1": alignment, "independence": "E2_FIRST_E1_CROSS_CHECK", "auction_state": auction_state, "auction_phase": "ACCEPTANCE" if "ACCEPTANCE" in auction_state else "REJECTION" if "FAILED_AUCTION" in auction_state else "BALANCE" if "BALANCED" in auction_state else "REPRICING" if direction != "NEUTRAL" else "TRANSITION", "auction_intent": intent, "acceptance_quality": acceptance_quality, "location_context": location, "regime_confidence": round(directional_strength, 4), "confidence": round(confidence, 4), "timing_state": timing, "decision_factors": decision_factors, "observations": observations, "evidence": [f"UP_EVIDENCE={up_evidence}/7", f"DOWN_EVIDENCE={down_evidence}/7", f"STRUCTURE_BULL={bull_structure}", f"STRUCTURE_BEAR={bear_structure}", f"ACCEPTANCE_UP={accepted_up}", f"ACCEPTANCE_DOWN={accepted_down}", f"REJECTION_UP={rejected_up}", f"REJECTION_DOWN={rejected_down}", f"EXPANSION={expanding}", f"COMPRESSION={compressed}", f"SPACE_OK={space_ok}", f"E1_STATE={e1_state}"], "candidate_comparison": candidate_summary, "conditional_opportunity_map": conditional_paths, "evidence_map": {"directional_pressure": direction, "location": location, "regime": regime, "auction_state": auction_state, "auction_intent": intent, "space_ok": space_ok, "overextended": overextended, "alignment_with_e1": alignment, "hypothesis_ambiguity": ambiguity}, "counter_evidence": counter, "counter_evidence_severity": "THESIS_INVALIDATION" if invalidation else "MATERIAL" if counter else "NONE", "missing_evidence": missing, "invalidation_evidence": invalidation, "why_not_trade": why_not_trade, "counterfactual": counterfactual, "opposing_space_atr": round(opposing_space_atr, 4), "invalidation_distance_atr": round(invalidation_distance_atr, 4), "decision": None, "entry": None, "trigger": None, "risk": None, "gate": None, "trade_decision_authority": "E9_ONLY", "professional_reasoning": reasoning, "reason_codes": list(dict.fromkeys(reason_codes))}
