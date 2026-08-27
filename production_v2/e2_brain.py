from __future__ import annotations

from statistics import mean
from typing import Any

QUESTION = "What opportunity is the market offering right now?"
MIN_BARS = 80


def _bars(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    bars = snapshot.get("bars") or []
    return [b for b in bars if isinstance(b, dict) and all(k in b for k in ("open", "high", "low", "close"))]


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    if not bars:
        return 0.0
    trs: list[float] = []
    prev = None
    for b in bars[-period:]:
        h, l, c = float(b["high"]), float(b["low"]), float(b["close"])
        trs.append(h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev)))
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
    highs: list[float] = []
    lows: list[float] = []
    for i in range(wing, len(bars) - wing):
        window = bars[i - wing:i + wing + 1]
        hi, lo = float(bars[i]["high"]), float(bars[i]["low"])
        if hi >= max(float(x["high"]) for x in window):
            highs.append(hi)
        if lo <= min(float(x["low"]) for x in window):
            lows.append(lo)
    return highs, lows


def _base_unavailable() -> dict[str, Any]:
    return {
        "state": "UNAVAILABLE", "reasoning_mode": "SINGLE_PROFESSIONAL_CORE",
        "question": QUESTION, "thesis": "Insufficient closed-candle history; no opportunity thesis is formed.",
        "regime": "UNRESOLVED", "direction": "NEUTRAL", "phase": "UNRESOLVED", "opportunity": "NONE",
        "opportunity_state": "WAIT", "opportunity_maturity": "UNPROVEN", "quality": "UNPROVEN",
        "opportunity_quality": "LOW", "opportunity_decision": "WAIT", "edge_assessment": "NO_EDGE",
        "alignment_with_e1": "INCONCLUSIVE", "independence": "E2_FIRST_E1_CROSS_CHECK",
        "auction_state": "UNKNOWN", "auction_phase": "TRANSITION", "location_context": "UNKNOWN",
        "regime_confidence": 0.0, "confidence": 0.0, "opportunity_score": 0.0,
        "acceptance_quality": "UNPROVEN", "timing_state": "WAIT", "decision_factors": [],
        "observations": [], "evidence": [], "evidence_map": {"directional_pressure": "NEUTRAL", "location": "MID_RANGE"},
        "counter_evidence": ["insufficient closed-candle history"], "counter_evidence_severity": "THESIS_INVALIDATION",
        "missing_evidence": [f"{MIN_BARS} valid closed candles"], "invalidation_evidence": [],
        "why_not_trade": ["insufficient market data"],
        "counterfactual": ["without sufficient history, no directional thesis is trustworthy"],
        "decision": None, "entry": None, "trigger": None, "risk": None, "gate": None,
        "reason_codes": ["INSUFFICIENT_MARKET_DATA"],
        "professional_reasoning": {
            "question": QUESTION, "conclusion": "NO_OPPORTUNITY_THESIS", "why_now": "Insufficient evidence.",
            "expected_path": "Wait for sufficient closed-candle history.", "required_evidence": [f"{MIN_BARS} valid closed candles"],
            "invalidation_conditions": ["data insufficiency"], "timing": "WAIT", "opportunity_quality": "LOW",
            "counter_evidence_count": 1, "counter_evidence": ["insufficient market data"],
            "independent_thesis": True, "e1_used_as": "CROSS_CHECK_ONLY", "entry_authorized": False,
        },
    }


def _candidate_quality(direction: str, regime: str, *, structure: bool, acceptance: bool,
                       rejection: bool, displacement: bool, pullback: bool, location_good: bool,
                       space_ok: bool, overextended: bool, efficiency: float, volatility: float) -> float:
    """Quality of an opportunity, not probability of profit and not an entry score."""
    if direction == "NEUTRAL":
        return 0.0
    value = 0.0
    value += 0.18 if structure else 0.0
    value += 0.18 if acceptance or displacement else 0.0
    value += 0.14 if pullback and regime == "TREND" else 0.0
    value += 0.12 if location_good else 0.0
    value += 0.14 if space_ok else -0.12
    value += 0.10 if efficiency >= 0.30 else 0.0
    value += 0.08 if 0.75 <= volatility <= 1.55 else -0.04
    value -= 0.18 if rejection else 0.0
    value -= 0.18 if overextended else 0.0
    return max(0.0, min(1.0, value))


