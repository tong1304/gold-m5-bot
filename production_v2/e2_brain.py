from __future__ import annotations

from statistics import mean
from typing import Any

QUESTION = "What opportunity is the market offering right now?"
MIN_BARS = 50


def _bars(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    bars = snapshot.get("bars") or []
    return [b for b in bars if isinstance(b, dict) and all(k in b for k in ("open", "high", "low", "close"))]


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    values: list[float] = []
    previous = None
    for b in bars[-period:]:
        h, l, c = float(b["high"]), float(b["low"]), float(b["close"])
        values.append(h - l if previous is None else max(h - l, abs(h - previous), abs(l - previous)))
        previous = c
    return mean(values) if values else 0.0


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    current = values[0]
    for value in values[1:]:
        current = alpha * value + (1.0 - alpha) * current
    return current


def _pivots(bars: list[dict[str, Any]], wing: int = 2) -> tuple[list[float], list[float]]:
    highs: list[float] = []
    lows: list[float] = []
    for i in range(wing, len(bars) - wing):
        window = bars[i - wing:i + wing + 1]
        h, l = float(bars[i]["high"]), float(bars[i]["low"])
        if h >= max(float(x["high"]) for x in window): highs.append(h)
        if l <= min(float(x["low"]) for x in window): lows.append(l)
    return highs, lows


def _direction(value: Any) -> str:
    value = str(value or "NEUTRAL").upper().strip()
    if value in {"UP", "BULLISH", "BUY", "LONG"}: return "UP"
    if value in {"DOWN", "BEARISH", "SELL", "SHORT"}: return "DOWN"
    return "NEUTRAL"


def _e1_context(snapshot: dict[str, Any]) -> dict[str, Any]:
    value = snapshot.get("E1_result") or {}
    return value if isinstance(value, dict) else {}


def _base_unavailable() -> dict[str, Any]:
    return {
        "state": "UNAVAILABLE", "question": QUESTION,
        "thesis": "Insufficient closed-candle history; opportunity is unproven.",
        "regime": "UNRESOLVED", "direction": "NEUTRAL", "phase": "UNRESOLVED",
        "opportunity": "NONE", "opportunity_state": "UNPROVEN", "opportunity_maturity": "UNPROVEN",
        "quality": "UNPROVEN", "alignment_with_e1": "INCONCLUSIVE",
        "independence": "E2_FIRST_E1_CROSS_CHECK", "auction_state": "UNKNOWN",
        "location_context": "UNKNOWN", "regime_confidence": 0.0,
        "decision_factors": [], "observations": [], "evidence": [],
        "counter_evidence": ["insufficient closed-candle history"],
        "counter_evidence_severity": "THESIS_INVALIDATION", "missing_evidence": [f"{MIN_BARS} valid closed candles"],
        "confidence": 0.0, "decision": None, "entry": None, "trigger": None, "risk": None, "gate": None,
        "reason_codes": ["INSUFFICIENT_MARKET_DATA"],
    }


def analyze_e2(snapshot: dict[str, Any]) -> dict[str, Any]:
    """E2 professional opportunity/regime brain.

    E2 answers the opportunity question independently. E1 is only a qualitative
    cross-check. E2 never consumes an upstream decision, gate, or score and never
    issues an execution instruction. E9 remains the sole trade authority.
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
    ema_gap = (ema20 - ema50) / atr
    slope5 = (c[-1] - c[-6]) / atr
    slope20 = (c[-1] - c[-21]) / atr

    ranges = [max(h[i] - l[i], 0.0) for i in range(len(bs))]
    avg20 = max(mean(ranges[-20:]), 1e-12)
    avg6 = mean(ranges[-6:])
    volatility_ratio = avg6 / avg20
    span = max(h[-1] - l[-1], 1e-12)
    body_ratio = abs(last - o[-1]) / span
    close_pos = (last - l[-1]) / span

    hi20, lo20 = max(h[-21:-1]), min(l[-21:-1])
    hi40, lo40 = max(h[-41:-1]), min(l[-41:-1])
    width40 = max(hi40 - lo40, 1e-12)
    position40 = max(0.0, min(1.0, (last - lo40) / width40))

    broke_up, broke_down = last > hi20, last < lo20
    swept_up = h[-1] > hi20 and last <= hi20
    swept_down = l[-1] < lo20 and last >= lo20
    accepted_up = broke_up and close_pos >= 0.65
    accepted_down = broke_down and close_pos <= 0.35

    travelled = max(sum(ranges[-12:]), 1e-12)
    efficiency = abs(c[-1] - c[-13]) / travelled
    ph, pl = _pivots(bs)
    hh = len(ph) > 1 and ph[-1] > ph[-2]
    lh = len(ph) > 1 and ph[-1] < ph[-2]
    hl = len(pl) > 1 and pl[-1] > pl[-2]
    ll = len(pl) > 1 and pl[-1] < pl[-2]
    bull_structure, bear_structure = hh and hl, lh and ll

    compressed = volatility_ratio < 0.70
    expansion = volatility_ratio > 1.30 or (span > 1.35 * avg20 and body_ratio >= 0.60)
    directional_up = body_ratio >= 0.55 and close_pos >= 0.70
    directional_down = body_ratio >= 0.55 and close_pos <= 0.30

    trend_up_score = sum((ema_gap > 0.35, slope5 > 0.20, slope20 > 0.50, bull_structure, efficiency >= 0.30))
    trend_down_score = sum((ema_gap < -0.35, slope5 < -0.20, slope20 < -0.50, bear_structure, efficiency >= 0.30))

    breakout_up = broke_up and last > ema20 and (expansion or directional_up)
    breakout_down = broke_down and last < ema20 and (expansion or directional_down)
    failed_auction_up = swept_up and close_pos <= 0.45
    failed_auction_down = swept_down and close_pos >= 0.55
    reversion_up = position40 <= 0.20 and failed_auction_down
    reversion_down = position40 >= 0.80 and failed_auction_up
    balanced = (
        abs(ema_gap) < 0.55 and abs(slope20) < 0.65 and efficiency < 0.30
        and 0.15 < position40 < 0.85 and not (accepted_up or accepted_down)
        and width40 / atr < 8.0
    )
    range_edge = position40 <= 0.20 or position40 >= 0.80

    # Regime is determined from raw market evidence first; E1 is deliberately not used here.
    if breakout_up and breakout_down:
        regime, direction = "TRANSITION", "NEUTRAL"
    elif breakout_up:
        regime, direction = "BREAKOUT", "UP"
    elif breakout_down:
        regime, direction = "BREAKOUT", "DOWN"
    elif trend_up_score >= 4 and trend_up_score > trend_down_score:
        regime, direction = "TREND", "UP"
    elif trend_down_score >= 4 and trend_down_score > trend_up_score:
        regime, direction = "TREND", "DOWN"
    elif reversion_up and not reversion_down:
        regime, direction = "MEAN_REVERSION", "UP"
    elif reversion_down and not reversion_up:
        regime, direction = "MEAN_REVERSION", "DOWN"
    elif balanced or (compressed and abs(slope20) < 0.80 and abs(ema_gap) < 0.75 and efficiency < 0.40):
        regime, direction = "RANGE", "NEUTRAL"
    elif abs(ema_gap) < 0.35 or abs(trend_up_score - trend_down_score) <= 1:
        regime, direction = "TRANSITION", "NEUTRAL"
    else:
        regime, direction = "RANGE", "NEUTRAL"

    # Auction interpretation: what participants are accepting/rejecting now.
    if accepted_up and not accepted_down:
        auction_state = "ACCEPTING_UP"
    elif accepted_down and not accepted_up:
        auction_state = "ACCEPTING_DOWN"
    elif failed_auction_up and not failed_auction_down:
        auction_state = "FAILED_AUCTION_UP"
    elif failed_auction_down and not failed_auction_up:
        auction_state = "FAILED_AUCTION_DOWN"
    elif regime == "TRANSITION":
        auction_state = "REPRICING"
    elif regime == "RANGE":
        auction_state = "BALANCED"
    elif direction == "UP":
        auction_state = "REPRICING_UP"
    elif direction == "DOWN":
        auction_state = "REPRICING_DOWN"
    else:
        auction_state = "UNKNOWN"

    location_context = "EDGE_LOW" if position40 <= 0.20 else "EDGE_HIGH" if position40 >= 0.80 else "MID_RANGE"

    if regime == "BREAKOUT":
        phase = "EXPANSION" if expansion or accepted_up or accepted_down else "BREAKOUT_DEVELOPING"
        opportunity = "BREAKOUT_CONTINUATION"
    elif regime == "TREND":
        phase = "EXPANSION" if expansion and efficiency >= 0.30 else "COMPRESSION" if compressed else "BALANCED"
        opportunity = "TREND_CONTINUATION"
    elif regime == "MEAN_REVERSION":
        phase, opportunity = "REJECTION", "MEAN_REVERSION"
    elif regime == "RANGE":
        phase = "COMPRESSION" if compressed else "BALANCED"
        opportunity = "RANGE_ROTATION" if range_edge or failed_auction_up or failed_auction_down else "WAIT_FOR_RANGE_EDGE"
    else:
        phase, opportunity = "TRANSITION", "WAIT_FOR_REPRICING"

    # E1 cross-check happens only after E2 has formed its own thesis.
    e1 = _e1_context(snapshot)
    e1_direction = _direction(e1.get("directional_pressure") or e1.get("direction"))
    e1_state = str(e1.get("market_state") or e1.get("state") or "UNRESOLVED").upper()
    e1_structure = str(e1.get("structure") or "UNRESOLVED").upper()
    alignment = (
        "ALIGNED" if direction != "NEUTRAL" and direction == e1_direction
        else "CONFLICT" if direction != "NEUTRAL" and e1_direction != "NEUTRAL"
        else "INCONCLUSIVE"
    )

    # Counter-evidence is graded. It weakens a thesis before it invalidates it.
    counter: list[str] = []
    missing: list[str] = []
    if regime == "TREND" and efficiency < 0.30:
        counter.append("directional movement lacks efficient follow-through")
    if regime == "TREND" and not (bull_structure if direction == "UP" else bear_structure):
        counter.append("swing structure does not fully confirm trend")
    if regime == "BREAKOUT" and not expansion:
        counter.append("breakout lacks clear volatility expansion")
    if regime == "BREAKOUT" and not (accepted_up or accepted_down):
        missing.append("acceptance beyond the broken level")
    if regime == "MEAN_REVERSION" and not (failed_auction_up or failed_auction_down):
        counter.append("rejection is not objectively proven")
    if regime == "RANGE" and not range_edge and not (failed_auction_up or failed_auction_down):
        counter.append("price is in the middle of balance; rotation has poor location")
        missing.append("range edge or rejection")
    if regime == "TRANSITION":
        missing.append("stable regime commitment")
    if alignment == "CONFLICT":
        counter.append(f"E1 conflicts with independent E2 direction={direction}")

    # Material invalidation is reserved for evidence that destroys the actual E2 thesis.
    invalidation: list[str] = []
    if regime == "BREAKOUT" and direction == "UP" and last < hi20 and failed_auction_up:
        invalidation.append("upside breakout failed and returned below the broken level")
    if regime == "BREAKOUT" and direction == "DOWN" and last > lo20 and failed_auction_down:
        invalidation.append("downside breakout failed and returned above the broken level")
    if regime == "MEAN_REVERSION" and direction == "UP" and last < lo40:
        invalidation.append("downside repricing overwhelmed the expected reversal zone")
    if regime == "MEAN_REVERSION" and direction == "DOWN" and last > hi40:
        invalidation.append("upside repricing overwhelmed the expected reversal zone")

    counter_severity = "THESIS_INVALIDATION" if invalidation else "MATERIAL" if len(counter) >= 2 else "MINOR" if counter else "NONE"

    # Evidence weighting is qualitative, not a trading score. It estimates maturity only.
    structure_strength = 1.0 if (bull_structure or bear_structure) else 0.0
    regime_clarity = {"BREAKOUT": 1.0, "TREND": 0.85, "MEAN_REVERSION": 0.70, "RANGE": 0.60, "TRANSITION": 0.25}[regime]
    acceptance = 1.0 if (accepted_up or accepted_down) else 0.0
    rejection = 1.0 if (failed_auction_up or failed_auction_down) else 0.0
    directional_quality = min(efficiency / 0.50, 1.0)
    confidence = (
        0.20
        + 0.20 * directional_quality
        + 0.20 * structure_strength
        + 0.25 * regime_clarity
        + 0.15 * max(acceptance, rejection, 1.0 if expansion else 0.0)
    )
    if alignment == "ALIGNED": confidence += 0.08
    elif alignment == "CONFLICT": confidence -= 0.10
    if counter_severity == "MATERIAL": confidence -= 0.12
    if counter_severity == "THESIS_INVALIDATION": confidence -= 0.25
    confidence = max(0.15, min(0.95, confidence))

    if invalidation:
        maturity = "INVALIDATED"
        opportunity_state, quality = "REJECTED", "LOW"
    elif regime == "TRANSITION":
        maturity = "FORMING"
        opportunity_state, quality = "WAIT", "LOW"
    elif opportunity == "WAIT_FOR_RANGE_EDGE":
        maturity = "FORMING"
        opportunity_state, quality = "WAIT", "LOW"
    elif missing:
        maturity = "DEVELOPING"
        opportunity_state = "WAIT_FOR_CONFIRMATION"
        quality = "MEDIUM" if confidence >= 0.55 else "LOW"
    elif counter_severity == "MATERIAL":
        maturity = "DEVELOPING"
        opportunity_state, quality = "CAUTION", "MEDIUM" if confidence >= 0.55 else "LOW"
    elif regime in {"BREAKOUT", "TREND", "MEAN_REVERSION"} and confidence >= 0.68:
        maturity = "MATURE"
        opportunity_state, quality = "ACTIONABLE_CONTEXT", "HIGH"
    else:
        maturity = "DEVELOPING"
        opportunity_state, quality = "DEVELOPING", "MEDIUM" if confidence >= 0.55 else "LOW"

    factors = [
        f"regime={regime}", f"auction={auction_state}", f"location={location_context}",
        f"efficiency={efficiency:.3f}", f"volatility_ratio={volatility_ratio:.3f}",
        f"counter_evidence={counter_severity}", f"maturity={maturity}",
    ]
    if regime == "TREND": factors.insert(0, f"Trend continuation has independent directional evidence={direction}")
    elif regime == "BREAKOUT": factors.insert(0, "Breakout opportunity requires acceptance, not merely a level breach")
    elif regime == "MEAN_REVERSION": factors.insert(0, "Reversal requires failed auction plus advantageous location")
    elif regime == "RANGE": factors.insert(0, "Range rotation is attractive at an edge, not in the middle")
    else: factors.insert(0, "Stable repricing commitment is required before directional opportunity")

    evidence = [
        f"ema_gap_atr={ema_gap:.3f}", f"slope5_atr={slope5:.3f}", f"slope20_atr={slope20:.3f}",
        f"trend_up_evidence={trend_up_score}/5", f"trend_down_evidence={trend_down_score}/5",
        f"volatility_ratio={volatility_ratio:.3f}", f"efficiency={efficiency:.3f}",
        f"structure={'BULLISH' if bull_structure else 'BEARISH' if bear_structure else 'MIXED'}",
        f"position40={position40:.3f}", f"range_width_atr={width40 / atr:.3f}",
        f"expansion={expansion}", f"balanced={balanced}", f"breakout_up={breakout_up}", f"breakout_down={breakout_down}",
        f"accepted_up={accepted_up}", f"accepted_down={accepted_down}",
        f"failed_auction_up={failed_auction_up}", f"failed_auction_down={failed_auction_down}",
        f"e1_direction={e1_direction}", f"e1_state={e1_state}", f"e1_structure={e1_structure}",
        f"e1_e2_alignment={alignment}",
    ]
    observations = [
        f"state={regime}", f"thesis={regime}:{opportunity}", f"direction={direction}",
        f"phase={phase}", f"opportunity={opportunity}", f"opportunity_state={opportunity_state}",
        f"opportunity_maturity={maturity}", f"quality={quality}", f"auction_state={auction_state}",
        f"location_context={location_context}", f"counter_evidence_severity={counter_severity}",
    ]

    reasons: list[str] = []
    if counter:
        reasons.append("COUNTER_EVIDENCE_PRESENT")
    if missing:
        reasons.append("MISSING_OPPORTUNITY_CONFIRMATION")
    if invalidation:
        reasons.append("E2_THESIS_INVALIDATED")
    if alignment == "CONFLICT":
        reasons.append("E1_E2_DIRECTION_CONFLICT")
    if not reasons:
        reasons.append("OPPORTUNITY_THESIS_ESTABLISHED")

    return {
        "state": regime,
        "question": QUESTION,
        "thesis": f"{regime} / {opportunity}",
        "regime": regime,
        "direction": direction,
        "phase": phase,
        "opportunity": opportunity,
        "opportunity_state": opportunity_state,
        "opportunity_maturity": maturity,
        "quality": quality,
        "alignment_with_e1": alignment,
        "independence": "E2_FIRST_E1_CROSS_CHECK",
        "auction_state": auction_state,
        "location_context": location_context,
        "regime_confidence": round(confidence, 3),
        "decision_factors": factors,
        "observations": observations,
        "evidence": evidence,
        "counter_evidence": counter,
        "counter_evidence_severity": counter_severity,
        "invalidation_evidence": invalidation,
        "missing_evidence": missing,
        "confidence": round(confidence, 3),
        "decision": None,
        "entry": None,
        "trigger": None,
        "risk": None,
        "gate": None,
        "reason_codes": reasons,
    }
