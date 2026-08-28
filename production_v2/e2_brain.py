from __future__ import annotations

from statistics import mean
from typing import Any

QUESTION = "What opportunity is the market offering right now?"
MIN_BARS = 80
ARCHITECTURE = "E2_PROFESSIONAL_OPPORTUNITY_CORE_V5"


def _bars(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    bars = snapshot.get("bars") or []
    return [b for b in bars if isinstance(b, dict) and all(k in b for k in ("open", "high", "low", "close"))]


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    a = 2.0 / (period + 1.0)
    value = values[0]
    for x in values[1:]:
        value = a * x + (1.0 - a) * value
    return value


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs: list[float] = []
    prev = float(bars[0]["close"])
    for b in bars[-period:]:
        h, l = float(b["high"]), float(b["low"])
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
        "regime": "UNRESOLVED",
        "direction": "NEUTRAL",
        "opportunity": "NONE",
        "opportunity_state": "WAIT",
        "opportunity_maturity": "UNPROVEN",
        "independence": "E2_FIRST_E1_CROSS_CHECK",
        "auction_intent": "UNKNOWN",
        "auction_intent_detail": {},
        "conditional_map": [],
        "market_tree": {},
        "opportunity_hierarchy": {},
        "hard_veto": ["INSUFFICIENT_MARKET_DATA"],
        "requires_downstream_confirmation": True,
        "entry": None,
        "decision": None,
        "reasons": ["INSUFFICIENT_MARKET_DATA"],
    }


