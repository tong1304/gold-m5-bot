from __future__ import annotations

from statistics import mean
from typing import Any

QUESTION = "What opportunity is the market offering right now?"
MIN_BARS = 80
ARCHITECTURE = "E2_PROFESSIONAL_OPPORTUNITY_CORE_V6"


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
    for value_i in values[1:]:
        value = alpha * value_i + (1.0 - alpha) * value
    return value


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs: list[float] = []
    prev = float(bars[-period - 1]["close"]) if len(bars) > period else float(bars[0]["close"])
    for b in bars[-period:]:
        h, l = float(b["high"]), float(b["low"])
        trs.append(max(h - l, abs(h - prev), abs(l - prev)))
        prev = float(b["close"])
    return mean(trs) if trs else 0.0


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
        "independence": "E2_INDEPENDENT_E1_CROSS_CHECK",
        "reasoning_mode": "PROFESSIONAL_DISCRETIONARY",
        "trade_decision_authority": "NONE",
        "auction_intent": "UNKNOWN",
        "auction_intent_detail": {},
        "opportunity_taxonomy": [],
        "opportunity_hierarchy": {"primary": None, "secondary": [], "rejected": [], "ranked": []},
        "conditional_map": [],
        "market_tree": {},
        "counter_evidence": ["INSUFFICIENT_MARKET_DATA"],
        "invalidation": ["DATA_INSUFFICIENT"],
        "hard_veto": ["INSUFFICIENT_MARKET_DATA"],
        "no_trade_reasoning": ["WAIT_FOR_VALID_MARKET_INFORMATION"],
        "requires_downstream_confirmation": True,
        "entry": None,
        "decision": None,
        "reasons": ["INSUFFICIENT_MARKET_DATA"],
    }


