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
    value = str(value or "NEUTRAL").upper().strip()
    if value in {"UP", "BULLISH", "BUY", "LONG"}:
        return "UP"
    if value in {"DOWN", "BEARISH", "SELL", "SHORT"}:
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
        "state": "UNAVAILABLE",
        "question": QUESTION,
        "thesis": "Insufficient closed-candle history; no opportunity thesis is formed.",
        "regime": "UNRESOLVED",
        "direction": "NEUTRAL",
        "phase": "UNRESOLVED",
        "opportunity": "NONE",
        "opportunity_state": "UNPROVEN",
        "opportunity_maturity": "UNPROVEN",
        "quality": "UNPROVEN",
        "alignment_with_e1": "INCONCLUSIVE",
        "independence": "E2_INDEPENDENT_THESIS_THEN_E1_CROSS_CHECK",
        "auction_state": "UNKNOWN",
        "location_context": "UNKNOWN",
        "regime_confidence": 0.0,
        "decision_factors": [],
        "observations": [],
        "evidence": [],
        "counter_evidence": ["insufficient closed-candle history"],
        "counter_evidence_severity": "THESIS_INVALIDATION",
        "missing_evidence": [f"{MIN_BARS} valid closed candles"],
        "invalidation_evidence": [],
        "confidence": 0.0,
        "decision": None,
        "entry": None,
        "trigger": None,
        "risk": None,
        "gate": None,
        "reason_codes": ["INSUFFICIENT_MARKET_DATA"],
    }


