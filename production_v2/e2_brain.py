from __future__ import annotations

from statistics import mean
from typing import Any

QUESTION = "What opportunity is the market offering right now?"
MIN_BARS = 80
ARCHITECTURE = "E2_PROFESSIONAL_OPPORTUNITY_CORE"


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
        "observations": [], "evidence": [],
        "evidence_map": {"directional_pressure": "NEUTRAL", "location": "MID_RANGE"},
        "counter_evidence": ["insufficient closed-candle history"],
        "counter_evidence_severity": "THESIS_INVALIDATION", "missing_evidence": [f"{MIN_BARS} valid closed candles"],
        "invalidation_evidence": [], "why_not_trade": ["insufficient market data"],
        "counterfactual": ["without sufficient history, no directional thesis is trustworthy"],
        "decision": None, "entry": None, "trigger": None, "risk": None, "gate": None,
        "trade_decision_authority": "E9_ONLY", "reason_codes": ["INSUFFICIENT_MARKET_DATA"],
        "professional_reasoning": {
            "question": QUESTION, "conclusion": "NO_OPPORTUNITY_THESIS", "why_now": "Insufficient evidence.",
            "expected_path": "Wait for sufficient closed-candle history.",
            "required_evidence": [f"{MIN_BARS} valid closed candles"],
            "invalidation_conditions": ["data insufficiency"], "timing": "WAIT", "opportunity_quality": "LOW",
            "opportunity_decision": "WAIT", "edge_assessment": "NO_EDGE", "counter_evidence_count": 1,
            "counter_evidence": ["insufficient market data"], "independent_thesis": True,
            "e1_used_as": "CROSS_CHECK_ONLY", "entry_authorized": False,
        },
    }


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _quality(candidate: dict[str, Any]) -> float:
    """Descriptive opportunity quality; never a win probability or entry score."""
    weights = {
        "structure": 0.18, "acceptance": 0.16, "location": 0.16, "path": 0.16,
        "trigger_readiness": 0.10, "efficiency": 0.08, "volatility": 0.06,
        "rejection_penalty": -0.08, "extension_penalty": -0.10,
    }
    return _clip(sum(weights[k] * float(candidate.get(k, 0.0)) for k in weights))


def _candidate(name: str, direction: str, regime: str, *, structure: float,
               acceptance: float, location: float, path: float, trigger_readiness: float,
               efficiency: float, volatility: float, rejected: bool, extended: bool,
               pullback: bool, displacement: bool, hard_veto: list[str]) -> dict[str, Any]:
    c = {
        "name": name, "direction": direction, "regime": regime,
        "structure": _clip(structure), "acceptance": _clip(acceptance),
        "location": _clip(location), "path": _clip(path),
        "trigger_readiness": _clip(trigger_readiness), "efficiency": _clip(efficiency),
        "volatility": _clip(volatility), "rejection_penalty": 1.0 if rejected else 0.0,
        "extension_penalty": 1.0 if extended else 0.0, "rejected": rejected,
        "extended": extended, "pullback": pullback, "displacement": displacement,
        "hard_veto": list(hard_veto),
    }
    c["quality"] = _quality(c)
    c["eligible"] = not hard_veto
    return c