def analyze_e2(snapshot: dict[str, Any]) -> dict[str, Any]:
    """E2 independently maps opportunity, intent and conditional paths; never issues entry/final trade decisions."""
    bars = _bars(snapshot)
    if len(bars) < MIN_BARS:
        return _unavailable()

    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    closes = [float(b["close"]) for b in bars]
    opens = [float(b["open"]) for b in bars]
    atr = max(_atr(bars), 1e-12)
    last = closes[-1]

    e20 = _ema(closes, 20)
    e50 = _ema(closes, 50)
    e20_prev = _ema(closes[:-5], 20)
    e50_prev = _ema(closes[:-5], 50)
    gap = (e20 - e50) / atr
    slope20_ema = (e20 - e20_prev) / atr
    slope50_ema = (e50 - e50_prev) / atr
    slope5 = (last - closes[-6]) / atr
    slope20 = (last - closes[-21]) / atr

    ranges = [max(float(b["high"]) - float(b["low"]), 0.0) for b in bars]
    avg20 = max(mean(ranges[-20:]), 1e-12)
    volatility_ratio = mean(ranges[-5:]) / avg20
    travel = max(sum(ranges[-12:]), 1e-12)
    efficiency12 = abs(last - closes[-13]) / travel

    hi20, lo20 = max(highs[-21:-1]), min(lows[-21:-1])
    hi40, lo40 = max(highs[-41:-1]), min(lows[-41:-1])
    width = max(hi40 - lo40, 1e-12)
    position40 = max(0.0, min(1.0, (last - lo40) / width))

    pivot_highs, pivot_lows = _pivots(bars)
    hh = len(pivot_highs) >= 2 and pivot_highs[-1] > pivot_highs[-2]
    lh = len(pivot_highs) >= 2 and pivot_highs[-1] < pivot_highs[-2]
    hl = len(pivot_lows) >= 2 and pivot_lows[-1] > pivot_lows[-2]
    ll = len(pivot_lows) >= 2 and pivot_lows[-1] < pivot_lows[-2]
    bullish_structure = hh and hl
    bearish_structure = lh and ll

    up = sum((gap > .35, slope20_ema > .08, slope50_ema > -.05, slope5 > .20,
              slope20 > .45, bullish_structure, efficiency12 >= .30))
    down = sum((gap < -.35, slope20_ema < -.08, slope50_ema < .05, slope5 < -.20,
                slope20 < -.45, bearish_structure, efficiency12 >= .30))

    span = max(highs[-1] - lows[-1], 1e-12)
    body = abs(last - opens[-1]) / span
    close_position = (last - lows[-1]) / span
    upper_wick = (highs[-1] - max(opens[-1], last)) / span
    lower_wick = (min(opens[-1], last) - lows[-1]) / span

    broke_up = last > hi20
    broke_down = last < lo20
    sweep_high = highs[-1] > hi20 and last <= hi20
    sweep_low = lows[-1] < lo20 and last >= lo20
    acceptance_up = broke_up and close_position >= .65 and body >= .45
    acceptance_down = broke_down and close_position <= .35 and body >= .45
    rejection_high = sweep_high and close_position <= .45 and upper_wick >= .20
    rejection_low = sweep_low and close_position >= .55 and lower_wick >= .20
    displacement_up = body >= .60 and close_position >= .75 and span >= 1.25 * avg20
    displacement_down = body >= .60 and close_position <= .25 and span >= 1.25 * avg20
    balanced = abs(slope20) < .65 and efficiency12 < .30 and width / atr < 8.5

    recent = [closes[-i] - closes[-i - 1] for i in range(1, 4)]
    follow_up = sum(x > 0 for x in recent)
    follow_down = sum(x < 0 for x in recent)
    net5 = (last - closes[-5]) / atr

    # Deep auction intent: distinguish initiative, acceptance, failed auction and unresolved balance.
    if acceptance_up and follow_up >= 2:
        auction_intent = "BUY_SIDE_ACCEPTANCE"
        auction_phase = "ACCEPTANCE"
        intent_strength = "HIGH"
        intent_reason = "breakout closed outside prior value/range and follow-through agrees"
    elif acceptance_down and follow_down >= 2:
        auction_intent = "SELL_SIDE_ACCEPTANCE"
        auction_phase = "ACCEPTANCE"
        intent_strength = "HIGH"
        intent_reason = "breakdown closed outside prior value/range and follow-through agrees"
    elif rejection_high:
        auction_intent = "FAILED_HIGH_AUCTION"
        auction_phase = "REJECTION"
        intent_strength = "MODERATE"
        intent_reason = "price explored above prior high but returned inside"
    elif rejection_low:
        auction_intent = "FAILED_LOW_AUCTION"
        auction_phase = "REJECTION"
        intent_strength = "MODERATE"
        intent_reason = "price explored below prior low but returned inside"
    elif up >= 5 and net5 > .50:
        auction_intent = "BUYER_INITIATIVE_PENDING_ACCEPTANCE"
        auction_phase = "INITIATIVE"
        intent_strength = "MODERATE"
        intent_reason = "buyers show directional initiative but acceptance is not proven"
    elif down >= 5 and net5 < -.50:
        auction_intent = "SELLER_INITIATIVE_PENDING_ACCEPTANCE"
        auction_phase = "INITIATIVE"
        intent_strength = "MODERATE"
        intent_reason = "sellers show directional initiative but acceptance is not proven"
    elif balanced:
        auction_intent = "TWO_SIDED_BALANCE"
        auction_phase = "BALANCE"
        intent_strength = "LOW"
        intent_reason = "auction remains rotational and directionally inefficient"
    else:
        auction_intent = "UNCOMMITTED_AUCTION"
        auction_phase = "UNRESOLVED"
        intent_strength = "LOW"
        intent_reason = "neither side has demonstrated sufficient acceptance"

    def opportunity(name: str, direction: str, regime: str, structure: bool,
                    acceptance: bool = False, rejection: bool = False,
                    pullback: bool = False, displacement: bool = False) -> dict[str, Any]:
        space = max((hi40 - last) / atr, 0.0) if direction == "UP" else max((last - lo40) / atr, 0.0)
        favorable_location = .10 <= position40 <= .75 if direction == "UP" else .25 <= position40 <= .90
        extended = position40 >= .92 if direction == "UP" else position40 <= .08
        vetoes: list[str] = []
        if not favorable_location:
            vetoes.append("LOCATION_NOT_ADVANTAGEOUS")
        if space < 1.0:
            vetoes.append("INSUFFICIENT_OPPOSING_SPACE")
        if extended:
            vetoes.append("OVEREXTENDED_LOCATION")
        if name == "BREAKOUT_CONTINUATION" and not acceptance:
            vetoes.append("NO_ACCEPTANCE")
        if rejection and ((direction == "UP" and position40 >= .70) or (direction == "DOWN" and position40 <= .30)):
            vetoes.append("FAILED_AUCTION_CONFLICT")
        quality = max(0.0, min(1.0,
            .20 * float(structure) + .18 * float(acceptance or displacement) +
            .16 * float(pullback) + .14 * float(favorable_location) +
            .16 * min(space / 3.0, 1.0) + .16 * min(efficiency12 / .55, 1.0) -
            .18 * float(rejection) - .18 * float(extended)))
        return {
            "name": name, "direction": direction, "regime": regime,
            "quality": quality, "space_atr": space, "vetoes": vetoes,
            "eligible": not vetoes, "structure": structure,
            "acceptance": acceptance, "pullback": pullback,
            "rejection": rejection, "displacement": displacement,
        }

    candidates: list[dict[str, Any]] = []
    if up >= 4:
        candidates.append(opportunity("TREND_PULLBACK_CONTINUATION", "UP", "TREND", bullish_structure,
                                      rejection=rejection_high, displacement=displacement_up))
    if down >= 4:
        candidates.append(opportunity("TREND_PULLBACK_CONTINUATION", "DOWN", "TREND", bearish_structure,
                                      rejection=rejection_low, displacement=displacement_down))
    if acceptance_up:
        candidates.append(opportunity("BREAKOUT_CONTINUATION", "UP", "BREAKOUT", bullish_structure, True,
                                      rejection_high, displacement=displacement_up))
    if acceptance_down:
        candidates.append(opportunity("BREAKOUT_CONTINUATION", "DOWN", "BREAKOUT", bearish_structure, True,
                                      rejection_high, displacement=displacement_down))
    if rejection_low and position40 <= .30:
        candidates.append(opportunity("LIQUIDITY_REVERSAL", "UP", "MEAN_REVERSION", bullish_structure,
                                      rejection=True, displacement=displacement_up))
    if rejection_high and position40 >= .70:
        candidates.append(opportunity("LIQUIDITY_REVERSAL", "DOWN", "MEAN_REVERSION", bearish_structure,
                                      rejection=True, displacement=displacement_down))
    if balanced:
        candidates.append(opportunity("RANGE_ROTATION", "UP" if position40 < .5 else "DOWN", "RANGE", True))

    eligible = sorted((x for x in candidates if x["eligible"]),
                      key=lambda x: (x["quality"], x["space_atr"]), reverse=True)
    best = eligible[0] if eligible else None
    second = eligible[1] if len(eligible) > 1 else None
    competing = bool(best and second and best["direction"] != second["direction"] and
                      abs(best["quality"] - second["quality"]) < .12)

    direction = best["direction"] if best and not competing else "NEUTRAL"
    regime = best["regime"] if best and not competing else ("RANGE" if balanced else "TRANSITION")
    primary = best["name"] if best and not competing else ("WAIT_FOR_RANGE_EDGE" if regime == "RANGE" else "WAIT_FOR_REPRICING")

    if best and not competing:
        phase = "ACCEPTANCE" if best["acceptance"] else "REJECTION" if best["rejection"] else "DEVELOPING"
    else:
        phase = "BALANCED" if balanced else "UNRESOLVED"

    opposing_space = (
        max((hi40 - last) / atr, 0.0) if direction == "UP" else
        max((last - lo40) / atr, 0.0) if direction == "DOWN" else 0.0
    )

    hard_veto: list[str] = []
    if competing:
        hard_veto.append("COMPETING_HYPOTHESES")
    if best is None:
        hard_veto.append("NO_ELIGIBLE_OPPORTUNITY")
    if direction == "DOWN" and position40 <= .12 and opposing_space < .5:
        hard_veto.append("SHORT_CHASE_AT_DISCOUNT_WITH_NO_SPACE")
    if direction == "UP" and position40 >= .88 and opposing_space < .5:
        hard_veto.append("LONG_CHASE_AT_PREMIUM_WITH_NO_SPACE")
    if auction_intent in {"UNCOMMITTED_AUCTION", "BUYER_INITIATIVE_PENDING_ACCEPTANCE", "SELLER_INITIATIVE_PENDING_ACCEPTANCE"}:
        hard_veto.append("AUCTION_ACCEPTANCE_NOT_PROVEN")

    # Professional discretionary reasoning: explain what matters, what does not, and what changes the thesis.
    counter_evidence: list[str] = []
    e1 = snapshot.get("E1_result") or {}
    e1_finding = str(e1.get("finding", "")).upper()
    if e1_finding and direction != "NEUTRAL" and direction not in e1_finding and "TRANSITION" not in e1_finding:
        counter_evidence.append("E1_DIRECTIONAL_VIEW_CONFLICT_RETAINED_AS_COUNTER_EVIDENCE")
    if rejection_high and direction == "UP":
        counter_evidence.append("FAILED_HIGH_AUCTION_AGAINST_LONG_THESIS")
    if rejection_low and direction == "DOWN":
        counter_evidence.append("FAILED_LOW_AUCTION_AGAINST_SHORT_THESIS")
    if efficiency12 < .15 and direction != "NEUTRAL":
        counter_evidence.append("LOW_AUCTION_EFFICIENCY_REDUCES_DIRECTIONAL_CONVICTION")

    # Market tree: mutually explicit branches rather than a single prediction.
    if direction == "UP":
        strengthen = "IF pullback holds and buyers regain acceptance -> bullish continuation strengthens"
        invalidate = "IF opposing structure wins or acceptance fails -> bullish thesis invalidates"
    elif direction == "DOWN":
        strengthen = "IF pullback holds and sellers regain acceptance -> bearish continuation strengthens"
        invalidate = "IF opposing structure wins or acceptance fails -> bearish thesis invalidates"
    else:
        strengthen = "IF directional evidence converges and auction accepts -> a directional thesis becomes actionable for downstream engines"
        invalidate = "IF counter-evidence dominates -> remain neutral and preserve capital"

    conditional_map = [
        strengthen,
        invalidate,
        "IF range edge rejects -> range rotation develops",
        "IF range break + acceptance -> breakout repricing develops",
        "IF failed auction receives opposite-side follow-through -> liquidity reversal strengthens",
        "IF opposing space collapses -> opportunity is vetoed regardless of directional evidence",
    ]

    hierarchy = {
        "primary": primary,
        "secondary": "LIQUIDITY_REVERSAL" if "FAILED" in auction_intent else "BREAKOUT_REPRICING",
        "alternative": "RANGE_ROTATION",
        "conditional_priority": [
            "accepted auction > developing directional opportunity > range rotation > no-trade",
            "reversal requires failed auction plus opposite-side follow-through",
            "breakout requires acceptance, not merely a wick through the boundary",
        ],
        "invalidation": "opposing structure wins, auction acceptance fails, or opposing space disappears",
        "no_trade_when": hard_veto or ["downstream confirmation is absent"],
    }

    opportunity_maturity = "CONDITIONAL" if best and not hard_veto else "UNPROVEN"
    finding = (
        f"Independent E2 thesis: {regime}/{direction} creates {primary} at {phase}; "
        f"auction intent={auction_intent}; thesis is conditional and requires downstream confirmation."
    )

    return {
        "role": "OPPORTUNITY_REGIME_ANALYST",
        "question": QUESTION,
        "finding": finding,
        "state": "ANALYSIS_COMPLETE",
        "architecture": ARCHITECTURE,
        "regime": regime,
        "direction": direction,
        "phase": phase,
        "opportunity": primary,
        "opportunity_state": "WAIT" if hard_veto else "DEVELOPING",
        "opportunity_maturity": opportunity_maturity,
        "independence": "E2_FIRST_E1_CROSS_CHECK",
        "auction_state": "ACCEPTED" if auction_phase == "ACCEPTANCE" else "FAILED" if auction_phase == "REJECTION" else "UNRESOLVED",
        "auction_intent": auction_intent,
        "auction_intent_detail": {
            "phase": auction_phase,
            "strength": intent_strength,
            "why": intent_reason,
            "buyer_evidence": up,
            "seller_evidence": down,
            "follow_through_up": follow_up,
            "follow_through_down": follow_down,
            "acceptance_proven": acceptance_up or acceptance_down,
        },
        "location_context": "EDGE_LOW" if position40 <= .20 else "EDGE_HIGH" if position40 >= .80 else "MID_RANGE",
        "opposing_space_atr": round(opposing_space, 3),
        "regime_confidence": round(max(up, down) / 7.0, 3),
        "confidence": round(best["quality"], 3) if best else 0.0,
        "opportunity_score": round(best["quality"], 3) if best else 0.0,
        "counter_evidence": counter_evidence,
        "counter_evidence_severity": "HIGH" if hard_veto else "MODERATE" if counter_evidence else "LOW",
        "missing_evidence": ["closed-candle acceptance/follow-through"],
        "invalidation_evidence": [
            "opposing structure wins",
            "auction thesis fails to receive follow-through",
            "opposing space disappears",
        ],
        "why_not_trade": hierarchy["no_trade_when"],
        "conditional_map": conditional_map,
        "market_tree": {
            "root": "OBSERVE_AUCTION",
            "branches": [
                {"if": "acceptance_proven", "then": "promote_directional_opportunity"},
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
            "required_evidence": [
                "acceptance or rejection follow-through",
                "opposing space remains adequate",
                "thesis remains structurally valid",
            ],
            "counter_case": counter_evidence or ["No dominant counter-evidence detected"],
            "invalidation_conditions": hierarchy["invalidation"],
            "timing": "WAIT",
            "independent_thesis": True,
            "e1_used_as": "CROSS_CHECK_ONLY",
            "entry_authorized": False,
        },
        "reasons": (["HARD_VETO_PRESENT"] if hard_veto else []) +
                   (["COUNTER_EVIDENCE_PRESENT"] if counter_evidence else []) +
                   ["CONDITIONAL_OPPORTUNITY_MAP", "OPPORTUNITY_HIERARCHY", "AUCTION_INTENT_DEPTH"],
    }
