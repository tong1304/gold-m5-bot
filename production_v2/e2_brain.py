from __future__ import annotations

from statistics import mean
from typing import Any

QUESTION = "What opportunity is the market offering right now?"
MIN_BARS = 80
ARCHITECTURE = "E2_PROFESSIONAL_OPPORTUNITY_CORE_V6"

# E2 is an opportunity analyst only. It never authorizes entry or final trade decisions.
MATURITY_ORDER = {
    "UNPROVEN": 0,
    "EMERGING": 1,
    "DEVELOPING": 2,
    "CONFIRMED": 3,
    "ACTIONABLE": 4,
}


def _bars(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    bars = snapshot.get("bars") or []
    return [
        b for b in bars
        if isinstance(b, dict)
        and all(k in b for k in ("open", "high", "low", "close"))
    ]


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    value = values[0]
    for x in values[1:]:
        value = alpha * x + (1.0 - alpha) * value
    return value


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs: list[float] = []
    prev = float(bars[0]["close"])
    for b in bars[-period:]:
        h = float(b["high"])
        l = float(b["low"])
        trs.append(max(h - l, abs(h - prev), abs(l - prev)))
        prev = float(b["close"])
    return mean(trs) if trs else 0.0


def _pivots(bars: list[dict[str, Any]], wing: int = 2) -> tuple[list[float], list[float]]:
    highs: list[float] = []
    lows: list[float] = []
    for i in range(wing, len(bars) - wing):
        hi = float(bars[i]["high"])
        lo = float(bars[i]["low"])
        window = bars[i - wing:i + wing + 1]
        if hi >= max(float(x["high"]) for x in window):
            highs.append(hi)
        if lo <= min(float(x["low"]) for x in window):
            lows.append(lo)
    return highs, lows


def _unavailable() -> dict[str, Any]:
    return {
        "role": "OPPORTUNITY_REGIME_ANALYST",
        "question": QUESTION,
        "finding": "INSUFFICIENT_DATA",
        "state": "UNAVAILABLE",
        "architecture": ARCHITECTURE,
        "regime": "UNRESOLVED",
        "direction": "NEUTRAL",
        "phase": "UNRESOLVED",
        "opportunity": "NONE",
        "opportunity_state": "WAIT",
        "opportunity_maturity": "UNPROVEN",
        "independence": "E2_FIRST_E1_CROSS_CHECK",
        "auction_state": "UNKNOWN",
        "auction_intent": "UNKNOWN",
        "auction_intent_detail": {},
        "location_context": "UNKNOWN",
        "opposing_space_atr": 0.0,
        "regime_confidence": 0.0,
        "confidence": 0.0,
        "opportunity_score": 0.0,
        "candidate_hypotheses": [],
        "counter_evidence": [],
        "counter_evidence_severity": "HIGH",
        "missing_evidence": ["sufficient closed-candle market evidence"],
        "confirmation_required": ["sufficient closed-candle market evidence"],
        "invalidation_evidence": [],
        "why_not_trade": ["INSUFFICIENT_MARKET_DATA"],
        "conditional_map": [],
        "market_tree": {},
        "opportunity_hierarchy": {},
        "hard_veto": ["INSUFFICIENT_MARKET_DATA"],
        "requires_downstream_confirmation": True,
        "opportunity_decision": "WAIT",
        "entry": None,
        "trigger": None,
        "decision": None,
        "professional_reasoning": {
            "question": QUESTION,
            "thesis": "No thesis: insufficient data.",
            "independent_thesis": True,
            "e1_used_as": "CROSS_CHECK_ONLY",
            "entry_authorized": False,
        },
        "reasons": ["INSUFFICIENT_MARKET_DATA"],
    }


def _candidate(
    *,
    name: str,
    direction: str,
    regime: str,
    structure: bool,
    acceptance: bool,
    rejection: bool,
    pullback: bool,
    displacement: bool,
    location_ok: bool,
    space_atr: float,
    efficiency: float,
    auction_intent: str,
) -> dict[str, Any]:
    """Build evidence only. Eligibility is governed by hard conditions, not a score threshold."""
    vetoes: list[str] = []
    if not structure:
        vetoes.append("STRUCTURE_NOT_ESTABLISHED")
    if not location_ok:
        vetoes.append("LOCATION_NOT_ADVANTAGEOUS")
    if space_atr < 1.0:
        vetoes.append("INSUFFICIENT_OPPOSING_SPACE")
    if name == "BREAKOUT_CONTINUATION" and not acceptance:
        vetoes.append("ACCEPTANCE_NOT_PROVEN")
    if name == "LIQUIDITY_REVERSAL" and not rejection:
        vetoes.append("FAILED_AUCTION_NOT_PROVEN")
    if name == "TREND_PULLBACK_CONTINUATION" and not pullback:
        vetoes.append("PULLBACK_NOT_ESTABLISHED")
    if name == "TREND_PULLBACK_CONTINUATION" and not acceptance and not displacement:
        vetoes.append("CONTINUATION_EVIDENCE_NOT_ESTABLISHED")
    if auction_intent in {"UNCOMMITTED_AUCTION", "BUYER_INITIATIVE_PENDING_ACCEPTANCE", "SELLER_INITIATIVE_PENDING_ACCEPTANCE"}:
        vetoes.append("AUCTION_ACCEPTANCE_NOT_PROVEN")

    # Score is descriptive, never the authority that makes a candidate tradable.
    evidence_score = max(0.0, min(1.0, (
        0.22 * float(structure)
        + 0.22 * float(acceptance)
        + 0.18 * float(rejection)
        + 0.16 * float(pullback)
        + 0.10 * float(displacement)
        + 0.06 * float(location_ok)
        + 0.06 * min(space_atr / 3.0, 1.0)
    )))

    return {
        "name": name,
        "direction": direction,
        "regime": regime,
        "evidence_score": round(evidence_score, 3),
        "quality": round(evidence_score, 3),
        "space_atr": round(space_atr, 3),
        "structure": structure,
        "acceptance": acceptance,
        "rejection": rejection,
        "pullback": pullback,
        "displacement": displacement,
        "location_ok": location_ok,
        "auction_intent": auction_intent,
        "eligible": not vetoes,
        "vetoes": vetoes,
        "efficiency": round(efficiency, 3),
    }


def analyze_e2(snapshot: dict[str, Any]) -> dict[str, Any]:
    """E2 independently maps market opportunity, auction intent and conditional paths.

    E2 deliberately does NOT issue BUY/SELL, entry, SL/TP or final trade decisions.
    E1 is used only as a cross-check; E3-E9 are not read or modified here.
    """
    bars = _bars(snapshot)
    if len(bars) < MIN_BARS:
        return _unavailable()

    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    closes = [float(b["close"]) for b in bars]
    opens = [float(b["open"]) for b in bars]
    atr = max(_atr(bars), 1e-12)
    last = closes[-1]

    # Directional context is evidence, not a decision.
    e20 = _ema(closes, 20)
    e50 = _ema(closes, 50)
    e20_prev = _ema(closes[:-5], 20)
    e50_prev = _ema(closes[:-5], 20) if len(closes) < 50 else _ema(closes[:-5], 50)
    gap = (e20 - e50) / atr
    slope20_ema = (e20 - e20_prev) / atr
    slope50_ema = (e50 - e50_prev) / atr
    slope5 = (last - closes[-6]) / atr
    slope20 = (last - closes[-21]) / atr

    ranges = [max(float(b["high"]) - float(b["low"]), 0.0) for b in bars]
    avg20 = max(mean(ranges[-20:]), 1e-12)
    volatility_ratio = mean(ranges[-5:]) / avg20
    travel12 = max(sum(ranges[-12:]), 1e-12)
    efficiency12 = abs(last - closes[-13]) / travel12

    hi20 = max(highs[-21:-1])
    lo20 = min(lows[-21:-1])
    hi40 = max(highs[-41:-1])
    lo40 = min(lows[-41:-1])
    width40 = max(hi40 - lo40, 1e-12)
    position40 = max(0.0, min(1.0, (last - lo40) / width40))

    pivot_highs, pivot_lows = _pivots(bars)
    hh = len(pivot_highs) >= 2 and pivot_highs[-1] > pivot_highs[-2]
    lh = len(pivot_highs) >= 2 and pivot_highs[-1] < pivot_highs[-2]
    hl = len(pivot_lows) >= 2 and pivot_lows[-1] > pivot_lows[-2]
    ll = len(pivot_lows) >= 2 and pivot_lows[-1] < pivot_lows[-2]
    bullish_structure = hh and hl
    bearish_structure = lh and ll

    up_evidence = {
        "ema_gap": gap > 0.35,
        "ema20_slope": slope20_ema > 0.08,
        "ema50_slope": slope50_ema > -0.05,
        "short_pressure": slope5 > 0.20,
        "medium_pressure": slope20 > 0.45,
        "structure": bullish_structure,
        "efficiency": efficiency12 >= 0.30,
    }
    down_evidence = {
        "ema_gap": gap < -0.35,
        "ema20_slope": slope20_ema < -0.08,
        "ema50_slope": slope50_ema < 0.05,
        "short_pressure": slope5 < -0.20,
        "medium_pressure": slope20 < -0.45,
        "structure": bearish_structure,
        "efficiency": efficiency12 >= 0.30,
    }
    up = sum(up_evidence.values())
    down = sum(down_evidence.values())

    # Closed-candle auction evidence.
    span = max(highs[-1] - lows[-1], 1e-12)
    body = abs(last - opens[-1]) / span
    close_position = (last - lows[-1]) / span
    upper_wick = (highs[-1] - max(opens[-1], last)) / span
    lower_wick = (min(opens[-1], last) - lows[-1]) / span

    broke_up = last > hi20
    broke_down = last < lo20
    sweep_high = highs[-1] > hi20 and last <= hi20
    sweep_low = lows[-1] < lo20 and last >= lo20
    acceptance_up = broke_up and close_position >= 0.65 and body >= 0.45
    acceptance_down = broke_down and close_position <= 0.35 and body >= 0.45
    rejection_high = sweep_high and close_position <= 0.45 and upper_wick >= 0.20
    rejection_low = sweep_low and close_position >= 0.55 and lower_wick >= 0.20
    displacement_up = body >= 0.60 and close_position >= 0.75 and span >= 1.25 * avg20
    displacement_down = body >= 0.60 and close_position <= 0.25 and span >= 1.25 * avg20

    recent_moves = [closes[-i] - closes[-i - 1] for i in range(1, 4)]
    follow_up = sum(x > 0 for x in recent_moves)
    follow_down = sum(x < 0 for x in recent_moves)
    net5 = (last - closes[-5]) / atr

    balanced = (
        abs(slope20) < 0.65
        and efficiency12 < 0.30
        and width40 / atr < 8.5
    )

    if acceptance_up and follow_up >= 2:
        auction_intent = "BUY_SIDE_ACCEPTANCE"
        auction_phase = "ACCEPTANCE"
        intent_strength = "HIGH"
        intent_reason = "buyers broke the prior boundary, closed beyond it, and follow-through agrees"
    elif acceptance_down and follow_down >= 2:
        auction_intent = "SELL_SIDE_ACCEPTANCE"
        auction_phase = "ACCEPTANCE"
        intent_strength = "HIGH"
        intent_reason = "sellers broke the prior boundary, closed beyond it, and follow-through agrees"
    elif rejection_high:
        auction_intent = "FAILED_HIGH_AUCTION"
        auction_phase = "REJECTION"
        intent_strength = "MODERATE"
        intent_reason = "price explored above the prior high but the closed candle returned inside"
    elif rejection_low:
        auction_intent = "FAILED_LOW_AUCTION"
        auction_phase = "REJECTION"
        intent_strength = "MODERATE"
        intent_reason = "price explored below the prior low but the closed candle returned inside"
    elif down >= 5 and net5 < -0.50:
        auction_intent = "SELLER_INITIATIVE_PENDING_ACCEPTANCE"
        auction_phase = "INITIATIVE"
        intent_strength = "MODERATE"
        intent_reason = "sellers show initiative, but the auction has not yet proved acceptance"
    elif up >= 5 and net5 > 0.50:
        auction_intent = "BUYER_INITIATIVE_PENDING_ACCEPTANCE"
        auction_phase = "INITIATIVE"
        intent_strength = "MODERATE"
        intent_reason = "buyers show initiative, but the auction has not yet proved acceptance"
    elif balanced:
        auction_intent = "TWO_SIDED_BALANCE"
        auction_phase = "BALANCE"
        intent_strength = "LOW"
        intent_reason = "price is rotational and directionally inefficient"
    else:
        auction_intent = "UNCOMMITTED_AUCTION"
        auction_phase = "UNRESOLVED"
        intent_strength = "LOW"
        intent_reason = "neither side has demonstrated sufficient acceptance"

    # Location is a context, not a reversal signal. Cheap price alone never creates a long thesis.
    long_location_ok = 0.10 <= position40 <= 0.75
    short_location_ok = 0.25 <= position40 <= 0.90
    long_extended = position40 >= 0.92
    short_extended = position40 <= 0.08

    long_space = max((hi40 - last) / atr, 0.0)
    short_space = max((last - lo40) / atr, 0.0)

    candidates: list[dict[str, Any]] = []

    # Pullback is explicit: directional impulse followed by a retracement that remains inside the thesis.
    prior_up = closes[-6] > closes[-11] if len(closes) >= 11 else False
    prior_down = closes[-6] < closes[-11] if len(closes) >= 11 else False
    retrace_up = last < max(closes[-2], closes[-3]) and last > min(closes[-6:-1])
    retrace_down = last > min(closes[-2], closes[-3]) and last < max(closes[-6:-1])
    pullback_up = bullish_structure and prior_up and retrace_up and not rejection_high
    pullback_down = bearish_structure and prior_down and retrace_down and not rejection_low

    if up >= 4:
        candidates.append(_candidate(
            name="TREND_PULLBACK_CONTINUATION", direction="UP", regime="TREND",
            structure=bullish_structure, acceptance=acceptance_up,
            rejection=rejection_high, pullback=pullback_up,
            displacement=displacement_up, location_ok=long_location_ok,
            space_atr=long_space, efficiency=efficiency12,
            auction_intent=auction_intent,
        ))
    if down >= 4:
        candidates.append(_candidate(
            name="TREND_PULLBACK_CONTINUATION", direction="DOWN", regime="TREND",
            structure=bearish_structure, acceptance=acceptance_down,
            rejection=rejection_low, pullback=pullback_down,
            displacement=displacement_down, location_ok=short_location_ok,
            space_atr=short_space, efficiency=efficiency12,
            auction_intent=auction_intent,
        ))

    if acceptance_up:
        candidates.append(_candidate(
            name="BREAKOUT_CONTINUATION", direction="UP", regime="BREAKOUT",
            structure=bullish_structure, acceptance=True, rejection=rejection_high,
            pullback=False, displacement=displacement_up, location_ok=long_location_ok,
            space_atr=long_space, efficiency=efficiency12,
            auction_intent=auction_intent,
        ))
    if acceptance_down:
        candidates.append(_candidate(
            name="BREAKOUT_CONTINUATION", direction="DOWN", regime="BREAKOUT",
            structure=bearish_structure, acceptance=True, rejection=rejection_high,
            pullback=False, displacement=displacement_down, location_ok=short_location_ok,
            space_atr=short_space, efficiency=efficiency12,
            auction_intent=auction_intent,
        ))

    if rejection_low and position40 <= 0.30:
        candidates.append(_candidate(
            name="LIQUIDITY_REVERSAL", direction="UP", regime="MEAN_REVERSION",
            structure=bullish_structure, acceptance=False, rejection=True,
            pullback=False, displacement=displacement_up, location_ok=long_location_ok,
            space_atr=long_space, efficiency=efficiency12,
            auction_intent=auction_intent,
        ))
    if rejection_high and position40 >= 0.70:
        candidates.append(_candidate(
            name="LIQUIDITY_REVERSAL", direction="DOWN", regime="MEAN_REVERSION",
            structure=bearish_structure, acceptance=False, rejection=True,
            pullback=False, displacement=displacement_down, location_ok=short_location_ok,
            space_atr=short_space, efficiency=efficiency12,
            auction_intent=auction_intent,
        ))

    if balanced:
        range_direction = "UP" if position40 < 0.50 else "DOWN"
        candidates.append(_candidate(
            name="RANGE_ROTATION", direction=range_direction, regime="RANGE",
            structure=True, acceptance=False, rejection=(rejection_low or rejection_high),
            pullback=False, displacement=False,
            location_ok=(position40 <= 0.35 if range_direction == "UP" else position40 >= 0.65),
            space_atr=(long_space if range_direction == "UP" else short_space),
            efficiency=efficiency12, auction_intent=auction_intent,
        ))

    # Hard evidence gates happen before ranking. A candidate cannot become valid because its score is high.
    accepted_auction = auction_intent in {"BUY_SIDE_ACCEPTANCE", "SELL_SIDE_ACCEPTANCE"}
    eligible = [c for c in candidates if c["eligible"]]
    eligible.sort(key=lambda c: (c["evidence_score"], c["space_atr"]), reverse=True)

    # Directional hypotheses can coexist while evidence develops; they are not silently collapsed into one trade.
    directional = [c for c in eligible if c["direction"] in {"UP", "DOWN"}]
    best = eligible[0] if eligible else None
    second = eligible[1] if len(eligible) > 1 else None
    competing = bool(
        best and second
        and best["direction"] != second["direction"]
        and abs(best["evidence_score"] - second["evidence_score"]) < 0.12
    )

    if competing:
        direction = "NEUTRAL"
        regime = "TRANSITION"
        primary = "WAIT_FOR_REPRICING"
    elif best:
        direction = best["direction"]
        regime = best["regime"]
        primary = best["name"]
    else:
        direction = "NEUTRAL"
        regime = "RANGE" if balanced else "TRANSITION"
        primary = "WAIT_FOR_RANGE_EDGE" if balanced else "WAIT_FOR_REPRICING"

    # Thesis maturity is evidence-driven and monotonic. Acceptance is necessary for CONFIRMED directional continuation.
    if not best or competing:
        maturity = "EMERGING" if directional else "UNPROVEN"
    elif best["name"] == "RANGE_ROTATION":
        maturity = "DEVELOPING" if best["rejection"] and best["location_ok"] else "EMERGING"
    elif best["name"] == "LIQUIDITY_REVERSAL":
        maturity = "CONFIRMED" if best["rejection"] and best["displacement"] else "DEVELOPING"
    elif accepted_auction and best["acceptance"]:
        maturity = "CONFIRMED"
    elif best["pullback"] or best["displacement"]:
        maturity = "DEVELOPING"
    else:
        maturity = "EMERGING"

    # ACTIONABLE is intentionally impossible for E2: downstream confirmation belongs to later engines.
    if maturity == "ACTIONABLE":
        maturity = "CONFIRMED"

    hard_veto: list[str] = []
    if not candidates:
        hard_veto.append("NO_OPPORTUNITY_PATTERN_ESTABLISHED")
    if not eligible:
        hard_veto.append("NO_ELIGIBLE_OPPORTUNITY")
    if competing:
        hard_veto.append("COMPETING_HYPOTHESES")
    if not accepted_auction:
        hard_veto.append("AUCTION_ACCEPTANCE_NOT_PROVEN")
    if direction == "DOWN" and short_extended and short_space < 0.5:
        hard_veto.append("SHORT_CHASE_AT_DISCOUNT_WITH_NO_SPACE")
    if direction == "UP" and long_extended and long_space < 0.5:
        hard_veto.append("LONG_CHASE_AT_PREMIUM_WITH_NO_SPACE")

    # The most important professional rule: a discount/premium is location information, never a standalone directional thesis.
    location_warning: list[str] = []
    if position40 <= 0.20:
        location_context = "DISCOUNT_EDGE"
        location_warning.append("LOW_LOCATION_DOES_NOT_BY_ITSELF_AUTHORIZE_LONG")
    elif position40 >= 0.80:
        location_context = "PREMIUM_EDGE"
        location_warning.append("HIGH_LOCATION_DOES_NOT_BY_ITSELF_AUTHORIZE_SHORT")
    else:
        location_context = "MID_RANGE"

    # E1 is explicitly retained as a cross-check, never as the source of E2's thesis.
    counter_evidence: list[str] = []
    e1 = snapshot.get("E1_result") or {}
    e1_finding = str(e1.get("finding", "")).upper()
    if direction != "NEUTRAL" and e1_finding:
        expected = "UP" if direction == "UP" else "DOWN"
        if expected not in e1_finding and "TRANSITION" not in e1_finding:
            counter_evidence.append("E1_DIRECTIONAL_VIEW_CONFLICT_RETAINED_AS_COUNTER_EVIDENCE")
    if direction == "UP" and rejection_high:
        counter_evidence.append("FAILED_HIGH_AUCTION_AGAINST_LONG_THESIS")
    if direction == "DOWN" and rejection_low:
        counter_evidence.append("FAILED_LOW_AUCTION_AGAINST_SHORT_THESIS")
    if direction != "NEUTRAL" and efficiency12 < 0.15:
        counter_evidence.append("LOW_AUCTION_EFFICIENCY_REDUCES_DIRECTIONAL_CONVICTION")
    if direction == "UP" and short_space < 0.5:
        counter_evidence.append("DOWNWARD_SPACE_IS_CONSTRAINED")
    if direction == "DOWN" and long_space < 0.5:
        counter_evidence.append("UPWARD_SPACE_IS_CONSTRAINED")

    # What must happen next is explicit. This is the bridge from analysis to later confirmation engines.
    if direction == "UP":
        confirmation_required = [
            "buyers defend the thesis area",
            "closed-candle acceptance or continuation appears",
            "follow-through preserves adequate opposing space",
        ]
        invalidation = [
            "acceptance fails and price is rejected back through the thesis area",
            "opposing structure wins",
            "upward opposing space disappears",
        ]
        strengthen = "IF buyers defend the area and regain acceptance -> bullish opportunity strengthens"
        weaken = "IF acceptance fails or sellers regain control -> bullish thesis weakens/invalidates"
    elif direction == "DOWN":
        confirmation_required = [
            "sellers defend the thesis area",
            "closed-candle acceptance or continuation appears",
            "follow-through preserves adequate opposing space",
        ]
        invalidation = [
            "acceptance fails and price is reclaimed through the thesis area",
            "opposing structure wins",
            "downward opposing space disappears",
        ]
        strengthen = "IF sellers defend the area and regain acceptance -> bearish opportunity strengthens"
        weaken = "IF acceptance fails or buyers regain control -> bearish thesis weakens/invalidates"
    elif balanced:
        confirmation_required = [
            "range edge rejection with follow-through",
            "or range break followed by closed-candle acceptance",
        ]
        invalidation = [
            "range breaks without acceptance",
            "price reaches the middle without edge evidence",
        ]
        strengthen = "IF an edge rejects -> range rotation strengthens; if a break accepts -> repricing becomes primary"
        weaken = "IF neither edge nor accepted break develops -> remain neutral"
    else:
        confirmation_required = [
            "directional evidence converges",
            "closed-candle acceptance/follow-through proves the auction",
        ]
        invalidation = [
            "counter-evidence dominates",
            "opposing space becomes insufficient",
        ]
        strengthen = "IF directional evidence converges and the auction accepts -> promote the corresponding opportunity"
        weaken = "IF evidence remains mixed -> preserve capital and wait for repricing"

    conditional_map = [
        strengthen,
        weaken,
        "IF range edge rejects -> RANGE_ROTATION develops",
        "IF range break + closed-candle acceptance -> BREAKOUT_REPRICING develops",
        "IF failed auction + opposite-side follow-through -> LIQUIDITY_REVERSAL strengthens",
        "IF opposing space collapses -> veto the opportunity regardless of directional evidence",
    ]

    primary_candidate = best or {}
    secondary_candidates = [c for c in candidates if c is not best]
    secondary_candidates.sort(key=lambda c: c["evidence_score"], reverse=True)

    hierarchy = {
        "primary": primary,
        "primary_direction": direction,
        "primary_maturity": maturity,
        "secondary": secondary_candidates[0]["name"] if secondary_candidates else "NONE",
        "alternative": "LIQUIDITY_REVERSAL" if rejection_high or rejection_low else "RANGE_ROTATION",
        "ranking_rule": [
            "hard evidence gates before score",
            "accepted auction > developing directional opportunity > range rotation > no-trade",
            "failed auction requires opposite-side follow-through before promotion",
            "location never overrides auction or structure",
        ],
        "invalidation": invalidation,
        "no_trade_when": hard_veto or ["downstream confirmation is absent"],
    }

    if hard_veto:
        opportunity_state = "WAIT"
    elif maturity in {"CONFIRMED"}:
        opportunity_state = "CONFIRMED_FOR_DOWNSTREAM_REVIEW"
    else:
        opportunity_state = "DEVELOPING"

    # E2 can report confidence, but confidence never authorizes a trade.
    confidence = primary_candidate.get("evidence_score", 0.0) if primary_candidate else 0.0
    finding = (
        f"Independent E2 thesis: {regime}/{direction} -> {primary}; "
        f"auction={auction_intent}; maturity={maturity}; "
        f"thesis remains {'blocked' if hard_veto else 'open for downstream review'}"
    )

    return {
        "role": "OPPORTUNITY_REGIME_ANALYST",
        "question": QUESTION,
        "finding": finding,
        "state": "ANALYSIS_COMPLETE",
        "architecture": ARCHITECTURE,
        "regime": regime,
        "direction": direction,
        "phase": auction_phase,
        "opportunity": primary,
        "opportunity_state": opportunity_state,
        "opportunity_maturity": maturity,
        "independence": "E2_FIRST_E1_CROSS_CHECK",
        "auction_state": "ACCEPTED" if accepted_auction else "FAILED" if auction_phase == "REJECTION" else "UNRESOLVED",
        "auction_intent": auction_intent,
        "auction_intent_detail": {
            "phase": auction_phase,
            "strength": intent_strength,
            "why": intent_reason,
            "buyer_evidence": up,
            "seller_evidence": down,
            "follow_through_up": follow_up,
            "follow_through_down": follow_down,
            "acceptance_proven": accepted_auction,
            "volatility_ratio": round(volatility_ratio, 3),
        },
        "location_context": location_context,
        "location_warnings": location_warning,
        "opposing_space_atr": round(
            long_space if direction == "UP" else short_space if direction == "DOWN" else max(long_space, short_space), 3
        ),
        "regime_confidence": round(max(up, down) / 7.0, 3),
        "confidence": round(confidence, 3),
        "opportunity_score": round(confidence, 3),
        "candidate_hypotheses": candidates,
        "counter_evidence": counter_evidence,
        "counter_evidence_severity": "HIGH" if hard_veto else "MODERATE" if counter_evidence else "LOW",
        "missing_evidence": confirmation_required,
        "confirmation_required": confirmation_required,
        "invalidation_evidence": invalidation,
        "why_not_trade": hierarchy["no_trade_when"],
        "conditional_map": conditional_map,
        "market_tree": {
            "root": "OBSERVE_AUCTION",
            "branches": [
                {"if": "closed_candle_acceptance", "then": "promote_directional_opportunity_for_downstream_review"},
                {"if": "range_edge_rejection", "then": "promote_range_rotation"},
                {"if": "range_break_and_acceptance", "then": "promote_breakout_repricing"},
                {"if": "failed_auction_and_opposite_follow_through", "then": "promote_liquidity_reversal"},
                {"if": "counter_evidence_dominates", "then": "remain_neutral"},
                {"if": "opposing_space_insufficient", "then": "hard_veto"},
            ],
        },
        "opportunity_hierarchy": hierarchy,
        "hard_veto": hard_veto,
        "requires_downstream_confirmation": True,
        "opportunity_decision": "WAIT",
        "entry": None,
        "trigger": None,
        "decision": None,
        "professional_reasoning": {
            "question": QUESTION,
            "thesis": finding,
            "why_now": f"Auction intent={auction_intent}; primary opportunity={primary}.",
            "what_market_is_trying_to_do": intent_reason,
            "expected_path": conditional_map,
            "required_evidence": confirmation_required,
            "counter_case": counter_evidence or ["No dominant counter-evidence detected"],
            "invalidation_conditions": invalidation,
            "timing": "WAIT",
            "independent_thesis": True,
            "e1_used_as": "CROSS_CHECK_ONLY",
            "entry_authorized": False,
        },
        "reasons": (["HARD_VETO_PRESENT"] if hard_veto else [])
        + (["COUNTER_EVIDENCE_PRESENT"] if counter_evidence else [])
        + ["EVIDENCE_HIERARCHY", "AUCTION_INTENT_DEPTH", "OPPORTUNITY_MATURITY", "CONDITIONAL_OPPORTUNITY_MAP"],
    }
