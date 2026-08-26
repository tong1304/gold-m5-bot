from __future__ import annotations

from statistics import mean
from typing import Any

QUESTION = "What opportunity is the market offering right now?"
MIN_BARS = 60


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
    out = values[0]
    for value in values[1:]:
        out = alpha * value + (1.0 - alpha) * out
    return out


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
        h = float(bars[i]["high"])
        l = float(bars[i]["low"])
        window = bars[i - wing:i + wing + 1]
        if h >= max(float(x["high"]) for x in window):
            highs.append(h)
        if l <= min(float(x["low"]) for x in window):
            lows.append(l)
    return highs, lows


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
        "counter_evidence_severity": "THESIS_INVALIDATION",
        "missing_evidence": [f"{MIN_BARS} valid closed candles"],
        "invalidation_evidence": [], "confidence": 0.0,
        "decision": None, "entry": None, "trigger": None, "risk": None, "gate": None,
        "reason_codes": ["INSUFFICIENT_MARKET_DATA"],
    }


def analyze_e2(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Independent professional opportunity analyst.

    E2 forms its own market thesis from price/volatility/structure first, then
    cross-checks E1. It does not inherit E1's decision, score, gate or direction.
    E2 describes opportunity maturity; E9 remains the only trade authority.
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

    # -------------------- MARKET AUCTION --------------------
    ema20 = _ema(c, 20)
    ema50 = _ema(c, 50)
    ema20_prev5 = _ema(c[:-5], 20)
    ema50_prev5 = _ema(c[:-5], 50)
    ema_gap = (ema20 - ema50) / atr
    ema20_slope = (ema20 - ema20_prev5) / atr
    ema50_slope = (ema50 - ema50_prev5) / atr

    range_values = [max(h[i] - l[i], 0.0) for i in range(len(bs))]
    avg20_range = max(mean(range_values[-20:]), 1e-12)
    avg5_range = mean(range_values[-5:])
    vol_ratio = avg5_range / avg20_range

    span = max(h[-1] - l[-1], 1e-12)
    body = abs(last - o[-1])
    body_ratio = body / span
    close_pos = (last - l[-1]) / span
    upper_wick = h[-1] - max(o[-1], last)
    lower_wick = min(o[-1], last) - l[-1]

    slope5 = (c[-1] - c[-6]) / atr
    slope20 = (c[-1] - c[-21]) / atr
    slope40 = (c[-1] - c[-41]) / atr
    travelled12 = max(sum(range_values[-12:]), 1e-12)
    efficiency12 = abs(c[-1] - c[-13]) / travelled12

    # Multi-window location prevents a single lookback from defining value.
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
    bull_structure = hh and hl
    bear_structure = lh and ll

    # -------------------- PARTICIPANT BEHAVIOUR --------------------
    broke_up = last > hi20
    broke_down = last < lo20
    swept_up = h[-1] > hi20 and last <= hi20
    swept_down = l[-1] < lo20 and last >= lo20

    accepted_up = broke_up and close_pos >= 0.65 and body_ratio >= 0.45
    accepted_down = broke_down and close_pos <= 0.35 and body_ratio >= 0.45
    failed_up = swept_up and close_pos <= 0.45
    failed_down = swept_down and close_pos >= 0.55

    displacement_up = body_ratio >= 0.60 and close_pos >= 0.75 and span >= 1.25 * avg20_range
    displacement_down = body_ratio >= 0.60 and close_pos <= 0.25 and span >= 1.25 * avg20_range

    # Detect pullback: directional move existed, current bar retraces without destroying structure.
    recent_up_impulse = c[-6] > c[-13] and (c[-6] - c[-13]) / atr >= 0.80
    recent_down_impulse = c[-6] < c[-13] and (c[-13] - c[-6]) / atr >= 0.80
    pullback_up = recent_up_impulse and last < c[-6] and last > lo20 and ema20 >= ema50
    pullback_down = recent_down_impulse and last > c[-6] and last < hi20 and ema20 <= ema50

    # A true compression is useful only if price is not already in random transition.
    compressed = vol_ratio < 0.72
    expanding = vol_ratio > 1.28 or displacement_up or displacement_down
    balanced = abs(slope20) < 0.65 and efficiency12 < 0.30 and width40 / atr < 8.5

    # -------------------- INDEPENDENT E2 REGIME --------------------
    up_evidence = sum((ema_gap > 0.35, ema20_slope > 0.08, slope5 > 0.20,
                       slope20 > 0.45, bull_structure, efficiency12 >= 0.30))
    down_evidence = sum((ema_gap < -0.35, ema20_slope < -0.08, slope5 < -0.20,
                         slope20 < -0.45, bear_structure, efficiency12 >= 0.30))

    # Priority is given to current auction failure/acceptance, then sustained trend,
    # then balance. This mirrors how a discretionary trader changes thesis after price acts.
    if accepted_up and accepted_down:
        regime, direction = "TRANSITION", "NEUTRAL"
    elif accepted_up and not failed_up:
        regime, direction = "BREAKOUT", "UP"
    elif accepted_down and not failed_down:
        regime, direction = "BREAKOUT", "DOWN"
    elif failed_up and not failed_down and pos40 >= 0.70:
        regime, direction = "MEAN_REVERSION", "DOWN"
    elif failed_down and not failed_up and pos40 <= 0.30:
        regime, direction = "MEAN_REVERSION", "UP"
    elif up_evidence >= 4 and up_evidence > down_evidence:
        regime, direction = "TREND", "UP"
    elif down_evidence >= 4 and down_evidence > up_evidence:
        regime, direction = "TREND", "DOWN"
    elif balanced or (compressed and abs(up_evidence - down_evidence) <= 2):
        regime, direction = "RANGE", "NEUTRAL"
    elif abs(up_evidence - down_evidence) <= 1 or abs(ema_gap) < 0.30:
        regime, direction = "TRANSITION", "NEUTRAL"
    else:
        regime, direction = "RANGE", "NEUTRAL"

    # -------------------- OPPORTUNITY THESIS --------------------
    if regime == "TREND":
        if direction == "UP" and pullback_up:
            opportunity = "TREND_PULLBACK_CONTINUATION"
            phase = "PULLBACK"
        elif direction == "DOWN" and pullback_down:
            opportunity = "TREND_PULLBACK_CONTINUATION"
            phase = "PULLBACK"
        elif expanding and ((direction == "UP" and displacement_up) or (direction == "DOWN" and displacement_down)):
            opportunity = "TREND_CONTINUATION"
            phase = "EXPANSION"
        else:
            opportunity = "TREND_CONTINUATION"
            phase = "BALANCED" if not expanding else "EXPANSION"
    elif regime == "BREAKOUT":
        opportunity = "BREAKOUT_CONTINUATION"
        phase = "ACCEPTANCE" if (accepted_up or accepted_down) else "BREAKOUT_DEVELOPING"
    elif regime == "MEAN_REVERSION":
        opportunity = "LIQUIDITY_REVERSAL"
        phase = "REJECTION"
    elif regime == "RANGE":
        if pos40 <= 0.20:
            opportunity = "RANGE_ROTATION_UP"
            direction = "UP"
            phase = "EDGE_REJECTION" if failed_down else "EDGE_WAIT"
        elif pos40 >= 0.80:
            opportunity = "RANGE_ROTATION_DOWN"
            direction = "DOWN"
            phase = "EDGE_REJECTION" if failed_up else "EDGE_WAIT"
        else:
            opportunity = "WAIT_FOR_RANGE_EDGE"
            phase = "BALANCED"
    else:
        opportunity = "WAIT_FOR_REPRICING"
        phase = "TRANSITION"

    # -------------------- LOCATION / RISK-REWARD SPACE --------------------
    if pos40 <= 0.20:
        location = "EDGE_LOW"
    elif pos40 >= 0.80:
        location = "EDGE_HIGH"
    else:
        location = "MID_RANGE"

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
    not_overextended = not ((direction == "UP" and pos40 >= 0.92) or (direction == "DOWN" and pos40 <= 0.08))

    # -------------------- E1 CROSS-CHECK AFTER E2 THESIS --------------------
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

    # -------------------- COUNTER-EVIDENCE --------------------
    counter: list[str] = []
    missing: list[str] = []
    invalidation: list[str] = []

    if regime == "TREND":
        structure_ok = bull_structure if direction == "UP" else bear_structure
        if not structure_ok:
            counter.append("trend direction lacks full swing confirmation")
        if efficiency12 < 0.25:
            counter.append("directional movement is inefficient")
        if direction == "UP" and ema20 < ema50 and not pullback_up:
            counter.append("moving-average structure still opposes upside thesis")
        if direction == "DOWN" and ema20 > ema50 and not pullback_down:
            counter.append("moving-average structure still opposes downside thesis")
        if pullback_up or pullback_down:
            missing.append("follow-through from the pullback")

    if regime == "BREAKOUT":
        if not expanding:
            counter.append("breakout lacks meaningful expansion")
        if direction == "UP" and not accepted_up:
            missing.append("acceptance above the broken level")
        if direction == "DOWN" and not accepted_down:
            missing.append("acceptance below the broken level")

    if regime == "MEAN_REVERSION":
        if not (failed_up or failed_down):
            missing.append("liquidity rejection")
        if not space_ok:
            counter.append("reversal has insufficient opposing-space")

    if regime == "RANGE":
        if opportunity == "WAIT_FOR_RANGE_EDGE":
            missing.append("price reaching a meaningful range edge")
        elif phase == "EDGE_WAIT":
            missing.append("rejection/response from the range edge")

    if not space_ok and direction != "NEUTRAL":
        counter.append("available path to opposing liquidity is too limited")
    if not not_overextended and direction != "NEUTRAL":
        counter.append("price is already materially extended from value")
    if alignment == "CONFLICT":
        counter.append(f"E1 disagrees with E2 independent direction={direction}")

    # Invalidation means the thesis is broken, not merely unconfirmed.
    if regime == "BREAKOUT" and direction == "UP" and failed_up:
        invalidation.append("upside auction failed back below the breakout area")
    if regime == "BREAKOUT" and direction == "DOWN" and failed_down:
        invalidation.append("downside auction failed back above the breakout area")
    if regime == "MEAN_REVERSION" and direction == "UP" and last < lo40:
        invalidation.append("downside repricing broke the expected reversal boundary")
    if regime == "MEAN_REVERSION" and direction == "DOWN" and last > hi40:
        invalidation.append("upside repricing broke the expected reversal boundary")

    severity = (
        "THESIS_INVALIDATION" if invalidation
        else "MATERIAL" if len(counter) >= 2
        else "MINOR" if counter
        else "NONE"
    )

    # -------------------- PROFESSIONAL MATURITY MODEL --------------------
    regime_strength = {"BREAKOUT": 1.0, "TREND": 0.88, "MEAN_REVERSION": 0.72,
                       "RANGE": 0.58, "TRANSITION": 0.22}[regime]
    structure_strength = 1.0 if (bull_structure or bear_structure) else 0.0
    directional_strength = min(efficiency12 / 0.50, 1.0)
    auction_strength = 1.0 if (accepted_up or accepted_down or failed_up or failed_down) else 0.0
    location_strength = 1.0 if (space_ok and not_overextended) else 0.45

    confidence = (
        0.12
        + 0.24 * regime_strength
        + 0.18 * structure_strength
        + 0.18 * directional_strength
        + 0.14 * auction_strength
        + 0.14 * location_strength
    )
    if alignment == "ALIGNED":
        confidence += 0.06
    elif alignment == "CONFLICT":
        confidence -= 0.08
    if severity == "MATERIAL":
        confidence -= 0.12
    elif severity == "THESIS_INVALIDATION":
        confidence -= 0.30
    confidence = max(0.10, min(0.95, confidence))

    if invalidation:
        maturity, opportunity_state, quality = "INVALIDATED", "REJECTED", "LOW"
    elif regime == "TRANSITION":
        maturity, opportunity_state, quality = "FORMING", "WAIT", "LOW"
    elif opportunity == "WAIT_FOR_RANGE_EDGE":
        maturity, opportunity_state, quality = "FORMING", "WAIT", "LOW"
    elif missing:
        maturity = "DEVELOPING"
        opportunity_state = "WAIT_FOR_CONFIRMATION"
        quality = "MEDIUM" if confidence >= 0.55 else "LOW"
    elif severity == "MATERIAL":
        maturity, opportunity_state = "DEVELOPING", "CAUTION"
        quality = "MEDIUM" if confidence >= 0.55 else "LOW"
    elif confidence >= 0.72 and regime in {"TREND", "BREAKOUT", "MEAN_REVERSION"} and space_ok and not_overextended:
        maturity, opportunity_state, quality = "MATURE", "ACTIONABLE_CONTEXT", "HIGH"
    else:
        maturity, opportunity_state = "DEVELOPING", "DEVELOPING"
        quality = "MEDIUM" if confidence >= 0.55 else "LOW"

    # -------------------- EXPLAINABLE OUTPUT --------------------
    factors = [
        f"independent_regime={regime}",
        f"opportunity={opportunity}",
        f"direction={direction}",
        f"auction={('ACCEPTING_UP' if accepted_up else 'ACCEPTING_DOWN' if accepted_down else 'FAILED_UP' if failed_up else 'FAILED_DOWN' if failed_down else 'UNRESOLVED')}",
        f"location={location}",
        f"space_atr={opposing_space_atr:.2f}",
        f"maturity={maturity}",
        f"counter_evidence={severity}",
    ]
    if pullback_up or pullback_down:
        factors.append("pullback_detected_without_structure_break")
    if expanding:
        factors.append("volatility_expansion_present")
    if compressed:
        factors.append("volatility_compression_present")

    evidence = [
        f"ema_gap_atr={ema_gap:.3f}", f"ema20_slope_atr={ema20_slope:.3f}",
        f"ema50_slope_atr={ema50_slope:.3f}", f"slope5_atr={slope5:.3f}",
        f"slope20_atr={slope20:.3f}", f"slope40_atr={slope40:.3f}",
        f"efficiency12={efficiency12:.3f}", f"volatility_ratio={vol_ratio:.3f}",
        f"trend_up_evidence={up_evidence}/6", f"trend_down_evidence={down_evidence}/6",
        f"structure={'BULLISH' if bull_structure else 'BEARISH' if bear_structure else 'MIXED'}",
        f"position20={pos20:.3f}", f"position40={pos40:.3f}",
        f"range_width_atr={width40 / atr:.3f}", f"body_ratio={body_ratio:.3f}",
        f"upper_wick_atr={upper_wick / atr:.3f}", f"lower_wick_atr={lower_wick / atr:.3f}",
        f"compressed={compressed}", f"expanding={expanding}",
        f"breakout_up={broke_up}", f"breakout_down={broke_down}",
        f"accepted_up={accepted_up}", f"accepted_down={accepted_down}",
        f"failed_up={failed_up}", f"failed_down={failed_down}",
        f"pullback_up={pullback_up}", f"pullback_down={pullback_down}",
        f"space_atr={opposing_space_atr:.3f}", f"invalidation_distance_atr={invalidation_distance_atr:.3f}",
        f"e1_direction={e1_direction}", f"e1_state={e1_state}", f"e1_structure={e1_structure}",
        f"e1_e2_alignment={alignment}",
    ]

    observations = [
        f"state={regime}", f"thesis={regime}:{opportunity}", f"direction={direction}",
        f"phase={phase}", f"opportunity={opportunity}", f"opportunity_state={opportunity_state}",
        f"opportunity_maturity={maturity}", f"quality={quality}", f"auction_state={factors[3].split('=', 1)[1]}",
        f"location_context={location}", f"counter_evidence_severity={severity}",
        f"upstream_thesis=E2 forms its own thesis first; E1 is a cross-check only.",
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
        "auction_state": factors[3].split("=", 1)[1],
        "location_context": location,
        "regime_confidence": round(confidence, 3),
        "decision_factors": factors,
        "observations": observations,
        "evidence": evidence,
        "counter_evidence": counter,
        "counter_evidence_severity": severity,
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