def analyze_e2(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Professional E2 opportunity/regime brain.

    E2 answers a different question from E1: not simply what the market is doing,
    but whether current auction behaviour offers a *tradable opportunity*.

    Thinking order:
      1. independently classify auction/regime;
      2. identify participant behaviour (acceptance, rejection, sweep, displacement);
      3. identify opportunity archetype and phase;
      4. measure location, available path and invalidation risk;
      5. actively search for counter-evidence;
      6. cross-check E1 only after the independent thesis exists.

    E2 never emits a trade decision or execution gate. E9 remains authoritative.
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

    # ---------- 1. AUCTION / REGIME ----------
    ema20 = _ema(c, 20)
    ema50 = _ema(c, 50)
    ema20_prev5 = _ema(c[:-5], 20)
    ema50_prev5 = _ema(c[:-5], 50)
    ema_gap = (ema20 - ema50) / atr
    ema20_slope = (ema20 - ema20_prev5) / atr
    ema50_slope = (ema50 - ema50_prev5) / atr

    ranges = [max(h[i] - l[i], 0.0) for i in range(len(bs))]
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
    width20 = max(hi20 - lo20, 1e-12)
    pos40 = max(0.0, min(1.0, (last - lo40) / width40))
    pos20 = max(0.0, min(1.0, (last - lo20) / width20))

    ph, pl = _pivots(bs)
    hh = len(ph) >= 2 and ph[-1] > ph[-2]
    lh = len(ph) >= 2 and ph[-1] < ph[-2]
    hl = len(pl) >= 2 and pl[-1] > pl[-2]
    ll = len(pl) >= 2 and pl[-1] < pl[-2]
    bull_structure = hh and hl
    bear_structure = lh and ll

    up_score = sum((ema_gap > 0.35, ema20_slope > 0.08, ema50_slope > -0.05,
                    slope5 > 0.20, slope20 > 0.45, bull_structure, efficiency12 >= 0.30))
    down_score = sum((ema_gap < -0.35, ema20_slope < -0.08, ema50_slope < 0.05,
                      slope5 < -0.20, slope20 < -0.45, bear_structure, efficiency12 >= 0.30))

    compressed = vol_ratio < 0.72
    expanding = vol_ratio > 1.28
    balanced = abs(slope20) < 0.65 and efficiency12 < 0.30 and width40 / atr < 8.5

    # ---------- 2. PARTICIPANT BEHAVIOUR ----------
    span = max(h[-1] - l[-1], 1e-12)
    body_ratio = abs(last - o[-1]) / span
    close_pos = (last - l[-1]) / span
    upper_wick = (h[-1] - max(o[-1], last)) / span
    lower_wick = (min(o[-1], last) - l[-1]) / span

    broke_up = last > hi20
    broke_down = last < lo20
    swept_up = h[-1] > hi20 and last <= hi20
    swept_down = l[-1] < lo20 and last >= lo20

    accepted_up = broke_up and close_pos >= 0.65 and body_ratio >= 0.45
    accepted_down = broke_down and close_pos <= 0.35 and body_ratio >= 0.45
    rejected_up = swept_up and close_pos <= 0.45 and upper_wick >= 0.20
    rejected_down = swept_down and close_pos >= 0.55 and lower_wick >= 0.20

    displacement_up = body_ratio >= 0.60 and close_pos >= 0.75 and span >= 1.25 * avg20_range
    displacement_down = body_ratio >= 0.60 and close_pos <= 0.25 and span >= 1.25 * avg20_range

    # ---------- 3. IMPULSE / PULLBACK STATE ----------
    up_impulse = c[-6] > c[-13] and (c[-6] - c[-13]) / atr >= 0.80
    down_impulse = c[-6] < c[-13] and (c[-13] - c[-6]) / atr >= 0.80
    pullback_up = up_impulse and last < c[-6] and last > lo20 and ema20 >= ema50
    pullback_down = down_impulse and last > c[-6] and last < hi20 and ema20 <= ema50

    # ---------- 4. INDEPENDENT REGIME THESIS ----------
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

    # ---------- 5. OPPORTUNITY, NOT SIGNAL ----------
    if regime == "TREND" and direction == "UP":
        if pullback_up:
            opportunity, phase = "TREND_PULLBACK_CONTINUATION", "PULLBACK"
        elif displacement_up:
            opportunity, phase = "TREND_CONTINUATION", "EXPANSION"
        else:
            opportunity, phase = "TREND_CONTINUATION", "DEVELOPING"
    elif regime == "TREND" and direction == "DOWN":
        if pullback_down:
            opportunity, phase = "TREND_PULLBACK_CONTINUATION", "PULLBACK"
        elif displacement_down:
            opportunity, phase = "TREND_CONTINUATION", "EXPANSION"
        else:
            opportunity, phase = "TREND_CONTINUATION", "DEVELOPING"
    elif regime == "BREAKOUT":
        opportunity = "BREAKOUT_CONTINUATION"
        phase = "ACCEPTANCE"
    elif regime == "MEAN_REVERSION":
        opportunity = "LIQUIDITY_REVERSAL"
        phase = "REJECTION"
    elif regime == "RANGE" and pos40 <= 0.20 and rejected_down:
        opportunity, direction, phase = "RANGE_ROTATION_UP", "UP", "EDGE_REJECTION"
    elif regime == "RANGE" and pos40 >= 0.80 and rejected_up:
        opportunity, direction, phase = "RANGE_ROTATION_DOWN", "DOWN", "EDGE_REJECTION"
    elif regime == "RANGE":
        opportunity, phase = "WAIT_FOR_RANGE_EDGE", "BALANCED"
    else:
        opportunity, phase = "WAIT_FOR_REPRICING", "TRANSITION"

    # ---------- 6. LOCATION / PATH / INVALIDATION ----------
    location = "EDGE_LOW" if pos40 <= 0.20 else "EDGE_HIGH" if pos40 >= 0.80 else "MID_RANGE"
    if direction == "UP":
        opposing_space_atr = max((hi40 - last) / atr, 0.0)
        invalidation_distance_atr = max((last - lo40) / atr, 0.0)
    elif direction == "DOWN":
        opposing_space_atr = max((last - lo40) / atr, 0.0)
        invalidation_distance_atr = max((hi40 - last) / atr, 0.0)
    else:
        opposing_space_atr = 0.0
        invalidation_distance_atr = 0.0

    space_ok = opposing_space_atr >= 1.0
    overextended = (direction == "UP" and pos40 >= 0.92) or (direction == "DOWN" and pos40 <= 0.08)

    # ---------- 7. COUNTER-EVIDENCE / THESIS INVALIDATION ----------
    counter: list[str] = []
    missing: list[str] = []
    invalidation: list[str] = []

    if direction == "UP":
        if ema20 < ema50 and not pullback_up:
            counter.append("short-term moving-average structure opposes upside thesis")
        if not bull_structure and regime == "TREND":
            counter.append("swing structure does not fully confirm upside trend")
        if rejected_up:
            counter.append("upside auction shows rejection")
        if not space_ok:
            counter.append("opposing liquidity is too close for attractive opportunity space")
        if overextended:
            counter.append("price is materially extended from value")
    elif direction == "DOWN":
        if ema20 > ema50 and not pullback_down:
            counter.append("short-term moving-average structure opposes downside thesis")
        if not bear_structure and regime == "TREND":
            counter.append("swing structure does not fully confirm downside trend")
        if rejected_down:
            counter.append("downside auction shows rejection")
        if not space_ok:
            counter.append("opposing liquidity is too close for attractive opportunity space")
        if overextended:
            counter.append("price is materially extended from value")

    if regime == "TREND" and phase == "PULLBACK":
        missing.append("follow-through after pullback")
    if regime == "BREAKOUT" and not expanding:
        missing.append("volatility expansion after breakout")
    if regime == "RANGE" and phase == "BALANCED":
        missing.append("meaningful range-edge interaction")
    if regime == "TRANSITION":
        missing.append("directional repricing / commitment")
    if regime == "MEAN_REVERSION" and not (rejected_up or rejected_down):
        missing.append("confirmed liquidity rejection")

    # Hard thesis invalidation is different from ordinary missing evidence.
    if direction == "UP" and rejected_up and pos40 >= 0.80:
        invalidation.append("upside acceptance failed at a high-value area")
    if direction == "DOWN" and rejected_down and pos40 <= 0.20:
        invalidation.append("downside acceptance failed at a low-value area")
    if direction == "UP" and down_score >= up_score + 2:
        invalidation.append("independent downside evidence dominates")
    if direction == "DOWN" and up_score >= down_score + 2:
        invalidation.append("independent upside evidence dominates")

    # ---------- 8. E1 CROSS-CHECK AFTER E2 THESIS ----------
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

    # ---------- 9. MATURITY / QUALITY ----------
    directional_strength = max(up_score, down_score) / 7.0
    auction_quality = 1.0 if auction_state not in {"NO_EDGE", "UNCOMMITTED_AUCTION"} else 0.45
    evidence_penalty = min(0.45, 0.10 * len(counter))
    missing_penalty = min(0.25, 0.08 * len(missing))
    alignment_bonus = 0.10 if alignment == "ALIGNED" else -0.10 if alignment == "CONFLICT" else 0.0
    confidence = max(0.0, min(1.0, 0.45 * directional_strength + 0.30 * auction_quality + 0.25 + alignment_bonus - evidence_penalty - missing_penalty))

    if invalidation:
        maturity = "INVALIDATED"
        opportunity_state = "INVALIDATED"
        quality = "REJECTED"
    elif direction == "NEUTRAL":
        maturity = "UNPROVEN" if not missing else "WAITING"
        opportunity_state = "UNPROVEN"
        quality = "UNPROVEN"
    elif opportunity in {"WAIT_FOR_REPRICING", "WAIT_FOR_RANGE_EDGE"}:
        maturity = "WAITING"
        opportunity_state = "DEVELOPING"
        quality = "WEAK" if confidence < 0.65 else "DEVELOPING"
    elif counter or missing:
        maturity = "DEVELOPING"
        opportunity_state = "DEVELOPING"
        quality = "DEVELOPING" if confidence >= 0.60 else "WEAK"
    else:
        maturity = "MATURE_CONTEXT"
        opportunity_state = "CONTEXT_READY"
        quality = "STRONG" if confidence >= 0.78 else "DEVELOPING"

    reason_codes: list[str] = []
    if invalidation:
        reason_codes.append("THESIS_INVALIDATED")
    if alignment == "CONFLICT":
        reason_codes.append("E1_E2_DIRECTION_CONFLICT")
    if missing:
        reason_codes.append("MISSING_OPPORTUNITY_CONFIRMATION")
    if counter:
        reason_codes.append("COUNTER_EVIDENCE_PRESENT")
    if opportunity not in {"NONE", "WAIT_FOR_REPRICING", "WAIT_FOR_RANGE_EDGE"} and not invalidation:
        reason_codes.append("OPPORTUNITY_THESIS_ESTABLISHED")
    if not reason_codes:
        reason_codes.append("NO_ACTIONABLE_OPPORTUNITY")

    observations = [
        f"ema_gap_atr={ema_gap:.3f}",
        f"ema20_slope_atr={ema20_slope:.3f}",
        f"ema50_slope_atr={ema50_slope:.3f}",
        f"slope5_atr={slope5:.3f}",
        f"slope20_atr={slope20:.3f}",
        f"slope40_atr={slope40:.3f}",
        f"volatility_ratio={vol_ratio:.3f}",
        f"efficiency12={efficiency12:.3f}",
        f"up_evidence={up_score}/7",
        f"down_evidence={down_score}/7",
        f"position_40={pos40:.3f}",
        f"position_20={pos20:.3f}",
        f"opposing_space_atr={opposing_space_atr:.3f}",
        f"invalidation_distance_atr={invalidation_distance_atr:.3f}",
        f"accepted_up={accepted_up}",
        f"accepted_down={accepted_down}",
        f"rejected_up={rejected_up}",
        f"rejected_down={rejected_down}",
        f"displacement_up={displacement_up}",
        f"displacement_down={displacement_down}",
        f"pullback_up={pullback_up}",
        f"pullback_down={pullback_down}",
    ]

    decision_factors = [
        f"independent_regime={regime}",
        f"independent_direction={direction}",
        f"auction_state={auction_state}",
        f"opportunity={opportunity}",
        f"phase={phase}",
        f"location={location}",
        f"alignment_with_e1={alignment}",
        f"confidence={confidence:.3f}",
    ]

    thesis = (
        f"E2 independently sees {regime} / {direction}; {opportunity} is {phase}. "
        f"The thesis is {maturity.lower()} and must be confirmed downstream before execution."
    )

    return {
        "state": "OPPORTUNITY_ANALYSIS_COMPLETE",
        "question": QUESTION,
        "thesis": thesis,
        "regime": regime,
        "direction": direction,
        "phase": phase,
        "opportunity": opportunity,
        "opportunity_state": opportunity_state,
        "opportunity_maturity": maturity,
        "quality": quality,
        "alignment_with_e1": alignment,
        "independence": "E2_INDEPENDENT_THESIS_THEN_E1_CROSS_CHECK",
        "auction_state": auction_state,
        "location_context": location,
        "regime_confidence": round(directional_strength, 4),
        "confidence": round(confidence, 4),
        "decision_factors": decision_factors,
        "observations": observations,
        "evidence": [
            f"UP_EVIDENCE={up_score}/7",
            f"DOWN_EVIDENCE={down_score}/7",
            f"STRUCTURE_BULL={bull_structure}",
            f"STRUCTURE_BEAR={bear_structure}",
            f"ACCEPTANCE_UP={accepted_up}",
            f"ACCEPTANCE_DOWN={accepted_down}",
            f"REJECTION_UP={rejected_up}",
            f"REJECTION_DOWN={rejected_down}",
            f"EXPANSION={expanding}",
            f"COMPRESSION={compressed}",
            f"SPACE_OK={space_ok}",
            f"E1_STATE={e1_state}",
            f"E1_STRUCTURE={e1_structure}",
        ],
        "counter_evidence": counter,
        "counter_evidence_severity": "THESIS_INVALIDATION" if invalidation else "MATERIAL" if counter else "NONE",
        "missing_evidence": missing,
        "invalidation_evidence": invalidation,
        "opposing_space_atr": round(opposing_space_atr, 4),
        "invalidation_distance_atr": round(invalidation_distance_atr, 4),
        "decision": None,
        "entry": None,
        "trigger": None,
        "risk": None,
        "gate": None,
        "reason_codes": list(dict.fromkeys(reason_codes)),
    }
