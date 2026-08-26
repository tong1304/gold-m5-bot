from __future__ import annotations

from statistics import mean
from typing import Any

QUESTION = "What opportunity is the market offering right now?"
MIN_BARS = 80


def _bars(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    bars = snapshot.get("bars") or []
    return [b for b in bars if isinstance(b, dict) and all(k in b for k in ("open", "high", "low", "close"))]


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
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
    value = str(value or "NEUTRAL").upper().strip()
    if value in {"UP", "BULLISH", "BUY", "LONG", "TREND_UP"}:
        return "UP"
    if value in {"DOWN", "BEARISH", "SELL", "SHORT", "TREND_DOWN"}:
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
        hi = float(bars[i]["high"])
        lo = float(bars[i]["low"])
        if hi >= max(float(x["high"]) for x in window):
            highs.append(hi)
        if lo <= min(float(x["low"]) for x in window):
            lows.append(lo)
    return highs, lows


def _base_unavailable() -> dict[str, Any]:
    return {
        "state": "UNAVAILABLE", "reasoning_mode": "SINGLE_PROFESSIONAL_CORE",
        "question": QUESTION,
        "thesis": "Insufficient closed-candle history; no opportunity thesis is formed.",
        "regime": "UNRESOLVED", "direction": "NEUTRAL", "phase": "UNRESOLVED",
        "opportunity": "NONE", "opportunity_state": "UNPROVEN", "opportunity_maturity": "UNPROVEN",
        "quality": "UNPROVEN", "opportunity_quality": "LOW", "alignment_with_e1": "INCONCLUSIVE",
        "independence": "E2_FIRST_E1_CROSS_CHECK", "auction_state": "UNKNOWN", "auction_phase": "TRANSITION",
        "location_context": "UNKNOWN", "regime_confidence": 0.0, "confidence": 0.0,
        "opportunity_score": 0.0, "acceptance_quality": "UNPROVEN", "timing_state": "WAIT",
        "decision_factors": [], "observations": [], "evidence": [],
        "counter_evidence": ["insufficient closed-candle history"], "counter_evidence_severity": "THESIS_INVALIDATION",
        "missing_evidence": [f"{MIN_BARS} valid closed candles"], "invalidation_evidence": [],
        "decision": None, "entry": None, "trigger": None, "risk": None, "gate": None,
        "reason_codes": ["INSUFFICIENT_MARKET_DATA"],
        "professional_reasoning": {
            "question": QUESTION, "conclusion": "NO_OPPORTUNITY_THESIS",
            "why_now": "Insufficient evidence to identify a tradable auction.",
            "expected_path": "Wait for sufficient closed-candle history.",
            "required_evidence": [f"{MIN_BARS} valid closed candles"],
            "invalidation_conditions": ["data insufficiency"],
            "timing": "WAIT", "opportunity_quality": "LOW", "counter_evidence_count": 1,
        },
    }


def analyze_e2(snapshot: dict[str, Any]) -> dict[str, Any]:
    """E2 professional opportunity brain.

    E2 is a single reasoning core. It independently asks whether the current
    auction creates a tradable opportunity, what playbook best explains it,
    what path must occur for the thesis to work, and what evidence would kill
    the thesis. E1 is consulted only after the independent thesis is formed.

    E2 never emits an entry command, trade gate, or execution authorization.
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

    # 1) Independently reconstruct the auction state.
    ema20 = _ema(c, 20)
    ema50 = _ema(c, 50)
    ema20_prev5 = _ema(c[:-5], 20)
    ema50_prev5 = _ema(c[:-5], 50)
    ema_gap = (ema20 - ema50) / atr
    ema20_slope = (ema20 - ema20_prev5) / atr
    ema50_slope = (ema50 - ema50_prev5) / atr

    ranges = [max(float(b["high"]) - float(b["low"]), 0.0) for b in bs]
    avg20_range = max(mean(ranges[-20:]), 1e-12)
    avg5_range = mean(ranges[-5:])
    vol_ratio = avg5_range / avg20_range
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

    up_score = sum((ema_gap > 0.35, ema20_slope > 0.08, ema50_slope > -0.05,
                    slope5 > 0.20, slope20 > 0.45, bull_structure, efficiency12 >= 0.30))
    down_score = sum((ema_gap < -0.35, ema20_slope < -0.08, ema50_slope < 0.05,
                      slope5 < -0.20, slope20 < -0.45, bear_structure, efficiency12 >= 0.30))
    compressed, expanding = vol_ratio < 0.72, vol_ratio > 1.28
    balanced = abs(slope20) < 0.65 and efficiency12 < 0.30 and width40 / atr < 8.5

    # 2) Read actual auction behaviour rather than treating indicators as commands.
    span = max(h[-1] - l[-1], 1e-12)
    body_ratio = abs(last - o[-1]) / span
    close_pos = (last - l[-1]) / span
    upper_wick = (h[-1] - max(o[-1], last)) / span
    lower_wick = (min(o[-1], last) - l[-1]) / span
    broke_up, broke_down = last > hi20, last < lo20
    swept_up, swept_down = h[-1] > hi20 and last <= hi20, l[-1] < lo20 and last >= lo20
    accepted_up = broke_up and close_pos >= 0.65 and body_ratio >= 0.45
    accepted_down = broke_down and close_pos <= 0.35 and body_ratio >= 0.45
    rejected_up = swept_up and close_pos <= 0.45 and upper_wick >= 0.20
    rejected_down = swept_down and close_pos >= 0.55 and lower_wick >= 0.20
    displacement_up = body_ratio >= 0.60 and close_pos >= 0.75 and span >= 1.25 * avg20_range
    displacement_down = body_ratio >= 0.60 and close_pos <= 0.25 and span >= 1.25 * avg20_range

    up_impulse = c[-6] > c[-13] and (c[-6] - c[-13]) / atr >= 0.80
    down_impulse = c[-6] < c[-13] and (c[-13] - c[-6]) / atr >= 0.80
    pullback_up = up_impulse and last < c[-6] and last > lo20 and ema20 >= ema50
    pullback_down = down_impulse and last > c[-6] and last < hi20 and ema20 <= ema50

    # 3) Build one independent thesis. No E1 dependency here.
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
    elif up_score >= 5 and up_score > down_score + 1:
        regime, direction, auction_state = "TREND", "UP", "DIRECTIONAL_AUCTION_UP"
    elif down_score >= 5 and down_score > up_score + 1:
        regime, direction, auction_state = "TREND", "DOWN", "DIRECTIONAL_AUCTION_DOWN"
    elif balanced or (compressed and abs(up_score - down_score) <= 2):
        regime, direction, auction_state = "RANGE", "NEUTRAL", "BALANCED_AUCTION"
    elif abs(up_score - down_score) <= 1 or abs(ema_gap) < 0.30:
        regime, direction, auction_state = "TRANSITION", "NEUTRAL", "UNCOMMITTED_AUCTION"
    else:
        regime, direction, auction_state = "RANGE", "NEUTRAL", "NO_EDGE"

    # 4) Name the playbook without pretending the playbook is an entry signal.
    if regime == "TREND" and direction == "UP":
        opportunity, phase = ("TREND_PULLBACK_CONTINUATION", "PULLBACK") if pullback_up else (("TREND_CONTINUATION", "EXPANSION") if displacement_up else ("TREND_CONTINUATION", "DEVELOPING"))
    elif regime == "TREND" and direction == "DOWN":
        opportunity, phase = ("TREND_PULLBACK_CONTINUATION", "PULLBACK") if pullback_down else (("TREND_CONTINUATION", "EXPANSION") if displacement_down else ("TREND_CONTINUATION", "DEVELOPING"))
    elif regime == "BREAKOUT":
        opportunity, phase = "BREAKOUT_CONTINUATION", "ACCEPTANCE"
    elif regime == "MEAN_REVERSION":
        opportunity, phase = "LIQUIDITY_REVERSAL", "REJECTION"
    elif regime == "RANGE" and pos40 <= 0.20 and rejected_down:
        opportunity, direction, phase = "RANGE_ROTATION_UP", "UP", "EDGE_REJECTION"
    elif regime == "RANGE" and pos40 >= 0.80 and rejected_up:
        opportunity, direction, phase = "RANGE_ROTATION_DOWN", "DOWN", "EDGE_REJECTION"
    elif regime == "RANGE":
        opportunity, phase = "WAIT_FOR_RANGE_EDGE", "BALANCED"
    else:
        opportunity, phase = "WAIT_FOR_REPRICING", "TRANSITION"

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

    # 5) Professional thinking requires an active search for what could make the idea wrong.
    counter: list[str] = []
    missing: list[str] = []
    invalidation: list[str] = []
    if direction == "UP":
        if ema20 < ema50 and not pullback_up: counter.append("short-term structure opposes upside thesis")
        if regime == "TREND" and not bull_structure: counter.append("swing structure does not fully confirm upside trend")
        if rejected_up: counter.append("upside auction shows rejection")
        if not space_ok: counter.append("opposing liquidity is too close")
        if overextended: counter.append("price is materially extended from value")
    elif direction == "DOWN":
        if ema20 > ema50 and not pullback_down: counter.append("short-term structure opposes downside thesis")
        if regime == "TREND" and not bear_structure: counter.append("swing structure does not fully confirm downside trend")
        if rejected_down: counter.append("downside auction shows rejection")
        if not space_ok: counter.append("opposing liquidity is too close")
        if overextended: counter.append("price is materially extended from value")

    if regime == "TREND" and phase == "PULLBACK": missing.append("follow-through after pullback")
    if regime == "BREAKOUT" and not expanding: missing.append("volatility expansion after breakout")
    if regime == "RANGE" and phase == "BALANCED": missing.append("meaningful range-edge interaction")
    if regime == "TRANSITION": missing.append("directional repricing / commitment")
    if regime == "MEAN_REVERSION" and not (rejected_up or rejected_down): missing.append("confirmed liquidity rejection")

    if direction == "UP" and rejected_up and pos40 >= 0.80: invalidation.append("upside acceptance failed at a high-value area")
    if direction == "DOWN" and rejected_down and pos40 <= 0.20: invalidation.append("downside acceptance failed at a low-value area")
    if direction == "UP" and down_score >= up_score + 2: invalidation.append("independent downside evidence dominates")
    if direction == "DOWN" and up_score >= down_score + 2: invalidation.append("independent upside evidence dominates")

    # 6) Only now compare the independent thesis with E1.
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

    # 7) Separate thesis quality from execution confirmation.
    directional_strength = max(up_score, down_score) / 7.0
    auction_quality = 1.0 if auction_state not in {"NO_EDGE", "UNCOMMITTED_AUCTION"} else 0.45
    evidence_penalty = min(0.45, 0.10 * len(counter))
    missing_penalty = min(0.25, 0.08 * len(missing))
    alignment_bonus = 0.10 if alignment == "ALIGNED" else -0.10 if alignment == "CONFLICT" else 0.0
    confidence = max(0.0, min(1.0, 0.45 * directional_strength + 0.30 * auction_quality + 0.25 + alignment_bonus - evidence_penalty - missing_penalty))
    opportunity_score = max(0.0, min(1.0, confidence * (0.85 if space_ok else 0.55) * (0.65 if overextended else 1.0)))

    if invalidation:
        maturity, opportunity_state, quality = "INVALIDATED", "INVALIDATED", "REJECTED"
    elif direction == "NEUTRAL":
        maturity, opportunity_state, quality = ("WAITING", "UNPROVEN", "UNPROVEN")
    elif opportunity in {"WAIT_FOR_REPRICING", "WAIT_FOR_RANGE_EDGE"}:
        maturity, opportunity_state, quality = "WAITING", "DEVELOPING", "WEAK" if confidence < 0.65 else "DEVELOPING"
    elif counter or missing:
        maturity, opportunity_state, quality = "DEVELOPING", "DEVELOPING", "DEVELOPING" if confidence >= 0.60 else "WEAK"
    else:
        maturity, opportunity_state, quality = "MATURE_CONTEXT", "CONTEXT_READY", "STRONG" if confidence >= 0.78 else "DEVELOPING"

    if invalidation:
        timing_state = "MISSED"
    elif direction == "NEUTRAL":
        timing_state = "WAIT"
    elif overextended:
        timing_state = "LATE"
    elif missing:
        timing_state = "READY_FOR_CONFIRMATION" if not counter else "DEVELOPING"
    elif opportunity in {"TREND_PULLBACK_CONTINUATION", "BREAKOUT_CONTINUATION", "LIQUIDITY_REVERSAL"}:
        timing_state = "READY_FOR_CONFIRMATION"
    else:
        timing_state = "DEVELOPING"

    opportunity_quality = "HIGH" if opportunity_score >= 0.78 and not counter else "MEDIUM" if opportunity_score >= 0.55 else "LOW"
    acceptance_quality = "CONFIRMED" if accepted_up or accepted_down else "STRONG" if displacement_up or displacement_down else "UNPROVEN"

    reason_codes: list[str] = []
    if invalidation: reason_codes.append("THESIS_INVALIDATED")
    if alignment == "CONFLICT": reason_codes.append("E1_E2_DIRECTION_CONFLICT")
    if missing: reason_codes.append("MISSING_OPPORTUNITY_CONFIRMATION")
    if counter: reason_codes.append("COUNTER_EVIDENCE_PRESENT")
    if opportunity not in {"NONE", "WAIT_FOR_REPRICING", "WAIT_FOR_RANGE_EDGE"} and not invalidation:
        reason_codes.append("OPPORTUNITY_THESIS_ESTABLISHED")
    if not reason_codes: reason_codes.append("NO_ACTIONABLE_OPPORTUNITY")

    required = list(dict.fromkeys(missing))
    if direction in {"UP", "DOWN"} and not required:
        required.append("downstream setup and confirmation evidence")
    invalidation_conditions = list(invalidation) or [
        "opposing structure becomes dominant" if direction in {"UP", "DOWN"} else "directional commitment fails",
        "auction invalidates the expected path",
    ]
    expected_path = {
        "TREND_PULLBACK_CONTINUATION": "impulse persists -> controlled pullback -> rejection/holding -> continuation",
        "TREND_CONTINUATION": "directional pressure persists -> price accepts continuation -> follow-through",
        "BREAKOUT_CONTINUATION": "breakout holds -> acceptance above/below prior range -> expansion/follow-through",
        "LIQUIDITY_REVERSAL": "liquidity is swept -> rejection holds -> price re-enters value -> reversal develops",
        "RANGE_ROTATION_UP": "lower-edge rejection holds -> price rotates toward range midpoint/high",
        "RANGE_ROTATION_DOWN": "upper-edge rejection holds -> price rotates toward range midpoint/low",
    }.get(opportunity, "market reprices and provides new evidence before a trade thesis can mature")
    why_now = f"{auction_state}; {location}; available opposing space={opposing_space_atr:.2f} ATR"

    observations = [
        f"ema_gap_atr={ema_gap:.3f}", f"ema20_slope_atr={ema20_slope:.3f}", f"ema50_slope_atr={ema50_slope:.3f}",
        f"slope5_atr={slope5:.3f}", f"slope20_atr={slope20:.3f}", f"slope40_atr={slope40:.3f}",
        f"volatility_ratio={vol_ratio:.3f}", f"efficiency12={efficiency12:.3f}", f"up_evidence={up_score}/7", f"down_evidence={down_score}/7",
        f"position_40={pos40:.3f}", f"position_20={pos20:.3f}", f"opposing_space_atr={opposing_space_atr:.3f}",
        f"invalidation_distance_atr={invalidation_distance_atr:.3f}", f"accepted_up={accepted_up}", f"accepted_down={accepted_down}",
        f"rejected_up={rejected_up}", f"rejected_down={rejected_down}", f"displacement_up={displacement_up}", f"displacement_down={displacement_down}",
        f"pullback_up={pullback_up}", f"pullback_down={pullback_down}",
    ]
    decision_factors = [
        f"independent_regime={regime}", f"independent_direction={direction}", f"auction_state={auction_state}",
        f"opportunity={opportunity}", f"phase={phase}", f"location={location}", f"alignment_with_e1={alignment}",
        f"opportunity_score={opportunity_score:.3f}", f"timing={timing_state}",
    ]
    thesis = f"Independent E2 thesis: {regime}/{direction} creates {opportunity} at {phase}; thesis is {maturity.lower()} and requires downstream confirmation."
    reasoning = {
        "question": QUESTION,
        "conclusion": thesis,
        "why_now": why_now,
        "expected_path": expected_path,
        "required_evidence": required,
        "invalidation_conditions": invalidation_conditions,
        "timing": timing_state,
        "opportunity_quality": opportunity_quality,
        "counter_evidence_count": len(counter),
        "counter_evidence": counter,
        "independent_thesis": True,
        "e1_used_as": "CROSS_CHECK_ONLY",
        "entry_authorized": False,
    }

    return {
        "state": "OPPORTUNITY_ANALYSIS_COMPLETE", "reasoning_mode": "SINGLE_PROFESSIONAL_CORE", "question": QUESTION,
        "thesis": thesis, "regime": regime, "direction": direction, "phase": phase, "opportunity": opportunity,
        "opportunity_state": opportunity_state, "opportunity_maturity": maturity, "quality": quality,
        "opportunity_quality": opportunity_quality, "opportunity_score": round(opportunity_score, 4),
        "alignment_with_e1": alignment, "independence": "E2_FIRST_E1_CROSS_CHECK", "auction_state": auction_state,
        "auction_phase": "ACCEPTANCE" if "ACCEPTANCE" in auction_state else "REJECTION" if "FAILED_AUCTION" in auction_state else "BALANCE" if "BALANCED" in auction_state else "REPRICING" if direction != "NEUTRAL" else "TRANSITION",
        "acceptance_quality": acceptance_quality, "location_context": location, "regime_confidence": round(directional_strength, 4),
        "confidence": round(confidence, 4), "timing_state": timing_state, "decision_factors": decision_factors,
        "observations": observations,
        "evidence": [f"UP_EVIDENCE={up_score}/7", f"DOWN_EVIDENCE={down_score}/7", f"STRUCTURE_BULL={bull_structure}", f"STRUCTURE_BEAR={bear_structure}",
                     f"ACCEPTANCE_UP={accepted_up}", f"ACCEPTANCE_DOWN={accepted_down}", f"REJECTION_UP={rejected_up}", f"REJECTION_DOWN={rejected_down}",
                     f"EXPANSION={expanding}", f"COMPRESSION={compressed}", f"SPACE_OK={space_ok}", f"E1_STATE={e1_state}", f"E1_STRUCTURE={e1_structure}"],
        "counter_evidence": counter, "counter_evidence_severity": "THESIS_INVALIDATION" if invalidation else "MATERIAL" if counter else "NONE",
        "missing_evidence": missing, "invalidation_evidence": invalidation,
        "opposing_space_atr": round(opposing_space_atr, 4), "invalidation_distance_atr": round(invalidation_distance_atr, 4),
        "decision": None, "entry": None, "trigger": None, "risk": None, "gate": None,
        "trade_decision_authority": "E9_ONLY", "professional_reasoning": reasoning,
        "reason_codes": list(dict.fromkeys(reason_codes)),
    }