def analyze_e2(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Professional opportunity brain; single core, no E2 sub-engines.

    The reasoning order is deliberately:
      1) reconstruct price/auction state independently;
      2) generate competing opportunity hypotheses;
      3) compare them and reject weak/late/contradictory ideas;
      4) define expected path, missing evidence and invalidation;
      5) only then cross-check E1.

    E2 never authorizes an entry, risk order or trade decision. E9 owns that.
    """
    bs = _bars(snapshot)
    if len(bs) < MIN_BARS:
        return _base_unavailable()

    h = [float(b["high"]) for b in bs]
    l = [float(b["low"]) for b in bs]
    c = [float(b["close"]) for b in bs]
    o = [float(b["open"]) for b in bs]
    last = c[-1]
    atr = max(_atr(bs), 1e-12)

    ema20 = _ema(c, 20)
    ema50 = _ema(c, 50)
    ema20_prev = _ema(c[:-5], 20)
    ema50_prev = _ema(c[:-5], 50)
    ema_gap = (ema20 - ema50) / atr
    ema20_slope = (ema20 - ema20_prev) / atr
    ema50_slope = (ema50 - ema50_prev) / atr

    ranges = [max(float(b["high"]) - float(b["low"]), 0.0) for b in bs]
    avg20 = max(mean(ranges[-20:]), 1e-12)
    vol_ratio = mean(ranges[-5:]) / avg20
    slope5 = (c[-1] - c[-6]) / atr
    slope20 = (c[-1] - c[-21]) / atr
    slope40 = (c[-1] - c[-41]) / atr
    travelled12 = max(sum(ranges[-12:]), 1e-12)
    efficiency12 = abs(c[-1] - c[-13]) / travelled12

    hi20, lo20 = max(h[-21:-1]), min(l[-21:-1])
    hi40, lo40 = max(h[-41:-1]), min(l[-41:-1])
    width40 = max(hi40 - lo40, 1e-12)
    pos40 = max(0.0, min(1.0, (last - lo40) / width40))
    pos20 = max(0.0, min(1.0, (last - lo20) / max(hi20 - lo20, 1e-12)))

    ph, pl = _pivots(bs)
    hh = len(ph) >= 2 and ph[-1] > ph[-2]
    lh = len(ph) >= 2 and ph[-1] < ph[-2]
    hl = len(pl) >= 2 and pl[-1] > pl[-2]
    ll = len(pl) >= 2 and pl[-1] < pl[-2]
    bull_structure, bear_structure = hh and hl, lh and ll

    up_evidence = sum((ema_gap > 0.35, ema20_slope > 0.08, ema50_slope > -0.05,
                       slope5 > 0.20, slope20 > 0.45, bull_structure, efficiency12 >= 0.30))
    down_evidence = sum((ema_gap < -0.35, ema20_slope < -0.08, ema50_slope < 0.05,
                         slope5 < -0.20, slope20 < -0.45, bear_structure, efficiency12 >= 0.30))
    compressed = vol_ratio < 0.72
    expanding = vol_ratio > 1.28
    balanced = abs(slope20) < 0.65 and efficiency12 < 0.30 and width40 / atr < 8.5

    span = max(h[-1] - l[-1], 1e-12)
    body_ratio = abs(last - o[-1]) / span
    close_pos = (last - l[-1]) / span
    upper_wick = (h[-1] - max(o[-1], last)) / span
    lower_wick = (min(o[-1], last) - l[-1]) / span
    broke_up, broke_down = last > hi20, last < lo20
    swept_up = h[-1] > hi20 and last <= hi20
    swept_down = l[-1] < lo20 and last >= lo20
    accepted_up = broke_up and close_pos >= 0.65 and body_ratio >= 0.45
    accepted_down = broke_down and close_pos <= 0.35 and body_ratio >= 0.45
    rejected_up = swept_up and close_pos <= 0.45 and upper_wick >= 0.20
    rejected_down = swept_down and close_pos >= 0.55 and lower_wick >= 0.20
    displacement_up = body_ratio >= 0.60 and close_pos >= 0.75 and span >= 1.25 * avg20
    displacement_down = body_ratio >= 0.60 and close_pos <= 0.25 and span >= 1.25 * avg20

    up_impulse = c[-6] > c[-13] and (c[-6] - c[-13]) / atr >= 0.80
    down_impulse = c[-6] < c[-13] and (c[-13] - c[-6]) / atr >= 0.80
    pullback_up = up_impulse and last < c[-6] and last > lo20 and ema20 >= ema50
    pullback_down = down_impulse and last > c[-6] and last < hi20 and ema20 <= ema50

    # Independent market auction classification. E1 is not consulted here.
    if accepted_up and accepted_down:
        regime, direction, auction_state = "TRANSITION", "NEUTRAL", "TWO_SIDED_ACCEPTANCE"
    elif accepted_up and not rejected_up:
        regime, direction, auction_state = "BREAKOUT", "UP", "ACCEPTANCE_UP"
    elif accepted_down and not rejected_down:
        regime, direction, auction_state = "BREAKOUT", "DOWN", "ACCEPTANCE_DOWN"
    elif rejected_up and not rejected_down and pos40 >= 0.70:
        regime, direction, auction_state = "MEAN_REVERSION", "DOWN", "FAILED_AUCTION_HIGH"
    elif rejected_down and not rejected_up and pos40 <= 0.30:
        regime, direction, auction_state = "MEAN_REVERSION", "UP", "FAILED_AUCTION_LOW"
    elif up_evidence >= 5 and up_evidence > down_evidence + 1:
        regime, direction, auction_state = "TREND", "UP", "DIRECTIONAL_AUCTION_UP"
    elif down_evidence >= 5 and down_evidence > up_evidence + 1:
        regime, direction, auction_state = "TREND", "DOWN", "DIRECTIONAL_AUCTION_DOWN"
    elif balanced or (compressed and abs(up_evidence - down_evidence) <= 2):
        regime, direction, auction_state = "RANGE", "NEUTRAL", "BALANCED_AUCTION"
    elif abs(up_evidence - down_evidence) <= 1 or abs(ema_gap) < 0.30:
        regime, direction, auction_state = "TRANSITION", "NEUTRAL", "UNCOMMITTED_AUCTION"
    else:
        regime, direction, auction_state = "RANGE", "NEUTRAL", "NO_EDGE"

    # Build competing opportunity hypotheses rather than accepting the first pattern.
    candidates: list[dict[str, Any]] = []
    if up_evidence >= 4:
        candidates.append({"name": "TREND_PULLBACK_CONTINUATION", "direction": "UP", "regime": "TREND",
                           "structure": bull_structure, "acceptance": accepted_up, "rejection": rejected_up,
                           "displacement": displacement_up, "pullback": pullback_up})
        candidates.append({"name": "TREND_CONTINUATION", "direction": "UP", "regime": "TREND",
                           "structure": bull_structure, "acceptance": accepted_up, "rejection": rejected_up,
                           "displacement": displacement_up, "pullback": False})
    if down_evidence >= 4:
        candidates.append({"name": "TREND_PULLBACK_CONTINUATION", "direction": "DOWN", "regime": "TREND",
                           "structure": bear_structure, "acceptance": accepted_down, "rejection": rejected_down,
                           "displacement": displacement_down, "pullback": pullback_down})
        candidates.append({"name": "TREND_CONTINUATION", "direction": "DOWN", "regime": "TREND",
                           "structure": bear_structure, "acceptance": accepted_down, "rejection": rejected_down,
                           "displacement": displacement_down, "pullback": False})
    if accepted_up:
        candidates.append({"name": "BREAKOUT_CONTINUATION", "direction": "UP", "regime": "BREAKOUT",
                           "structure": bull_structure, "acceptance": True, "rejection": rejected_up,
                           "displacement": displacement_up, "pullback": False})
    if accepted_down:
        candidates.append({"name": "BREAKOUT_CONTINUATION", "direction": "DOWN", "regime": "BREAKOUT",
                           "structure": bear_structure, "acceptance": True, "rejection": rejected_down,
                           "displacement": displacement_down, "pullback": False})
    if rejected_down and pos40 <= 0.30:
        candidates.append({"name": "LIQUIDITY_REVERSAL", "direction": "UP", "regime": "MEAN_REVERSION",
                           "structure": bull_structure, "acceptance": False, "rejection": True,
                           "displacement": displacement_up, "pullback": False})
    if rejected_up and pos40 >= 0.70:
        candidates.append({"name": "LIQUIDITY_REVERSAL", "direction": "DOWN", "regime": "MEAN_REVERSION",
                           "structure": bear_structure, "acceptance": False, "rejection": True,
                           "displacement": displacement_down, "pullback": False})

    location_by_direction = {
        "UP": pos40 <= 0.75 and pos40 >= 0.10,
        "DOWN": pos40 >= 0.25 and pos40 <= 0.90,
    }
    scored: list[dict[str, Any]] = []
    for item in candidates:
        d = item["direction"]
        space = max((hi40 - last) / atr, 0.0) if d == "UP" else max((last - lo40) / atr, 0.0)
        invalidation_distance = max((last - lo40) / atr, 0.0) if d == "UP" else max((hi40 - last) / atr, 0.0)
        space_ok = space >= 1.0
        extended = (d == "UP" and pos40 >= 0.92) or (d == "DOWN" and pos40 <= 0.08)
        q = _candidate_quality(d, item["regime"], structure=item["structure"], acceptance=item["acceptance"],
                               rejection=item["rejection"], displacement=item["displacement"],
                               pullback=item["pullback"], location_good=location_by_direction[d],
                               space_ok=space_ok, overextended=extended, efficiency=efficiency12,
                               volatility=vol_ratio)
        item = dict(item, quality=q, space_atr=space, invalidation_atr=invalidation_distance,
                    space_ok=space_ok, extended=extended)
        scored.append(item)

    scored.sort(key=lambda x: (x["quality"], x["space_atr"], x["structure"]), reverse=True)
    best = scored[0] if scored else None
    second = scored[1] if len(scored) > 1 else None

    # A professional trader does not force a trade when two ideas are close.
    ambiguity = bool(best and second and abs(float(best["quality"]) - float(second["quality"])) < 0.10
                     and best["direction"] != second["direction"])
    if best and ambiguity:
        direction = "NEUTRAL"
        regime = "TRANSITION"
        opportunity = "WAIT_FOR_REPRICING"
        phase = "AMBIGUOUS"
        auction_state = "COMPETING_HYPOTHESES"
    elif best:
        direction = best["direction"]
        opportunity = best["name"]
        regime = best["regime"]
        if opportunity == "TREND_PULLBACK_CONTINUATION":
            phase = "PULLBACK" if best["pullback"] else "DEVELOPING"
        elif opportunity == "BREAKOUT_CONTINUATION":
            phase = "ACCEPTANCE"
        elif opportunity == "LIQUIDITY_REVERSAL":
            phase = "REJECTION"
        else:
            phase = "EXPANSION" if best["displacement"] else "DEVELOPING"
    else:
        direction = "NEUTRAL"
        opportunity = "WAIT_FOR_REPRICING" if regime == "TRANSITION" else "WAIT_FOR_RANGE_EDGE"
        phase = "TRANSITION" if regime == "TRANSITION" else "BALANCED"

    location = "EDGE_LOW" if pos40 <= 0.20 else "EDGE_HIGH" if pos40 >= 0.80 else "MID_RANGE"
    if direction == "UP":
        opposing_space_atr = max((hi40 - last) / atr, 0.0)
        invalidation_distance_atr = max((last - lo40) / atr, 0.0)
    elif direction == "DOWN":
        opposing_space_atr = max((last - lo40) / atr, 0.0)
        invalidation_distance_atr = max((hi40 - last) / atr, 0.0)
    else:
        opposing_space_atr = invalidation_distance_atr = 0.0
    space_ok = opposing_space_atr >= 1.0
    overextended = (direction == "UP" and pos40 >= 0.92) or (direction == "DOWN" and pos40 <= 0.08)

    counter: list[str] = []
    missing: list[str] = []
    invalidation: list[str] = []
    if ambiguity:
        counter.append("opposing opportunity hypotheses are too close; directional edge is not decisive")
    if direction == "UP":
        if ema20 < ema50 and not pullback_up: counter.append("short-term structure opposes upside thesis")
        if not bull_structure and regime == "TREND": counter.append("swing structure does not fully confirm upside thesis")
        if rejected_up: counter.append("upside auction shows rejection")
        if not space_ok: counter.append("opposing liquidity is too close")
        if overextended: counter.append("price is materially extended from value")
    elif direction == "DOWN":
        if ema20 > ema50 and not pullback_down: counter.append("short-term structure opposes downside thesis")
        if not bear_structure and regime == "TREND": counter.append("swing structure does not fully confirm downside thesis")
        if rejected_down: counter.append("downside auction shows rejection")
        if not space_ok: counter.append("opposing liquidity is too close")
        if overextended: counter.append("price is materially extended from value")

    if regime == "TREND" and opportunity == "TREND_PULLBACK_CONTINUATION":
        if not (accepted_up or accepted_down or displacement_up or displacement_down):
            missing.append("controlled pullback plus directional rejection/holding")
        else:
            missing.append("follow-through after pullback")
    if opportunity == "BREAKOUT_CONTINUATION" and not expanding:
        missing.append("volatility expansion and acceptance after breakout")
    if opportunity == "LIQUIDITY_REVERSAL":
        missing.append("rejection must hold and produce follow-through back into value")
    if opportunity == "WAIT_FOR_RANGE_EDGE":
        missing.append("meaningful range-edge interaction")
    if opportunity == "WAIT_FOR_REPRICING" or ambiguity:
        missing.append("clear directional commitment / repricing")

    if direction == "UP" and rejected_up and pos40 >= 0.80:
        invalidation.append("upside acceptance failed at a high-value area")
    if direction == "DOWN" and rejected_down and pos40 <= 0.20:
        invalidation.append("downside acceptance failed at a low-value area")
    if direction == "UP" and down_evidence >= up_evidence + 2:
        invalidation.append("independent downside evidence dominates")
    if direction == "DOWN" and up_evidence >= down_evidence + 2:
        invalidation.append("independent upside evidence dominates")

    # E1 is deliberately a late cross-check, never a source of direction.
    e1 = _e1_context(snapshot)
    e1_direction = _direction(e1.get("directional_pressure") or e1.get("direction"))
    e1_state = str(e1.get("market_state") or e1.get("state") or "UNRESOLVED").upper()
    e1_structure = str(e1.get("structure") or "UNRESOLVED").upper()
    if direction == "NEUTRAL" or e1_direction == "NEUTRAL":
        alignment = "INCONCLUSIVE"
    elif direction == e1_direction:
        alignment = "ALIGNED"
    else:
        alignment = "CONFLICT"
        counter.append("E1 directional evidence conflicts with the independent E2 thesis")

    # Quality is evidence-weighted, not a disguised trade probability.
    best_quality = float(best["quality"]) if best else 0.0
    directional_strength = max(up_evidence, down_evidence) / 7.0
    evidence_penalty = min(0.45, 0.08 * len(counter))
    missing_penalty = min(0.25, 0.07 * len(missing))
    alignment_adjustment = 0.04 if alignment == "ALIGNED" else -0.04 if alignment == "CONFLICT" else 0.0
    confidence = max(0.0, min(1.0, 0.45 * best_quality + 0.30 * directional_strength + 0.25
                              - evidence_penalty - missing_penalty + alignment_adjustment))
    opportunity_score = max(0.0, min(1.0, 0.65 * best_quality + 0.35 * confidence))

    if invalidation:
        maturity, opportunity_state, quality = "INVALIDATED", "INVALIDATED", "REJECTED"
    elif direction == "NEUTRAL":
        maturity, opportunity_state, quality = "WAITING", "WAIT", "UNPROVEN"
    elif counter or missing:
        maturity, opportunity_state, quality = "DEVELOPING", "DEVELOPING", "STRONG_CONTEXT" if opportunity_score >= 0.70 else "DEVELOPING"
    else:
        maturity, opportunity_state, quality = "MATURE_CONTEXT", "CONTEXT_READY", "STRONG" if opportunity_score >= 0.78 else "DEVELOPING"

    if invalidation:
        timing_state = "MISSED"
    elif direction == "NEUTRAL":
        timing_state = "WAIT"
    elif overextended:
        timing_state = "LATE"
    elif missing:
        timing_state = "READY_FOR_CONFIRMATION"
    else:
        timing_state = "DEVELOPING"

    opportunity_quality = "HIGH" if opportunity_score >= 0.78 and not counter else "MEDIUM" if opportunity_score >= 0.55 else "LOW"
    acceptance_quality = "CONFIRMED" if accepted_up or accepted_down else "STRONG" if displacement_up or displacement_down else "UNPROVEN"

    if invalidation or direction == "NEUTRAL":
        opportunity_decision, edge_assessment = ("NO_OPPORTUNITY", "NO_EDGE") if invalidation else ("WAIT", "NO_EDGE")
    elif overextended or not space_ok or counter or missing:
        opportunity_decision, edge_assessment = "WATCH", "EDGE_CONDITIONAL"
    elif opportunity_score >= 0.72:
        opportunity_decision, edge_assessment = "ACTIONABLE_BIAS", "EDGE_PRESENT"
    else:
        opportunity_decision, edge_assessment = "WATCH", "EDGE_CONDITIONAL"

    why_not_trade: list[str] = []
    if direction == "NEUTRAL": why_not_trade.append("no decisive directional opportunity is established")
    if ambiguity: why_not_trade.append("competing hypotheses are too close to justify commitment")
    if overextended: why_not_trade.append("late location: price is too extended for immediate participation")
    if direction != "NEUTRAL" and not space_ok: why_not_trade.append("insufficient opposing space for a favorable path")
    why_not_trade.extend(f"missing: {x}" for x in missing)
    why_not_trade.extend(f"counter-evidence: {x}" for x in counter)
    why_not_trade.extend(f"invalidated: {x}" for x in invalidation)
    if not why_not_trade:
        why_not_trade.append("E2 has contextual edge only; E9 must still validate confirmation and economics")

    if direction == "UP":
        counterfactual = ["if supporting structure fails and downside evidence dominates, abandon the upside thesis"]
    elif direction == "DOWN":
        counterfactual = ["if opposing structure is reclaimed and upside evidence dominates, abandon the downside thesis"]
    else:
        counterfactual = ["if one side gains sustained acceptance and follow-through, replace the neutral thesis with that directional thesis"]
    if overextended:
        counterfactual.append("if price returns to favorable location without losing structure, reassess the same directional idea")

    expected_path = {
        "TREND_PULLBACK_CONTINUATION": "impulse persists -> controlled pullback -> rejection/holding -> confirmation -> continuation",
        "TREND_CONTINUATION": "directional pressure persists -> acceptance -> confirmation -> follow-through",
        "BREAKOUT_CONTINUATION": "breakout holds -> acceptance beyond prior range -> expansion -> follow-through",
        "LIQUIDITY_REVERSAL": "liquidity is swept -> rejection holds -> re-entry into value -> reversal follow-through",
        "RANGE_ROTATION_UP": "lower-edge rejection holds -> rotation toward midpoint/high",
        "RANGE_ROTATION_DOWN": "upper-edge rejection holds -> rotation toward midpoint/low",
    }.get(opportunity, "market reprices and provides clear evidence before the opportunity can mature")

    reason_codes: list[str] = []
    if invalidation: reason_codes.append("THESIS_INVALIDATED")
    if alignment == "CONFLICT": reason_codes.append("E1_E2_DIRECTION_CONFLICT")
    if ambiguity: reason_codes.append("COMPETING_HYPOTHESES")
    if missing: reason_codes.append("MISSING_OPPORTUNITY_CONFIRMATION")
    if counter: reason_codes.append("COUNTER_EVIDENCE_PRESENT")
    if opportunity not in {"WAIT_FOR_REPRICING", "WAIT_FOR_RANGE_EDGE"} and not invalidation and direction != "NEUTRAL":
        reason_codes.append("OPPORTUNITY_THESIS_ESTABLISHED")
    if not reason_codes: reason_codes.append("NO_ACTIONABLE_OPPORTUNITY")

    observations = [
        f"ema_gap_atr={ema_gap:.3f}", f"ema20_slope_atr={ema20_slope:.3f}", f"ema50_slope_atr={ema50_slope:.3f}",
        f"slope5_atr={slope5:.3f}", f"slope20_atr={slope20:.3f}", f"slope40_atr={slope40:.3f}",
        f"volatility_ratio={vol_ratio:.3f}", f"efficiency12={efficiency12:.3f}",
        f"up_evidence={up_evidence}/7", f"down_evidence={down_evidence}/7",
        f"position_40={pos40:.3f}", f"position_20={pos20:.3f}", f"opposing_space_atr={opposing_space_atr:.3f}",
        f"invalidation_distance_atr={invalidation_distance_atr:.3f}", f"accepted_up={accepted_up}", f"accepted_down={accepted_down}",
        f"rejected_up={rejected_up}", f"rejected_down={rejected_down}", f"displacement_up={displacement_up}", f"displacement_down={displacement_down}",
        f"pullback_up={pullback_up}", f"pullback_down={pullback_down}",
        f"candidate_count={len(scored)}", f"best_candidate_quality={best_quality:.3f}", f"hypothesis_ambiguity={ambiguity}",
    ]
    candidate_summary = [
        {"name": x["name"], "direction": x["direction"], "quality": round(float(x["quality"]), 4),
         "space_atr": round(float(x["space_atr"]), 4), "space_ok": bool(x["space_ok"]), "extended": bool(x["extended"])}
        for x in scored[:6]
    ]
    decision_factors = [
        f"independent_regime={regime}", f"independent_direction={direction}", f"auction_state={auction_state}",
        f"opportunity={opportunity}", f"phase={phase}", f"location={location}", f"best_candidate_quality={best_quality:.3f}",
        f"candidate_count={len(scored)}", f"alignment_with_e1={alignment}", f"timing={timing_state}",
        f"opportunity_score={opportunity_score:.3f}", f"decision={opportunity_decision}",
    ]
    thesis = f"Independent E2 thesis: {regime}/{direction} creates {opportunity} at {phase}; thesis is {maturity.lower()} and requires downstream confirmation."
    reasoning = {
        "question": QUESTION, "conclusion": thesis,
        "why_now": f"{auction_state}; {location}; opposing space={opposing_space_atr:.2f} ATR",
        "expected_path": expected_path, "required_evidence": list(dict.fromkeys(missing)),
        "invalidation_conditions": list(invalidation) or ["opposing structure becomes dominant", "auction invalidates the expected path"],
        "timing": timing_state, "opportunity_quality": opportunity_quality,
        "opportunity_decision": opportunity_decision, "edge_assessment": edge_assessment,
        "candidate_comparison": candidate_summary, "counter_evidence_count": len(counter),
        "counter_evidence": counter, "why_not_trade": why_not_trade, "counterfactual": counterfactual,
        "independent_thesis": True, "e1_used_as": "CROSS_CHECK_ONLY", "entry_authorized": False,
    }

    return {
        "state": "OPPORTUNITY_ANALYSIS_COMPLETE", "reasoning_mode": "SINGLE_PROFESSIONAL_CORE", "question": QUESTION,
        "thesis": thesis, "regime": regime, "direction": direction, "phase": phase, "opportunity": opportunity,
        "opportunity_state": opportunity_state, "opportunity_maturity": maturity, "quality": quality,
        "opportunity_quality": opportunity_quality, "opportunity_score": round(opportunity_score, 4),
        "opportunity_decision": opportunity_decision, "edge_assessment": edge_assessment,
        "alignment_with_e1": alignment, "independence": "E2_FIRST_E1_CROSS_CHECK", "auction_state": auction_state,
        "auction_phase": "ACCEPTANCE" if "ACCEPTANCE" in auction_state else "REJECTION" if "FAILED_AUCTION" in auction_state else "BALANCE" if "BALANCED" in auction_state else "REPRICING" if direction != "NEUTRAL" else "TRANSITION",
        "acceptance_quality": acceptance_quality, "location_context": location,
        "regime_confidence": round(directional_strength, 4), "confidence": round(confidence, 4),
        "timing_state": timing_state, "decision_factors": decision_factors,
        "observations": observations,
        "evidence": [
            f"UP_EVIDENCE={up_evidence}/7", f"DOWN_EVIDENCE={down_evidence}/7",
            f"STRUCTURE_BULL={bull_structure}", f"STRUCTURE_BEAR={bear_structure}",
            f"ACCEPTANCE_UP={accepted_up}", f"ACCEPTANCE_DOWN={accepted_down}",
            f"REJECTION_UP={rejected_up}", f"REJECTION_DOWN={rejected_down}",
            f"EXPANSION={expanding}", f"COMPRESSION={compressed}", f"SPACE_OK={space_ok}",
            f"E1_STATE={e1_state}", f"E1_STRUCTURE={e1_structure}",
        ],
        "candidate_comparison": candidate_summary,
        "evidence_map": {
            "directional_pressure": direction, "location": location, "regime": regime,
            "auction_state": auction_state, "space_ok": space_ok, "overextended": overextended,
            "alignment_with_e1": alignment, "hypothesis_ambiguity": ambiguity,
        },
        "counter_evidence": counter,
        "counter_evidence_severity": "THESIS_INVALIDATION" if invalidation else "MATERIAL" if counter else "NONE",
        "missing_evidence": missing, "invalidation_evidence": invalidation,
        "why_not_trade": why_not_trade, "counterfactual": counterfactual,
        "opposing_space_atr": round(opposing_space_atr, 4), "invalidation_distance_atr": round(invalidation_distance_atr, 4),
        "decision": None, "entry": None, "trigger": None, "risk": None, "gate": None,
        "trade_decision_authority": "E9_ONLY", "professional_reasoning": reasoning,
        "reason_codes": list(dict.fromkeys(reason_codes)),
    }