def analyze_e2(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Independent opportunity brain. E1 is contextual cross-evidence only; E2 has no entry authority."""
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
    travel12 = max(sum(ranges[-12:]), 1e-12)
    efficiency12 = abs(last - closes[-13]) / travel12

    hi20, lo20 = max(highs[-21:-1]), min(lows[-21:-1])
    hi40, lo40 = max(highs[-41:-1]), min(lows[-41:-1])
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
        "short_slope": slope5 > 0.20,
        "medium_slope": slope20 > 0.45,
        "structure": bullish_structure,
        "efficiency": efficiency12 >= 0.30,
    }
    down_evidence = {
        "ema_gap": gap < -0.35,
        "ema20_slope": slope20_ema < -0.08,
        "ema50_slope": slope50_ema < 0.05,
        "short_slope": slope5 < -0.20,
        "medium_slope": slope20 < -0.45,
        "structure": bearish_structure,
        "efficiency": efficiency12 >= 0.30,
    }
    up = sum(up_evidence.values())
    down = sum(down_evidence.values())

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
    balanced = abs(slope20) < 0.65 and efficiency12 < 0.30 and width40 / atr < 8.5

    recent = [closes[-i] - closes[-i - 1] for i in range(1, 4)]
    follow_up = sum(x > 0 for x in recent)
    follow_down = sum(x < 0 for x in recent)
    net5 = (last - closes[-5]) / atr

    prior_impulse = max(closes[-11:-5]) - min(closes[-11:-5]) if len(closes) >= 11 else 0.0
    pullback_up = (
        gap > 0.20 and slope20 > 0.25 and prior_impulse >= 0.90 * atr
        and -0.80 <= net5 <= 0.15 and position40 < 0.80
    )
    pullback_down = (
        gap < -0.20 and slope20 < -0.25 and prior_impulse >= 0.90 * atr
        and -0.15 <= net5 <= 0.80 and position40 > 0.20
    )

    if acceptance_up and follow_up >= 2:
        auction_intent, auction_phase, intent_strength = "BUY_SIDE_ACCEPTANCE", "ACCEPTANCE", "HIGH"
        intent_reason = "initiative moved above prior range and price is holding with follow-through"
    elif acceptance_down and follow_down >= 2:
        auction_intent, auction_phase, intent_strength = "SELL_SIDE_ACCEPTANCE", "ACCEPTANCE", "HIGH"
        intent_reason = "initiative moved below prior range and price is holding with follow-through"
    elif rejection_high:
        auction_intent, auction_phase, intent_strength = "FAILED_HIGH_AUCTION", "REJECTION", "MODERATE"
        intent_reason = "price explored above prior range but returned inside"
    elif rejection_low:
        auction_intent, auction_phase, intent_strength = "FAILED_LOW_AUCTION", "REJECTION", "MODERATE"
        intent_reason = "price explored below prior range but returned inside"
    elif up >= 5 and net5 > 0.50:
        auction_intent, auction_phase, intent_strength = "BUYER_INITIATIVE_PENDING_ACCEPTANCE", "INITIATIVE", "MODERATE"
        intent_reason = "buyers show initiative but acceptance has not been proven"
    elif down >= 5 and net5 < -0.50:
        auction_intent, auction_phase, intent_strength = "SELLER_INITIATIVE_PENDING_ACCEPTANCE", "INITIATIVE", "MODERATE"
        intent_reason = "sellers show initiative but acceptance has not been proven"
    elif balanced:
        auction_intent, auction_phase, intent_strength = "TWO_SIDED_BALANCE", "BALANCE", "LOW"
        intent_reason = "auction is rotational and directionally inefficient"
    else:
        auction_intent, auction_phase, intent_strength = "UNCOMMITTED_AUCTION", "UNRESOLVED", "LOW"
        intent_reason = "neither side has demonstrated durable acceptance"

    def make_candidate(
        name: str, direction: str, regime: str, structure: bool, *,
        acceptance: bool = False, rejection: bool = False,
        pullback: bool = False, displacement: bool = False,
    ) -> dict[str, Any]:
        if direction == "UP":
            space = max((hi40 - last) / atr, 0.0)
            location_ok = 0.10 <= position40 <= 0.75
            extended = position40 >= 0.92
        else:
            space = max((last - lo40) / atr, 0.0)
            location_ok = 0.25 <= position40 <= 0.90
            extended = position40 <= 0.08

        vetoes: list[str] = []
        if not location_ok:
            vetoes.append("LOCATION_NOT_ADVANTAGEOUS")
        if space < 1.0:
            vetoes.append("INSUFFICIENT_OPPOSING_SPACE")
        if extended:
            vetoes.append("OVEREXTENDED_LOCATION")
        if name == "BREAKOUT_REPRICING" and not acceptance:
            vetoes.append("NO_ACCEPTANCE")
        if name == "PULLBACK_CONTINUATION" and not pullback:
            vetoes.append("NO_PULLBACK_STRUCTURE")
        if name == "LIQUIDITY_REVERSAL" and not rejection:
            vetoes.append("NO_LIQUIDITY_REJECTION")

        quality = max(0.0, min(1.0,
            0.18 * float(structure)
            + 0.18 * float(acceptance)
            + 0.16 * float(pullback)
            + 0.16 * float(rejection)
            + 0.12 * float(displacement)
            + 0.10 * float(location_ok)
            + 0.10 * min(space / 3.0, 1.0)
        ))
        return {
            "name": name, "direction": direction, "regime": regime,
            "quality": round(quality, 4), "space_atr": round(space, 4),
            "location_ok": location_ok, "structure": structure,
            "acceptance": acceptance, "rejection": rejection,
            "pullback": pullback, "displacement": displacement,
            "vetoes": vetoes, "eligible": not vetoes,
        }

    candidates: list[dict[str, Any]] = []
    if up >= 4:
        candidates.append(make_candidate(
            "PULLBACK_CONTINUATION", "UP", "TREND", bullish_structure,
            pullback=pullback_up, displacement=displacement_up, rejection=rejection_high,
        ))
    if down >= 4:
        candidates.append(make_candidate(
            "PULLBACK_CONTINUATION", "DOWN", "TREND", bearish_structure,
            pullback=pullback_down, displacement=displacement_down, rejection=rejection_low,
        ))
    if acceptance_up:
        candidates.append(make_candidate(
            "BREAKOUT_REPRICING", "UP", "BREAKOUT", bullish_structure,
            acceptance=True, displacement=displacement_up,
        ))
    if acceptance_down:
        candidates.append(make_candidate(
            "BREAKOUT_REPRICING", "DOWN", "BREAKOUT", bearish_structure,
            acceptance=True, displacement=displacement_down,
        ))
    if rejection_low:
        candidates.append(make_candidate(
            "LIQUIDITY_REVERSAL", "UP", "REVERSAL", bullish_structure,
            rejection=True, displacement=displacement_up,
        ))
    if rejection_high:
        candidates.append(make_candidate(
            "LIQUIDITY_REVERSAL", "DOWN", "REVERSAL", bearish_structure,
            rejection=True, displacement=displacement_down,
        ))
    if balanced and position40 <= 0.35:
        candidates.append(make_candidate("RANGE_ROTATION", "UP", "RANGE", True))
    if balanced and position40 >= 0.65:
        candidates.append(make_candidate("RANGE_ROTATION", "DOWN", "RANGE", True))

    ranked = sorted(candidates, key=lambda x: (x["quality"], x["space_atr"]), reverse=True)
    eligible = [x for x in ranked if x["eligible"]]
    primary = eligible[0] if eligible else None
    secondary = eligible[1:3] if eligible else []
    competing = bool(
        len(eligible) >= 2
        and eligible[0]["direction"] != eligible[1]["direction"]
        and abs(eligible[0]["quality"] - eligible[1]["quality"]) < 0.12
    )

    hard_veto: list[str] = []
    if primary is None:
        hard_veto.append("NO_ELIGIBLE_OPPORTUNITY")
    if competing:
        hard_veto.append("COMPETING_HYPOTHESES")
    if auction_intent in {
        "UNCOMMITTED_AUCTION", "BUYER_INITIATIVE_PENDING_ACCEPTANCE", "SELLER_INITIATIVE_PENDING_ACCEPTANCE",
    }:
        hard_veto.append("AUCTION_ACCEPTANCE_NOT_PROVEN")
    if primary and primary["direction"] == "UP" and position40 >= 0.88 and primary["space_atr"] < 1.0:
        hard_veto.append("LONG_CHASE_NO_SPACE")
    if primary and primary["direction"] == "DOWN" and position40 <= 0.12 and primary["space_atr"] < 1.0:
        hard_veto.append("SHORT_CHASE_NO_SPACE")

    direction = primary["direction"] if primary and not competing else "NEUTRAL"
    regime = primary["regime"] if primary and not competing else ("RANGE" if balanced else "TRANSITION")
    opportunity_name = primary["name"] if primary and not competing else (
        "WAIT_FOR_RANGE_EDGE" if balanced else "WAIT_FOR_REPRICING"
    )
    maturity = "ACCEPTED" if primary and primary["acceptance"] else (
        "REJECTED" if primary and primary["rejection"] else (
            "DEVELOPING" if primary else "UNPROVEN"
        )
    )

    counter_evidence: list[str] = []
    e1 = snapshot.get("E1_result") or {}
    e1_finding = str(e1.get("finding", "")).upper()
    if e1_finding and direction != "NEUTRAL":
        if direction == "UP" and ("DOWN" in e1_finding or "BEARISH" in e1_finding):
            counter_evidence.append("E1_BEARISH_VIEW_IS_COUNTER_EVIDENCE_NOT_COMMAND")
        if direction == "DOWN" and ("UP" in e1_finding or "BULLISH" in e1_finding):
            counter_evidence.append("E1_BULLISH_VIEW_IS_COUNTER_EVIDENCE_NOT_COMMAND")
    if rejection_high and direction == "UP":
        counter_evidence.append("FAILED_HIGH_AUCTION_AGAINST_LONG_THESIS")
    if rejection_low and direction == "DOWN":
        counter_evidence.append("FAILED_LOW_AUCTION_AGAINST_SHORT_THESIS")
    if efficiency12 < 0.15 and direction != "NEUTRAL":
        counter_evidence.append("LOW_AUCTION_EFFICIENCY")

    invalidation: list[str] = []
    if direction == "UP":
        invalidation.append("IF_price_accepts_below_recent_support_then_bullish_thesis_invalidates")
    elif direction == "DOWN":
        invalidation.append("IF_price_accepts_above_recent_resistance_then_bearish_thesis_invalidates")
    else:
        invalidation.append("IF_one_side_gains_confirmed_acceptance_then_neutral_state_invalidates")
    if primary and primary["name"] == "BREAKOUT_REPRICING":
        invalidation.append("IF_breakout_returns_inside_range_then_breakout_thesis_invalidates")
    if primary and primary["name"] == "LIQUIDITY_REVERSAL":
        invalidation.append("IF_rejection_level_is_reclaimed_in_the_original_direction_then_reversal_thesis_invalidates")

    if direction == "UP":
        strengthen = "IF buyers defend the pullback/reclaim and acceptance persists THEN continuation path strengthens"
        weaken = "IF upside fails and price returns through the defended area THEN bullish path weakens"
        opposite = "IF sellers gain confirmed acceptance below the opposing structure THEN bearish path becomes primary"
    elif direction == "DOWN":
        strengthen = "IF sellers defend the pullback/reject and acceptance persists THEN continuation path strengthens"
        weaken = "IF downside fails and price reclaims the defended area THEN bearish path weakens"
        opposite = "IF buyers gain confirmed acceptance above the opposing structure THEN bullish path becomes primary"
    elif balanced:
        strengthen = "IF range edge rejects and price rotates back toward value THEN range opportunity develops"
        weaken = "IF range edge fails without rejection THEN rotation thesis weakens"
        opposite = "IF range breaks and acceptance follows THEN breakout repricing becomes primary"
    else:
        strengthen = "IF one side gains closed-candle acceptance and follow-through THEN directional opportunity develops"
        weaken = "IF price remains two-sided and inefficient THEN directional thesis stays unproven"
        opposite = "IF the opposite side gains acceptance THEN the opportunity map flips"

    conditional_map = [
        {"if": strengthen.split(" THEN ")[0], "then": "THEN " + strengthen.split(" THEN ", 1)[1]},
        {"if": weaken.split(" THEN ")[0], "then": "THEN " + weaken.split(" THEN ", 1)[1]},
        {"if": opposite.split(" THEN ")[0], "then": "THEN " + opposite.split(" THEN ", 1)[1]},
    ]

    no_trade_reasoning: list[str] = list(hard_veto)
    if primary and not primary["acceptance"] and primary["name"] in {"BREAKOUT_REPRICING", "PULLBACK_CONTINUATION"}:
        no_trade_reasoning.append("OPPORTUNITY_REQUIRES_DOWNSTREAM_CONFIRMATION")
    if competing:
        no_trade_reasoning.append("DO_NOT_RESOLVE_COMPETING_HYPOTHESES_BY_SCORE_ALONE")
    if not no_trade_reasoning:
        no_trade_reasoning.append("NO_E2_ENTRY_AUTHORITY;_DOWNSTREAM_CONFIRMATION_REQUIRED")

    primary_thesis = (
        f"{direction}_{opportunity_name}_{maturity}"
        if direction != "NEUTRAL" else f"NEUTRAL_{opportunity_name}_UNPROVEN"
    )

    reasons = [
        "E2_INDEPENDENT_ANALYSIS",
        f"AUCTION_INTENT={auction_intent}",
        f"OPPORTUNITY={opportunity_name}",
        *[f"HARD_VETO={x}" for x in hard_veto],
        *[f"COUNTER={x}" for x in counter_evidence],
    ]

    taxonomy = [
        "TREND_CONTINUATION", "PULLBACK_CONTINUATION", "RANGE_ROTATION",
        "BREAKOUT_REPRICING", "LIQUIDITY_REVERSAL", "NO_OPPORTUNITY",
    ]

    return {
        "role": "OPPORTUNITY_REGIME_ANALYST",
        "question": QUESTION,
        "finding": primary_thesis,
        "state": "ANALYSIS_COMPLETE",
        "regime": regime,
        "direction": direction,
        "opportunity": opportunity_name,
        "opportunity_state": "WAIT" if hard_veto or primary is None else "DEVELOPING",
        "opportunity_maturity": maturity,
        "independence": "E2_INDEPENDENT_E1_CROSS_CHECK",
        "reasoning_mode": "PROFESSIONAL_DISCRETIONARY",
        "trade_decision_authority": "NONE",
        "auction_intent": auction_intent,
        "auction_intent_detail": {
            "phase": auction_phase, "strength": intent_strength, "reason": intent_reason,
            "acceptance_up": acceptance_up, "acceptance_down": acceptance_down,
            "rejection_high": rejection_high, "rejection_low": rejection_low,
        },
        "opportunity_taxonomy": taxonomy,
        "opportunity_hierarchy": {
            "primary": primary,
            "secondary": secondary,
            "rejected": [x for x in ranked if not x["eligible"]],
            "ranked": ranked,
            "selection_rule": "HIERARCHY_THEN_HARD_VETO_THEN_CONFIRMATION",
        },
        "primary_thesis": primary_thesis,
        "counter_evidence": counter_evidence,
        "invalidation": invalidation,
        "hard_veto": hard_veto,
        "asymmetric_opportunity": {
            "directional_space_atr": primary["space_atr"] if primary else 0.0,
            "location_position40": round(position40, 4),
            "path_quality": primary["quality"] if primary else 0.0,
            "is_asymmetric": bool(primary and primary["space_atr"] >= 1.5 and primary["location_ok"]),
        },
        "location": {
            "position40": round(position40, 4),
            "range_width_atr": round(width40 / atr, 4),
            "value_zone": "DISCOUNT" if position40 < 0.35 else "PREMIUM" if position40 > 0.65 else "EQUILIBRIUM",
        },
        "opposing_space": {
            "up_atr": round(max((hi40 - last) / atr, 0.0), 4),
            "down_atr": round(max((last - lo40) / atr, 0.0), 4),
        },
        "conditional_map": conditional_map,
        "market_tree": {
            "current_state": primary_thesis,
            "strengthen": strengthen,
            "weaken": weaken,
            "opposite": opposite,
        },
        "professional_reasoning": {
            "question": "What is the market offering, not what do I want it to do?",
            "context_vs_trade_decision": "E2 maps opportunity/context only; E7/E8/E9 decide confirmation, economics and final action.",
            "competing_hypotheses": [x["name"] + ":" + x["direction"] for x in eligible[:4]],
            "auction_intent_depth": intent_reason,
            "discretionary_rule": "Do not force a trade when path, location, opposing space or invalidation is unclear.",
        },
        "no_trade_reasoning": no_trade_reasoning,
        "requires_downstream_confirmation": True,
        "entry": None,
        "decision": None,
        "reasons": reasons,
        "observations": [
            f"atr14={atr:.8f}", f"ema_gap_atr={gap:.4f}",
            f"ema20_slope_atr={slope20_ema:.4f}", f"ema50_slope_atr={slope50_ema:.4f}",
            f"slope5_atr={slope5:.4f}", f"slope20_atr={slope20:.4f}",
            f"volatility_ratio={volatility_ratio:.4f}", f"efficiency12={efficiency12:.4f}",
            f"up_evidence={up}/7", f"down_evidence={down}/7",
            f"position_40={position40:.4f}",
            f"opposing_space_atr={primary['space_atr'] if primary else 0.0:.4f}",
        ],
    }