def analyze_e2(snapshot: dict[str, Any]) -> dict[str, Any]:
    """E2 professional opportunity brain.

    E2 answers one question only: what opportunity is the market offering now?
    It forms its own thesis from market behavior, location and path, then uses
    E1 only as a cross-check. E2 never authorizes entry, risk, or a trade.
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

    ema20, ema50 = _ema(c, 20), _ema(c, 50)
    ema20_prev, ema50_prev = _ema(c[:-5], 20), _ema(c[:-5], 50)
    ema_gap = (ema20 - ema50) / atr
    ema20_slope = (ema20 - ema20_prev) / atr
    ema50_slope = (ema50 - ema50_prev) / atr

    ranges = [max(float(b["high"]) - float(b["low"]), 0.0) for b in bs]
    avg20 = max(mean(ranges[-20:]), 1e-12)
    vol_ratio = mean(ranges[-5:]) / avg20
    slope5 = (c[-1] - c[-6]) / atr
    slope20 = (c[-1] - c[-21]) / atr
    efficiency12 = abs(c[-1] - c[-13]) / max(sum(ranges[-12:]), 1e-12)

    hi20, lo20 = max(h[-21:-1]), min(l[-21:-1])
    hi40, lo40 = max(h[-41:-1]), min(l[-41:-1])
    width40 = max(hi40 - lo40, atr)
    pos40 = _clip((last - lo40) / width40)

    ph, pl = _pivots(bs)
    hh = len(ph) >= 2 and ph[-1] > ph[-2]
    lh = len(ph) >= 2 and ph[-1] < ph[-2]
    hl = len(pl) >= 2 and pl[-1] > pl[-2]
    ll = len(pl) >= 2 and pl[-1] < pl[-2]
    bull_structure = hh and hl
    bear_structure = lh and ll

    up_evidence = sum((ema_gap > 0.35, ema20_slope > 0.08, ema50_slope > -0.05,
                       slope5 > 0.20, slope20 > 0.45, bull_structure, efficiency12 >= 0.30))
    down_evidence = sum((ema_gap < -0.35, ema20_slope < -0.08, ema50_slope < 0.05,
                         slope5 < -0.20, slope20 < -0.45, bear_structure, efficiency12 >= 0.30))

    span = max(h[-1] - l[-1], 1e-12)
    body = abs(last - o[-1]) / span
    close_pos = (last - l[-1]) / span
    upper_wick = (h[-1] - max(o[-1], last)) / span
    lower_wick = (min(o[-1], last) - l[-1]) / span

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
    impulse_high = max(h[-8:-2])
    impulse_low = min(l[-8:-2])
    impulse_width = max(impulse_high - impulse_low, atr)
    retrace_up = _clip((impulse_high - last) / impulse_width)
    retrace_down = _clip((last - impulse_low) / impulse_width)
    controlled_up = impulse_up and 0.20 <= retrace_up <= 0.65 and last > lo20 and ema20 >= ema50
    controlled_down = impulse_down and 0.20 <= retrace_down <= 0.65 and last < hi20 and ema20 <= ema50
    pullback_up = controlled_up and (lower_wick >= 0.15 or close_pos >= 0.55 or c[-1] >= c[-2])
    pullback_down = controlled_down and (upper_wick >= 0.15 or close_pos <= 0.45 or c[-1] <= c[-2])

    compressed = vol_ratio < 0.72
    expanding = vol_ratio > 1.28
    balanced = abs(slope20) < 0.65 and efficiency12 < 0.30 and width40 / atr < 8.5

    # 1. Independent auction read. E1 is deliberately absent here.
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

    # 2. Competing opportunity hypotheses.
    candidates: list[dict[str, Any]] = []

    if up_evidence >= 4:
        path = _clip((hi40 - last) / (3.0 * atr))
        location = 1.0 if 0.10 <= pos40 <= 0.75 else 0.35 if pos40 < 0.90 else 0.0
        hard = []
        if pos40 >= 0.94:
            hard.append("LOCATION_TOO_EXTENDED")
        if (hi40 - last) / atr < 1.0:
            hard.append("INSUFFICIENT_OPPOSING_SPACE")
        if rejected_up and pos40 >= 0.80:
            hard.append("FAILED_HIGH_ACCEPTANCE")
        candidates.append(_candidate("TREND_PULLBACK_CONTINUATION", "UP", "TREND", structure=1.0 if bull_structure else 0.25,
            acceptance=1.0 if accepted_up or displacement_up else 0.25, location=location, path=path,
            trigger_readiness=1.0 if pullback_up else 0.35, efficiency=_clip(efficiency12 / 0.55),
            volatility=1.0 if 0.75 <= vol_ratio <= 1.55 else 0.35, rejected=rejected_up, extended=pos40 >= 0.92,
            pullback=pullback_up, displacement=displacement_up, hard_veto=hard))
        hard = []
        if pos40 >= 0.94: hard.append("LOCATION_TOO_EXTENDED")
        if (hi40 - last) / atr < 1.0: hard.append("INSUFFICIENT_OPPOSING_SPACE")
        candidates.append(_candidate("TREND_CONTINUATION", "UP", "TREND", structure=1.0 if bull_structure else 0.25,
            acceptance=1.0 if accepted_up or displacement_up else 0.20, location=location, path=path,
            trigger_readiness=1.0 if accepted_up or displacement_up else 0.25, efficiency=_clip(efficiency12 / 0.55),
            volatility=1.0 if 0.75 <= vol_ratio <= 1.55 else 0.35, rejected=rejected_up, extended=pos40 >= 0.92,
            pullback=False, displacement=displacement_up, hard_veto=hard))

    if down_evidence >= 4:
        path = _clip((last - lo40) / (3.0 * atr))
        location = 1.0 if 0.25 <= pos40 <= 0.90 else 0.35 if pos40 > 0.10 else 0.0
        hard = []
        if pos40 <= 0.06: hard.append("LOCATION_TOO_EXTENDED")
        if (last - lo40) / atr < 1.0: hard.append("INSUFFICIENT_OPPOSING_SPACE")
        if rejected_down and pos40 <= 0.20: hard.append("FAILED_LOW_ACCEPTANCE")
        candidates.append(_candidate("TREND_PULLBACK_CONTINUATION", "DOWN", "TREND", structure=1.0 if bear_structure else 0.25,
            acceptance=1.0 if accepted_down or displacement_down else 0.25, location=location, path=path,
            trigger_readiness=1.0 if pullback_down else 0.35, efficiency=_clip(efficiency12 / 0.55),
            volatility=1.0 if 0.75 <= vol_ratio <= 1.55 else 0.35, rejected=rejected_down, extended=pos40 <= 0.08,
            pullback=pullback_down, displacement=displacement_down, hard_veto=hard))
        hard = []
        if pos40 <= 0.06: hard.append("LOCATION_TOO_EXTENDED")
        if (last - lo40) / atr < 1.0: hard.append("INSUFFICIENT_OPPOSING_SPACE")
        candidates.append(_candidate("TREND_CONTINUATION", "DOWN", "TREND", structure=1.0 if bear_structure else 0.25,
            acceptance=1.0 if accepted_down or displacement_down else 0.20, location=location, path=path,
            trigger_readiness=1.0 if accepted_down or displacement_down else 0.25, efficiency=_clip(efficiency12 / 0.55),
            volatility=1.0 if 0.75 <= vol_ratio <= 1.55 else 0.35, rejected=rejected_down, extended=pos40 <= 0.08,
            pullback=False, displacement=displacement_down, hard_veto=hard))

    if accepted_up:
        hard = ["NO_POST_BREAKOUT_SPACE"] if (hi40 - last) / atr < 1.0 else []
        candidates.append(_candidate("BREAKOUT_CONTINUATION", "UP", "BREAKOUT", structure=1.0 if bull_structure else 0.35,
            acceptance=1.0, location=1.0 if 0.35 <= pos40 <= 0.88 else 0.35, path=_clip((hi40 - last) / (3.0 * atr)),
            trigger_readiness=1.0 if expanding or displacement_up else 0.45, efficiency=_clip(efficiency12 / 0.55),
            volatility=1.0 if expanding else 0.55, rejected=rejected_up, extended=pos40 >= 0.92,
            pullback=False, displacement=displacement_up, hard_veto=hard))

    if accepted_down:
        hard = ["NO_POST_BREAKOUT_SPACE"] if (last - lo40) / atr < 1.0 else []
        candidates.append(_candidate("BREAKOUT_CONTINUATION", "DOWN", "BREAKOUT", structure=1.0 if bear_structure else 0.35,
            acceptance=1.0, location=1.0 if 0.12 <= pos40 <= 0.65 else 0.35, path=_clip((last - lo40) / (3.0 * atr)),
            trigger_readiness=1.0 if expanding or displacement_down else 0.45, efficiency=_clip(efficiency12 / 0.55),
            volatility=1.0 if expanding else 0.55, rejected=rejected_down, extended=pos40 <= 0.08,
            pullback=False, displacement=displacement_down, hard_veto=hard))

    if rejected_down and pos40 <= 0.30:
        candidates.append(_candidate("LIQUIDITY_REVERSAL", "UP", "MEAN_REVERSION", structure=1.0 if bull_structure else 0.35,
            acceptance=0.20, location=1.0, path=_clip((hi40 - last) / (3.0 * atr)),
            trigger_readiness=0.75 if lower_wick >= 0.20 else 0.35, efficiency=_clip(efficiency12 / 0.55),
            volatility=1.0 if 0.75 <= vol_ratio <= 1.60 else 0.45, rejected=True, extended=False,
            pullback=False, displacement=displacement_up,
            hard_veto=[] if lower_wick >= 0.20 else ["REJECTION_NOT_STRONG_ENOUGH"]))

    if rejected_up and pos40 >= 0.70:
        candidates.append(_candidate("LIQUIDITY_REVERSAL", "DOWN", "MEAN_REVERSION", structure=1.0 if bear_structure else 0.35,
            acceptance=0.20, location=1.0, path=_clip((last - lo40) / (3.0 * atr)),
            trigger_readiness=0.75 if upper_wick >= 0.20 else 0.35, efficiency=_clip(efficiency12 / 0.55),
            volatility=1.0 if 0.75 <= vol_ratio <= 1.60 else 0.45, rejected=True, extended=False,
            pullback=False, displacement=displacement_down,
            hard_veto=[] if upper_wick >= 0.20 else ["REJECTION_NOT_STRONG_ENOUGH"]))

    # 3. Professional hierarchy: hard veto first, then quality.
    eligible = [x for x in candidates if x["eligible"]]
    eligible.sort(key=lambda x: (x["quality"], x["path"], x["structure"]), reverse=True)
    candidates.sort(key=lambda x: (x["eligible"], x["quality"]), reverse=True)
    best = eligible[0] if eligible else None
    second = eligible[1] if len(eligible) > 1 else None
    ambiguity = bool(best and second and best["direction"] != second["direction"] and abs(float(best["quality"]) - float(second["quality"])) < 0.10)

    if ambiguity:
        direction, regime, opportunity, phase = "NEUTRAL", "TRANSITION", "WAIT_FOR_REPRICING", "AMBIGUOUS"
        auction_state = "COMPETING_HYPOTHESES"
    elif best:
        direction, regime, opportunity = best["direction"], best["regime"], best["name"]
        auction_state = {"BREAKOUT_CONTINUATION": "ACCEPTANCE_UP" if direction == "UP" else "ACCEPTANCE_DOWN",
                         "LIQUIDITY_REVERSAL": "FAILED_AUCTION_LOW" if direction == "UP" else "FAILED_AUCTION_HIGH"}.get(
                             opportunity, "DIRECTIONAL_AUCTION_UP" if direction == "UP" else "DIRECTIONAL_AUCTION_DOWN")
        if opportunity == "TREND_PULLBACK_CONTINUATION": phase = "PULLBACK" if best["pullback"] else "DEVELOPING"
        elif opportunity == "BREAKOUT_CONTINUATION": phase = "ACCEPTANCE" if expanding or best["displacement"] else "BREAKOUT"
        elif opportunity == "LIQUIDITY_REVERSAL": phase = "REJECTION"
        else: phase = "EXPANSION" if best["displacement"] else "DEVELOPING"
    else:
        direction, regime = "NEUTRAL", base_regime
        opportunity = "WAIT_FOR_RANGE_EDGE" if base_regime == "RANGE" else "WAIT_FOR_REPRICING"
        phase = "BALANCED" if base_regime == "RANGE" else "TRANSITION"
        auction_state = "BALANCED_AUCTION" if base_regime == "RANGE" else "UNCOMMITTED_AUCTION"

    location = "EDGE_LOW" if pos40 <= 0.20 else "EDGE_HIGH" if pos40 >= 0.80 else "MID_RANGE"
    opposing_space_atr = max((hi40 - last) / atr, 0.0) if direction == "UP" else max((last - lo40) / atr, 0.0) if direction == "DOWN" else 0.0
    space_ok = opposing_space_atr >= 1.0
    overextended = (direction == "UP" and pos40 >= 0.92) or (direction == "DOWN" and pos40 <= 0.08)

    counter: list[str] = []
    missing: list[str] = []
    invalidation: list[str] = []
    if ambiguity: counter.append("competing directional hypotheses are too close; no decisive edge")
    if direction == "UP":
        if ema20 < ema50 and not pullback_up: counter.append("short-term value structure opposes upside thesis")
        if regime == "TREND" and not bull_structure: counter.append("bullish swing sequence is not fully established")
        if rejected_up: counter.append("upside auction shows rejection")
        if not space_ok: counter.append("opposing liquidity is too close")
        if overextended: counter.append("price is materially extended")
    elif direction == "DOWN":
        if ema20 > ema50 and not pullback_down: counter.append("short-term value structure opposes downside thesis")
        if regime == "TREND" and not bear_structure: counter.append("bearish swing sequence is not fully established")
        if rejected_down: counter.append("downside auction shows rejection")
        if not space_ok: counter.append("opposing liquidity is too close")
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
    elif opportunity == "LIQUIDITY_REVERSAL":
        missing.append("rejection must hold and rotate back into value")
    elif opportunity == "WAIT_FOR_RANGE_EDGE":
        missing.append("meaningful range-edge interaction and rejection")
    elif opportunity == "WAIT_FOR_REPRICING":
        missing.append("clear directional commitment / repricing")

    if direction == "UP" and rejected_up and pos40 >= 0.80: invalidation.append("upside acceptance failed at a high-value area")
    if direction == "DOWN" and rejected_down and pos40 <= 0.20: invalidation.append("downside acceptance failed at a low-value area")
    if direction == "UP" and down_evidence >= up_evidence + 2: invalidation.append("independent downside evidence dominates")
    if direction == "DOWN" and up_evidence >= down_evidence + 2: invalidation.append("independent upside evidence dominates")

    # 4. E1 cross-check only after the independent E2 thesis exists.
    e1 = _e1_context(snapshot)
    e1_direction = _direction(e1.get("directional_pressure") or e1.get("direction"))
    e1_state = str(e1.get("market_state") or e1.get("state") or "UNRESOLVED").upper()
    e1_structure = str(e1.get("structure") or "UNRESOLVED").upper()
    if direction == "NEUTRAL" or e1_direction == "NEUTRAL": alignment = "INCONCLUSIVE"
    elif direction == e1_direction: alignment = "ALIGNED"
    else:
        alignment = "CONFLICT"
        counter.append("E1 directional evidence conflicts with the independent E2 thesis")

    best_quality = float(best["quality"]) if best else 0.0
    directional_strength = max(up_evidence, down_evidence) / 7.0
    counter_penalty = min(0.36, 0.06 * len(counter))
    missing_penalty = min(0.24, 0.05 * len(missing))
    confidence = _clip(0.55 * best_quality + 0.25 * directional_strength + 0.20 - counter_penalty - missing_penalty)
    opportunity_score = _clip(0.70 * best_quality + 0.30 * confidence)

    if invalidation:
        maturity, opportunity_state, quality = "INVALIDATED", "INVALIDATED", "REJECTED"
    elif direction == "NEUTRAL":
        maturity, opportunity_state, quality = "WAITING", "WAIT", "UNPROVEN"
    elif not best:
        maturity, opportunity_state, quality = "UNPROVEN", "WAIT", "REJECTED"
    elif best.get("hard_veto"):
        maturity, opportunity_state, quality = "BLOCKED", "WAIT", "BLOCKED"
    elif counter or missing:
        maturity, opportunity_state = "DEVELOPING", "DEVELOPING"
        quality = "STRONG_CONTEXT" if opportunity_score >= 0.70 else "DEVELOPING"
    else:
        maturity, opportunity_state = "MATURE_CONTEXT", "CONTEXT_READY"
        quality = "STRONG" if opportunity_score >= 0.78 else "DEVELOPING"

    if invalidation or best is None or best.get("hard_veto"): timing = "MISSED" if invalidation or overextended else "WAIT"
    elif direction == "NEUTRAL": timing = "WAIT"
    elif overextended: timing = "LATE"
    elif missing: timing = "READY_FOR_CONFIRMATION"
    else: timing = "DEVELOPING"

    opportunity_quality = "HIGH" if opportunity_score >= 0.78 and not counter and not missing else "MEDIUM" if opportunity_score >= 0.55 else "LOW"
    if invalidation or direction == "NEUTRAL" or best is None or best.get("hard_veto"):
        opportunity_decision, edge = ("NO_OPPORTUNITY", "NO_EDGE") if invalidation or best is None else ("WAIT", "NO_EDGE")
    elif counter or missing or overextended or not space_ok:
        opportunity_decision, edge = "WATCH", "EDGE_CONDITIONAL"
    elif opportunity_score >= 0.72:
        opportunity_decision, edge = "ACTIONABLE_BIAS", "EDGE_PRESENT"
    else:
        opportunity_decision, edge = "WATCH", "EDGE_CONDITIONAL"

    why_not_trade: list[str] = []
    if direction == "NEUTRAL": why_not_trade.append("no decisive directional opportunity is established")
    if ambiguity: why_not_trade.append("competing hypotheses are too close to justify commitment")
    if best and best.get("hard_veto"): why_not_trade.extend(f"hard veto: {x}" for x in best["hard_veto"])
    if overextended: why_not_trade.append("late location: price is too extended for immediate participation")
    if direction != "NEUTRAL" and not space_ok: why_not_trade.append("insufficient opposing space for a favorable path")
    why_not_trade.extend(f"missing: {x}" for x in missing)
    why_not_trade.extend(f"counter-evidence: {x}" for x in counter)
    why_not_trade.extend(f"invalidated: {x}" for x in invalidation)
    if not why_not_trade: why_not_trade.append("E2 provides opportunity context only; E9 must validate confirmation and trade economics")

    if direction == "UP": counterfactual = ["if supporting structure fails and downside evidence dominates, abandon the upside thesis"]
    elif direction == "DOWN": counterfactual = ["if opposing structure is reclaimed and upside evidence dominates, abandon the downside thesis"]
    else: counterfactual = ["if one side gains sustained acceptance and follow-through, replace neutrality with that directional thesis"]
    if overextended: counterfactual.append("if price returns to favorable location without losing structure, reassess the same directional idea")

    expected_path = {
        "TREND_PULLBACK_CONTINUATION": "impulse -> controlled pullback -> holding/rejection -> confirmation -> continuation",
        "TREND_CONTINUATION": "directional pressure -> acceptance/displacement -> confirmation -> follow-through",
        "BREAKOUT_CONTINUATION": "breakout -> acceptance beyond range -> expansion -> follow-through",
        "LIQUIDITY_REVERSAL": "liquidity sweep -> rejection holds -> return into value -> reversal follow-through",
    }.get(opportunity, "repricing -> clear directional commitment -> opportunity maturity")

    candidate_summary = [{
        "name": x["name"], "direction": x["direction"], "eligible": bool(x["eligible"]),
        "quality": round(float(x["quality"]), 4), "path": round(float(x["path"]), 4),
        "structure": round(float(x["structure"]), 4), "location": round(float(x["location"]), 4),
        "pullback": bool(x["pullback"]), "acceptance": round(float(x["acceptance"]), 4),
        "hard_veto": list(x["hard_veto"]),
    } for x in candidates[:8]]

    observations = [
        f"ema_gap_atr={ema_gap:.3f}", f"ema20_slope_atr={ema20_slope:.3f}", f"ema50_slope_atr={ema50_slope:.3f}",
        f"slope5_atr={slope5:.3f}", f"slope20_atr={slope20:.3f}", f"volatility_ratio={vol_ratio:.3f}",
        f"efficiency12={efficiency12:.3f}", f"up_evidence={up_evidence}/7", f"down_evidence={down_evidence}/7",
        f"position_40={pos40:.3f}", f"retrace_up={retrace_up:.3f}", f"retrace_down={retrace_down:.3f}",
        f"opposing_space_atr={opposing_space_atr:.3f}", f"accepted_up={accepted_up}", f"accepted_down={accepted_down}",
        f"rejected_up={rejected_up}", f"rejected_down={rejected_down}", f"displacement_up={displacement_up}",
        f"displacement_down={displacement_down}", f"pullback_up={pullback_up}", f"pullback_down={pullback_down}",
        f"candidate_count={len(candidates)}", f"eligible_count={len(eligible)}", f"best_candidate_quality={best_quality:.3f}",
        f"hypothesis_ambiguity={ambiguity}",
    ]

    decision_factors = [
        f"independent_regime={regime}", f"independent_direction={direction}", f"auction_state={auction_state}",
        f"opportunity={opportunity}", f"phase={phase}", f"location={location}", f"best_candidate_quality={best_quality:.3f}",
        f"candidate_count={len(candidates)}", f"eligible_count={len(eligible)}", f"alignment_with_e1={alignment}",
        f"timing={timing}", f"opportunity_score={opportunity_score:.3f}", f"decision={opportunity_decision}",
    ]

    thesis = f"Independent E2 thesis: {regime}/{direction} creates {opportunity} at {phase}; thesis is {maturity.lower()} and requires downstream confirmation."
    reasoning = {
        "question": QUESTION, "conclusion": thesis,
        "why_now": f"{auction_state}; {location}; opposing space={opposing_space_atr:.2f} ATR",
        "expected_path": expected_path, "required_evidence": list(dict.fromkeys(missing)),
        "invalidation_conditions": list(invalidation) or ["opposing structure becomes dominant", "auction invalidates the expected path"],
        "timing": timing, "opportunity_quality": opportunity_quality, "opportunity_decision": opportunity_decision,
        "edge_assessment": edge, "candidate_comparison": candidate_summary,
        "counter_evidence_count": len(counter), "counter_evidence": counter, "why_not_trade": why_not_trade,
        "counterfactual": counterfactual, "independent_thesis": True, "e1_used_as": "CROSS_CHECK_ONLY", "entry_authorized": False,
        "hard_veto_priority": True,
    }

    reason_codes: list[str] = []
    if invalidation: reason_codes.append("THESIS_INVALIDATED")
    if alignment == "CONFLICT": reason_codes.append("E1_E2_DIRECTION_CONFLICT")
    if ambiguity: reason_codes.append("COMPETING_HYPOTHESES")
    if best and best.get("hard_veto"): reason_codes.append("HARD_VETO_BLOCKED_OPPORTUNITY")
    if missing: reason_codes.append("MISSING_OPPORTUNITY_CONFIRMATION")
    if counter: reason_codes.append("COUNTER_EVIDENCE_PRESENT")
    if opportunity not in {"WAIT_FOR_REPRICING", "WAIT_FOR_RANGE_EDGE"} and not invalidation and direction != "NEUTRAL":
        reason_codes.append("OPPORTUNITY_THESIS_ESTABLISHED")
    if not reason_codes: reason_codes.append("NO_ACTIONABLE_OPPORTUNITY")

    return {
        "state": "OPPORTUNITY_ANALYSIS_COMPLETE", "architecture": ARCHITECTURE, "sub_engines_active": False,
        "reasoning_mode": "SINGLE_PROFESSIONAL_CORE", "question": QUESTION, "thesis": thesis,
        "regime": regime, "direction": direction, "phase": phase, "opportunity": opportunity,
        "opportunity_state": opportunity_state, "opportunity_maturity": maturity, "quality": quality,
        "opportunity_quality": opportunity_quality, "opportunity_score": round(opportunity_score, 4),
        "opportunity_decision": opportunity_decision, "edge_assessment": edge, "alignment_with_e1": alignment,
        "independence": "E2_FIRST_E1_CROSS_CHECK", "auction_state": auction_state,
        "auction_phase": "ACCEPTANCE" if "ACCEPTANCE" in auction_state else "REJECTION" if "FAILED_AUCTION" in auction_state else "BALANCE" if "BALANCED" in auction_state else "REPRICING" if direction != "NEUTRAL" else "TRANSITION",
        "acceptance_quality": "CONFIRMED" if accepted_up or accepted_down else "STRONG" if displacement_up or displacement_down else "UNPROVEN",
        "location_context": location, "regime_confidence": round(directional_strength, 4), "confidence": round(confidence, 4),
        "timing_state": timing, "decision_factors": decision_factors, "observations": observations,
        "evidence": [
            f"UP_EVIDENCE={up_evidence}/7", f"DOWN_EVIDENCE={down_evidence}/7", f"STRUCTURE_BULL={bull_structure}",
            f"STRUCTURE_BEAR={bear_structure}", f"ACCEPTANCE_UP={accepted_up}", f"ACCEPTANCE_DOWN={accepted_down}",
            f"REJECTION_UP={rejected_up}", f"REJECTION_DOWN={rejected_down}", f"EXPANSION={expanding}",
            f"COMPRESSION={compressed}", f"SPACE_OK={space_ok}", f"E1_STATE={e1_state}", f"E1_STRUCTURE={e1_structure}",
        ],
        "candidate_comparison": candidate_summary,
        "evidence_map": {
            "directional_pressure": direction, "location": location, "regime": regime, "auction_state": auction_state,
            "space_ok": space_ok, "overextended": overextended, "alignment_with_e1": alignment,
            "hypothesis_ambiguity": ambiguity, "hard_veto_active": bool(best and best.get("hard_veto")),
        },
        "counter_evidence": counter,
        "counter_evidence_severity": "THESIS_INVALIDATION" if invalidation else "MATERIAL" if counter else "NONE",
        "missing_evidence": missing, "invalidation_evidence": invalidation, "why_not_trade": why_not_trade,
        "counterfactual": counterfactual, "opposing_space_atr": round(opposing_space_atr, 4),
        "invalidation_distance_atr": round(((last - lo40) / atr) if direction == "UP" else ((hi40 - last) / atr) if direction == "DOWN" else 0.0, 4),
        "decision": None, "entry": None, "trigger": None, "risk": None, "gate": None,
        "trade_decision_authority": "E9_ONLY", "professional_reasoning": reasoning,
        "reason_codes": list(dict.fromkeys(reason_codes)),
    }
