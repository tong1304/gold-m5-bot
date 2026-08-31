from __future__ import annotations

from statistics import mean
from typing import Any

QUESTION = "What opportunity is the market offering right now?"
MIN_BARS = 80
ARCHITECTURE = "E2_PROFESSIONAL_OPPORTUNITY_CORE_V8"
MATURITY_ORDER = {"UNPROVEN": 0, "EMERGING": 1, "DEVELOPING": 2, "CONFIRMED": 3, "ACTIONABLE": 4}


def _text(v: Any) -> str:
    return str(v if v is not None else "").upper().strip()


def _dedupe(xs: list[Any]) -> list[str]:
    return list(dict.fromkeys(_text(x) for x in xs if _text(x)))


def _bars(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [b for b in (snapshot.get("bars") or [])
            if isinstance(b, dict) and all(k in b for k in ("open", "high", "low", "close"))]


def _num(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if x == x and abs(x) != float("inf") else default
    except (TypeError, ValueError):
        return default


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    a = 2.0 / (period + 1.0)
    out = values[0]
    for x in values[1:]:
        out = a * x + (1.0 - a) * out
    return out


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    tr: list[float] = []
    prev = _num(bars[0].get("close"))
    for b in bars[-period:]:
        h, l = _num(b.get("high")), _num(b.get("low"))
        tr.append(max(h - l, abs(h - prev), abs(l - prev)))
        prev = _num(b.get("close"))
    return mean(tr) if tr else 0.0


def _pivots(bars: list[dict[str, Any]], wing: int = 2) -> tuple[list[float], list[float]]:
    hs, ls = [], []
    for i in range(wing, len(bars) - wing):
        h, l = _num(bars[i]["high"]), _num(bars[i]["low"])
        window = bars[i-wing:i+wing+1]
        if h >= max(_num(x["high"]) for x in window):
            hs.append(h)
        if l <= min(_num(x["low"]) for x in window):
            ls.append(l)
    return hs, ls


def _unavailable() -> dict[str, Any]:
    return {
        "role": "OPPORTUNITY_REGIME_ANALYST", "question": QUESTION,
        "finding": "INSUFFICIENT_DATA", "state": "UNAVAILABLE",
        "architecture": ARCHITECTURE, "regime": "UNRESOLVED",
        "regime_phase": "UNRESOLVED", "direction": "NEUTRAL",
        "opportunity_direction": "NEUTRAL", "opportunity_bias": "NEUTRAL",
        "phase": "UNRESOLVED", "opportunity": "NONE",
        "opportunity_state": "WAIT", "opportunity_maturity": "UNPROVEN",
        "independence": "E2_FIRST_E1_CROSS_CHECK", "auction_state": "UNKNOWN",
        "auction_intent": "UNKNOWN", "auction_intent_detail": {},
        "location_context": "UNKNOWN", "opposing_space_atr": 0.0,
        "regime_confidence": 0.0, "confidence": 0.0, "opportunity_score": 0.0,
        "candidate_hypotheses": [], "candidate_setups": [], "candidate_playbooks": [],
        "preferred_playbook": None, "counter_evidence": [],
        "counter_evidence_severity": "HIGH",
        "missing_evidence": ["sufficient closed-candle market evidence"],
        "confirmation_required": ["sufficient closed-candle market evidence"],
        "invalidation_evidence": [], "why_not_trade": ["INSUFFICIENT_MARKET_DATA"],
        "conditional_map": [], "market_tree": {}, "opportunity_hierarchy": {},
        "hard_veto": ["INSUFFICIENT_MARKET_DATA"],
        "requires_downstream_confirmation": True, "opportunity_decision": "WAIT",
        "entry": None, "trigger": None, "decision": None,
        "evidence": ["INSUFFICIENT_MARKET_DATA"],
        "conflicts": ["INSUFFICIENT_MARKET_DATA"],
        "reasoning_trace": ["No thesis: insufficient closed-candle evidence."],
        "professional_reasoning": {
            "question": QUESTION, "thesis": "No thesis: insufficient data.",
            "conclusion": "No opportunity can be classified from insufficient data.",
            "why_now": "Insufficient data.", "expected_path": "WAIT_FOR_SUFFICIENT_DATA",
            "required_evidence": ["sufficient closed-candle market evidence"],
            "invalidation_conditions": ["data integrity failure"],
            "timing": "WAIT", "opportunity_quality": 0.0,
            "counter_evidence_count": 1, "independent_thesis": True,
            "e1_used_as": "CROSS_CHECK_ONLY", "entry_authorized": False,
        },
        "reasoning_mode": "SINGLE_PROFESSIONAL_CORE", "sub_engines_active": False,
        "gate": None, "timing_state": "WAIT",
        "reasons": ["INSUFFICIENT_MARKET_DATA"],
    }


def _classify_opportunity(*, up: int, down: int, auction: str, balanced: bool,
                          acceptance: bool, rejection: bool, space_atr: float,
                          location_ok: bool) -> dict[str, Any]:
    """Classify opportunity quality without authorizing an order."""
    if up >= 5 and up > down:
        direction = "BUY"
    elif down >= 5 and down > up:
        direction = "SELL"
    else:
        direction = "NEUTRAL"

    blockers: list[str] = []
    missing: list[str] = []
    directional_conflict = direction != "NEUTRAL" and min(up, down) >= 4 and abs(up - down) <= 1
    if directional_conflict:
        blockers.append("DIRECTIONAL_EVIDENCE_CONFLICT")
        missing.append("clear directional dominance")
    if direction != "NEUTRAL" and not acceptance and not rejection:
        blockers.append("AUCTION_CONFIRMATION_PENDING")
        missing.append("closed-candle acceptance/follow-through proves the auction")
    if direction != "NEUTRAL" and not location_ok:
        blockers.append("LOCATION_NOT_ADVANTAGEOUS")
        missing.append("advantageous location")
    if direction != "NEUTRAL" and space_atr < 1.0:
        blockers.append("INSUFFICIENT_OPPOSING_SPACE")
        missing.append("adequate opposing space")
    if auction in {"UNCOMMITTED_AUCTION", "BUYER_INITIATIVE_PENDING_ACCEPTANCE",
                   "SELLER_INITIATIVE_PENDING_ACCEPTANCE"}:
        blockers.append("AUCTION_ACCEPTANCE_NOT_PROVEN")
    if direction == "NEUTRAL":
        blockers.append("DIRECTIONAL_EDGE_NOT_ESTABLISHED")

    hard_quality_block = (
        directional_conflict or
        (direction != "NEUTRAL" and not location_ok) or
        (direction != "NEUTRAL" and space_atr < 1.0)
    )
    if direction == "NEUTRAL":
        maturity = "EMERGING" if balanced else "UNPROVEN"
        finding = "BALANCED_AUCTION" if balanced else "UNRESOLVED"
    elif rejection and not hard_quality_block:
        maturity, finding = "DEVELOPING", "CONDITIONAL_REVERSAL_OPPORTUNITY"
    elif acceptance and not hard_quality_block:
        maturity, finding = "CONFIRMED", "CONDITIONAL_OPPORTUNITY_CONFIRMED"
    else:
        maturity, finding = "DEVELOPING", "CONDITIONAL_DIRECTIONAL_OPPORTUNITY"
    return {"direction": direction, "finding": finding,
            "opportunity_maturity": maturity, "missing_evidence": _dedupe(missing),
            "blockers": _dedupe(blockers)}


def _candidate(name: str, direction: str, structure: bool, acceptance: bool,
               rejection: bool, pullback: bool, displacement: bool,
               location_ok: bool, space_atr: float, auction: str,
               efficiency: float, acceptance_confirmed: bool) -> dict[str, Any]:
    vetoes: list[str] = []
    if not structure:
        vetoes.append("STRUCTURE_NOT_ESTABLISHED")
    if not location_ok:
        vetoes.append("LOCATION_NOT_ADVANTAGEOUS")
    if space_atr < 1.0:
        vetoes.append("INSUFFICIENT_OPPOSING_SPACE")
    if name == "AUCTION_ACCEPTANCE_CONTINUATION" and not acceptance_confirmed:
        vetoes.append("ACCEPTANCE_FOLLOW_THROUGH_NOT_PROVEN")
    if name == "LIQUIDITY_REVERSAL" and not rejection:
        vetoes.append("FAILED_AUCTION_NOT_PROVEN")
    if name == "TREND_PULLBACK_CONTINUATION" and not pullback:
        vetoes.append("PULLBACK_NOT_ESTABLISHED")
    if name == "TREND_PULLBACK_CONTINUATION" and not (acceptance_confirmed or displacement):
        vetoes.append("CONTINUATION_EVIDENCE_NOT_ESTABLISHED")
    quality = (
        0.22 * float(structure) + 0.22 * float(acceptance_confirmed) +
        0.18 * float(rejection) + 0.16 * float(pullback) +
        0.10 * float(displacement) + 0.06 * float(location_ok) +
        0.06 * min(space_atr / 3.0, 1.0)
    )
    return {"name": name, "direction": direction,
            "evidence_score": round(quality, 3), "quality": round(quality, 3),
            "space_atr": round(space_atr, 3), "structure": structure,
            "acceptance": acceptance_confirmed, "rejection": rejection,
            "pullback": pullback, "displacement": displacement,
            "location_ok": location_ok, "auction_intent": auction,
            "eligible": not vetoes, "vetoes": vetoes,
            "efficiency": round(efficiency, 3)}


def _regime_phase(*, direction: str, auction_phase: str, efficiency: float,
                  persistence: float, extension_atr: float,
                  acceptance_confirmed: bool, rejection: bool) -> str:
    if rejection and not acceptance_confirmed:
        return "FAILED"
    if direction == "NEUTRAL":
        return "MATURE" if auction_phase == "BALANCE" else "UNRESOLVED"
    if extension_atr >= 2.75 and efficiency < 0.35:
        return "LATE"
    if acceptance_confirmed or (persistence >= 0.75 and efficiency >= 0.30):
        return "MATURE"
    return "EARLY"


def analyze_e2(snapshot: dict[str, Any]) -> dict[str, Any]:
    bars = _bars(snapshot)
    if len(bars) < MIN_BARS:
        return _unavailable()
    closes = [_num(b["close"]) for b in bars]
    highs = [_num(b["high"]) for b in bars]
    lows = [_num(b["low"]) for b in bars]
    opens = [_num(b["open"]) for b in bars]
    atr = max(_atr(bars), 1e-12)
    last = closes[-1]
    e20, e50 = _ema(closes, 20), _ema(closes, 50)
    prev20, prev50 = _ema(closes[:-5], 20), _ema(closes[:-5], 50)
    gap, s20, s50 = (e20 - e50) / atr, (e20 - prev20) / atr, (e50 - prev50) / atr
    s5, s20p = (last - closes[-6]) / atr, (last - closes[-21]) / atr
    ranges = [max(_num(b["high"]) - _num(b["low"]), 0.0) for b in bars]
    avg20 = max(mean(ranges[-20:]), 1e-12)
    efficiency = abs(last - closes[-13]) / max(sum(ranges[-12:]), 1e-12)
    hi20, lo20 = max(highs[-21:-1]), min(lows[-21:-1])
    hi40, lo40 = max(highs[-41:-1]), min(lows[-41:-1])
    width = max(hi40 - lo40, 1e-12)
    pos = max(0.0, min(1.0, (last - lo40) / width))
    ph, pl = _pivots(bars)
    bullish = len(ph) >= 2 and ph[-1] > ph[-2] and len(pl) >= 2 and pl[-1] > pl[-2]
    bearish = len(ph) >= 2 and ph[-1] < ph[-2] and len(pl) >= 2 and pl[-1] < pl[-2]
    up = sum((gap > .35, s20 > .08, s50 > -.05, s5 > .20, s20p > .45, bullish, efficiency >= .30))
    down = sum((gap < -.35, s20 < -.08, s50 < .05, s5 < -.20, s20p < -.45, bearish, efficiency >= .30))
    span = max(highs[-1] - lows[-1], 1e-12)
    body = abs(last - opens[-1]) / span
    cp = (last - lows[-1]) / span
    uw = (highs[-1] - max(opens[-1], last)) / span
    lw = (min(opens[-1], last) - lows[-1]) / span
    broke_up, broke_down = last > hi20, last < lo20
    sweep_high = highs[-1] > hi20 and last <= hi20
    sweep_low = lows[-1] < lo20 and last >= lo20
    acceptance_up_raw = broke_up and cp >= .65 and body >= .45
    acceptance_down_raw = broke_down and cp <= .35 and body >= .45
    rejection_high = sweep_high and cp <= .45 and uw >= .20
    rejection_low = sweep_low and cp >= .55 and lw >= .20
    displacement_up = body >= .60 and cp >= .75 and span >= 1.25 * avg20
    displacement_down = body >= .60 and cp <= .25 and span >= 1.25 * avg20
    follow_up = sum(closes[-i] > closes[-i-1] for i in range(1, 4))
    follow_down = sum(closes[-i] < closes[-i-1] for i in range(1, 4))
    acceptance_up = acceptance_up_raw and follow_up >= 2
    acceptance_down = acceptance_down_raw and follow_down >= 2
    net5 = (last - closes[-5]) / atr
    if acceptance_up:
        auction, auction_phase, strength, reason = "BUY_SIDE_ACCEPTANCE", "ACCEPTANCE", "HIGH", "buyers broke and held the prior boundary with closed-candle follow-through"
    elif acceptance_down:
        auction, auction_phase, strength, reason = "SELL_SIDE_ACCEPTANCE", "ACCEPTANCE", "HIGH", "sellers broke and held the prior boundary with closed-candle follow-through"
    elif rejection_high:
        auction, auction_phase, strength, reason = "FAILED_HIGH_AUCTION", "REJECTION", "MODERATE", "price swept the prior high and closed back inside"
    elif rejection_low:
        auction, auction_phase, strength, reason = "FAILED_LOW_AUCTION", "REJECTION", "MODERATE", "price swept the prior low and closed back inside"
    elif up >= 5 and net5 > .5:
        auction, auction_phase, strength, reason = "BUYER_INITIATIVE_PENDING_ACCEPTANCE", "INITIATIVE", "MODERATE", "buyers show initiative but terminal acceptance is not proven"
    elif down >= 5 and net5 < -.5:
        auction, auction_phase, strength, reason = "SELLER_INITIATIVE_PENDING_ACCEPTANCE", "INITIATIVE", "MODERATE", "sellers show initiative but terminal acceptance is not proven"
    elif abs(s20p) < .65 and efficiency < .30 and width / atr < 8.5:
        auction, auction_phase, strength, reason = "TWO_SIDED_BALANCE", "BALANCE", "LOW", "price is rotational and directionally inefficient"
    else:
        auction, auction_phase, strength, reason = "UNCOMMITTED_AUCTION", "UNRESOLVED", "LOW", "neither side has sufficient closed-candle auction proof"
    balanced = auction == "TWO_SIDED_BALANCE"
    long_loc, short_loc = .10 <= pos <= .75, .25 <= pos <= .90
    long_space, short_space = max((hi40 - last) / atr, 0.0), max((last - lo40) / atr, 0.0)
    base = _classify_opportunity(up=up, down=down, auction=auction, balanced=balanced,
        acceptance=acceptance_up or acceptance_down, rejection=rejection_high or rejection_low,
        space_atr=long_space if up >= down else short_space, location_ok=long_loc if up >= down else short_loc)
    direction = base["direction"]
    candidates: list[dict[str, Any]] = []
    if bullish and rejection_low:
        candidates.append(_candidate("LIQUIDITY_REVERSAL", "BUY", bullish, False, True, False, displacement_up, long_loc, long_space, auction, efficiency, acceptance_up))
    if bearish and rejection_high:
        candidates.append(_candidate("LIQUIDITY_REVERSAL", "SELL", bearish, False, True, False, displacement_down, short_loc, short_space, auction, efficiency, acceptance_down))
    if acceptance_up:
        candidates.append(_candidate("AUCTION_ACCEPTANCE_CONTINUATION", "BUY", bullish, True, False, False, displacement_up, long_loc, long_space, auction, efficiency, True))
    if acceptance_down:
        candidates.append(_candidate("AUCTION_ACCEPTANCE_CONTINUATION", "SELL", bearish, True, False, False, displacement_down, short_loc, short_space, auction, efficiency, True))
    prior_up, prior_down = closes[-6] > closes[-11], closes[-6] < closes[-11]
    retr_up = last < max(closes[-2], closes[-3]) and last > min(closes[-6:-1])
    retr_down = last > min(closes[-2], closes[-3]) and last < max(closes[-6:-1])
    pull_up, pull_down = bullish and prior_up and retr_up and not rejection_high, bearish and prior_down and retr_down and not rejection_low
    if pull_up:
        candidates.append(_candidate("TREND_PULLBACK_CONTINUATION", "BUY", bullish, False, False, True, displacement_up, long_loc, long_space, auction, efficiency, acceptance_up))
    if pull_down:
        candidates.append(_candidate("TREND_PULLBACK_CONTINUATION", "SELL", bearish, False, False, True, displacement_down, short_loc, short_space, auction, efficiency, acceptance_down))
    if not candidates and direction in {"BUY", "SELL"}:
        is_buy = direction == "BUY"
        candidates.append(_candidate("DIRECTIONAL_CONTINUATION_WATCH", direction, bullish if is_buy else bearish,
            acceptance_up_raw if is_buy else acceptance_down_raw, False, False,
            displacement_up if is_buy else displacement_down, long_loc if is_buy else short_loc,
            long_space if is_buy else short_space, auction, efficiency,
            acceptance_up if is_buy else acceptance_down))
    eligible = [c for c in candidates if c["eligible"]]
    blockers = list(base["blockers"])
    if direction != "NEUTRAL" and not eligible:
        blockers.append("NO_ELIGIBLE_OPPORTUNITY_PATH")
    active_space = long_space if direction == "BUY" else short_space
    if direction != "NEUTRAL" and active_space < 1.0:
        blockers.append("OPPOSING_SPACE_CONSTRAINED")
    blockers = _dedupe(blockers)
    missing = list(base["missing_evidence"])
    if direction != "NEUTRAL" and active_space < 1.0 and "adequate opposing space" not in missing:
        missing.append("adequate opposing space")
    if direction != "NEUTRAL" and not (acceptance_up or acceptance_down or rejection_high or rejection_low):
        if "closed-candle acceptance/follow-through proves the auction" not in missing:
            missing.append("closed-candle acceptance/follow-through proves the auction")
    directional_strength, separation = max(up, down) / 7.0, abs(up - down) / 7.0
    space_quality = min(active_space / 2.0, 1.0) if direction != "NEUTRAL" else 0.0
    confidence = 100.0 * (.45 * directional_strength + .25 * separation + .15 * min(efficiency / .5, 1.0) + .15 * space_quality) if direction != "NEUTRAL" else 100.0 * (.5 * min(abs(up - down) / 3.0, 1.0) + .5 * float(balanced))
    persistence = max(sum(closes[-i] > closes[-i-1] for i in range(1, 5)), sum(closes[-i] < closes[-i-1] for i in range(1, 5))) / 4.0
    extension_atr = abs(last - (hi40 + lo40) / 2.0) / atr
    phase = _regime_phase(direction=direction, auction_phase=auction_phase, efficiency=efficiency,
        persistence=persistence, extension_atr=extension_atr,
        acceptance_confirmed=acceptance_up or acceptance_down,
        rejection=rejection_high or rejection_low)
    maturity = base["opportunity_maturity"]
    if blockers and maturity == "CONFIRMED":
        maturity = "DEVELOPING"
    preferred = max(eligible, key=lambda c: c["quality"]) if eligible else None
    public_direction = "UP" if direction == "BUY" else "DOWN" if direction == "SELL" else "NEUTRAL"
    regime = "RANGE" if balanced else "TREND" if direction != "NEUTRAL" and not (rejection_high or rejection_low) else "TRANSITION"
    evidence = [f"DIRECTIONAL_SCORE_UP={up}", f"DIRECTIONAL_SCORE_DOWN={down}", f"AUCTION={auction}", f"AUCTION_PHASE={auction_phase}", f"LOCATION={'FAVORABLE' if (long_loc if direction == 'BUY' else short_loc) else 'CONSTRAINED'}", f"OPPOSING_SPACE_ATR={round(active_space, 3) if direction != 'NEUTRAL' else 0.0}", f"FOLLOW_THROUGH_UP={follow_up}", f"FOLLOW_THROUGH_DOWN={follow_down}", f"EFFICIENCY={round(efficiency, 3)}"]
    reasoning_trace = [f"Question: {QUESTION}", f"Independent directional assessment: UP={up}, DOWN={down}.", f"Auction assessment: {auction} / phase={auction_phase}.", "Location and opposing-space assessment applied before maturity.", f"Opportunity maturity={maturity}; execution authority remains downstream."]
    reasoning = {"question": QUESTION, "conclusion": f"{public_direction} opportunity is {maturity.lower()} based on closed-candle evidence.", "why_now": reason, "expected_path": "AUCTION_ACCEPTANCE_AND_FOLLOW_THROUGH" if direction != "NEUTRAL" else "WAIT_FOR_DIRECTIONAL_EVIDENCE", "required_evidence": _dedupe(missing), "invalidation_conditions": ["closed-candle invalidation of the directional auction or structural thesis"], "timing": "READY_FOR_CONFIRMATION" if maturity == "CONFIRMED" else "DEVELOPING" if direction != "NEUTRAL" else "WAIT", "opportunity_quality": round(confidence, 2), "counter_evidence_count": len(blockers), "independent_thesis": True, "e1_used_as": "CROSS_CHECK_ONLY", "entry_authorized": False, "evidence_hierarchy": ["closed_candle_auction", "directional_pressure", "structure", "location", "opposing_space"], "maturity_boundary": "E2 classifies opportunity maturity only; E7/E8/E9 control confirmation, economics and execution."}
    return {"role": "OPPORTUNITY_REGIME_ANALYST", "question": QUESTION, "finding": base["finding"], "state": "ANALYSIS_COMPLETE", "architecture": ARCHITECTURE, "regime": regime, "regime_phase": phase, "direction": public_direction, "opportunity_direction": public_direction, "opportunity_bias": public_direction, "reasoning_mode": "SINGLE_PROFESSIONAL_CORE", "sub_engines_active": False, "gate": None, "timing_state": reasoning["timing"], "independence": "E2_FIRST_E1_CROSS_CHECK", "phase": auction_phase, "auction_state": "CONFIRMED" if auction_phase == "ACCEPTANCE" else "REJECTED" if auction_phase == "REJECTION" else "PENDING", "auction_intent": auction, "auction_intent_detail": {"strength": strength, "reason": reason, "closed_candle_only": True, "follow_through_up": follow_up, "follow_through_down": follow_down, "terminal_confirmation": acceptance_up or acceptance_down}, "location_context": "FAVORABLE" if (long_loc if direction == "BUY" else short_loc) else "CONSTRAINED", "opposing_space_atr": round(active_space, 3) if direction != "NEUTRAL" else 0.0, "regime_confidence": round(confidence / 100.0, 3), "confidence": round(confidence / 100.0, 3), "opportunity_score": round(confidence, 2), "opportunity_maturity": maturity, "opportunity_state": "VISIBLE" if maturity == "CONFIRMED" else "VISIBLE_PENDING_PROOF" if direction != "NEUTRAL" else "WAIT", "candidate_hypotheses": candidates, "candidate_setups": candidates, "candidate_playbooks": candidates, "preferred_playbook": preferred, "counter_evidence": blockers, "conflicts": blockers, "counter_evidence_severity": "HIGH" if blockers else "LOW", "missing_evidence": _dedupe(missing), "confirmation_required": _dedupe(missing), "invalidation_evidence": [], "why_not_trade": blockers, "conditional_map": [{"condition": "AUCTION_CONFIRMED", "path": "CONTINUATION"}, {"condition": "AUCTION_REJECTED", "path": "REVERSAL_WATCH"}, {"condition": "DIRECTIONAL_EDGE_LOST", "path": "WAIT"}], "market_tree": {"directional_evidence": {"up": up, "down": down}, "auction": auction, "balanced": balanced, "position40": round(pos, 3), "location": "FAVORABLE" if (long_loc if direction == "BUY" else short_loc) else "CONSTRAINED"}, "opportunity_hierarchy": {"direction": "E2", "auction": "E2", "confirmation": "E7", "economics": "E8", "execution": "E9"}, "hard_veto": [], "requires_downstream_confirmation": True, "opportunity_decision": "CONDITIONAL" if maturity == "CONFIRMED" else "WAIT", "entry": None, "trigger": None, "decision": None, "evidence": evidence, "reasoning_trace": reasoning_trace, "professional_reasoning": reasoning, "reasons": _dedupe(blockers + ["E2_OPPORTUNITY_CLASSIFICATION", "CLOSED_CANDLE_ONLY", "NO_LOOKAHEAD", "E1_USED_AS_CROSS_CHECK_ONLY"])}
