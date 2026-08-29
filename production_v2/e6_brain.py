from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Setup Brain"
QUESTION = "What setup is forming, in what direction, and at what stage?"
ARCHITECTURE = "E6_PROFESSIONAL_SETUP_FORMATION_BRAIN_V3"
VERSION = "3.0"
MIN_BARS = 60
ATR_PERIOD = 14
EMA_FAST = 20
EMA_SLOW = 50
BREAKOUT_LOOKBACK = 12
PULLBACK_LOOKBACK = 6


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    value = values[0]
    for x in values[1:]:
        value = alpha * x + (1.0 - alpha) * value
    return value


def _atr(bars: list[dict[str, Any]], period: int = ATR_PERIOD) -> float:
    if len(bars) < 2:
        return 0.0
    sample = bars[-(period + 1):]
    trs: list[float] = []
    for i, bar in enumerate(sample):
        high = float(bar["high"])
        low = float(bar["low"])
        if i == 0:
            trs.append(high - low)
        else:
            prev_close = float(sample[i - 1]["close"])
            trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return mean(trs[-period:]) if trs else 0.0


def _norm_direction(value: Any) -> str:
    v = str(value or "NEUTRAL").upper().strip()
    if v in {"UP", "BULLISH", "BUY", "LONG", "TREND_UP"}:
        return "BUY"
    if v in {"DOWN", "BEARISH", "SELL", "SHORT", "TREND_DOWN"}:
        return "SELL"
    return "NEUTRAL"


def _payload(upstream: dict[str, EngineResult], engine_id: str) -> dict[str, Any]:
    result = upstream.get(engine_id)
    return result.output if result else {}


def _direction_context(e1: dict[str, Any], e2: dict[str, Any], e3: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    support: list[str] = []
    counter: list[str] = []
    e2_direction = _norm_direction(e2.get("direction"))
    e1_pressure = _norm_direction(e1.get("directional_pressure"))
    direction = e2_direction if e2_direction in {"BUY", "SELL"} else e1_pressure
    if direction in {"BUY", "SELL"}:
        support.append(f"DIRECTIONAL_CONTEXT={direction}")
    else:
        counter.append("NO_DIRECTIONAL_CONTEXT")

    slope = str(e3.get("slope_context", "")).upper()
    if slope in {"UP", "DOWN"}:
        slope_direction = "BUY" if slope == "UP" else "SELL"
        support.append(f"E3_SLOPE={slope}")
        if direction in {"BUY", "SELL"} and slope_direction != direction:
            counter.append("STRUCTURE_SLOPE_CONFLICT")

    finding = str(e3.get("finding", e3.get("structure_state", ""))).upper()
    internal = str(e3.get("internal_count_state", "")).upper()
    external = str(e3.get("external_count_state", "")).upper()
    if "MIXED" in finding or "MIXED" in internal:
        counter.append("STRUCTURE_MIXED")
    if direction == "BUY" and external == "DOWN":
        counter.append("EXTERNAL_STRUCTURE_COUNTERTREND")
    if direction == "SELL" and external == "UP":
        counter.append("EXTERNAL_STRUCTURE_COUNTERTREND")
    if "FAILED_BOS" in finding:
        counter.append("FAILED_STRUCTURE_BREAK")
    if "CHOCH" in finding or "CHOCH" in str(e3.get("external_bos", "")).upper():
        counter.append("STRUCTURE_TRANSITION_EVIDENCE")
    return direction, support, list(dict.fromkeys(counter))


def _candle_behavior(bars: list[dict[str, Any]], atr: float, direction: str) -> dict[str, Any]:
    last = bars[-1]
    open_ = float(last["open"])
    close = float(last["close"])
    high = float(last["high"])
    low = float(last["low"])
    body = abs(close - open_)
    rng = max(high - low, 1e-9)
    close_position = (close - low) / rng
    impulse = body >= 0.60 * atr
    directional_close = (
        close_position >= 0.65 if direction == "BUY"
        else close_position <= 0.35 if direction == "SELL"
        else False
    )
    return {
        "body_atr": round(body / max(atr, 1e-9), 4),
        "range_atr": round(rng / max(atr, 1e-9), 4),
        "close_position": round(close_position, 4),
        "impulse": impulse,
        "directional_close": directional_close,
    }


def _trend_pullback(bars: list[dict[str, Any]], atr: float, direction: str, e3: dict[str, Any]) -> dict[str, Any]:
    if direction not in {"BUY", "SELL"} or len(bars) < EMA_SLOW + 5:
        return {"candidate": False, "evidence": [], "missing": ["direction_or_history"]}
    closes = [float(b["close"]) for b in bars]
    e20 = _ema(closes, EMA_FAST)
    e50 = _ema(closes, EMA_SLOW)
    recent = bars[-PULLBACK_LOOKBACK:]
    recent_low = min(float(b["low"]) for b in recent)
    recent_high = max(float(b["high"]) for b in recent)
    price = closes[-1]
    distance = abs(price - e20) / max(atr, 1e-9)
    aligned = price > e20 > e50 if direction == "BUY" else price < e20 < e50
    touched = recent_low <= e20 + 0.25 * atr if direction == "BUY" else recent_high >= e20 - 0.25 * atr
    reclaimed = price >= e20 if direction == "BUY" else price <= e20
    clean_structure = "MIXED" not in str(e3.get("finding", "")).upper()
    evidence: list[str] = []
    missing: list[str] = []
    if aligned: evidence.append("TREND_ALIGNMENT_EMA20_EMA50")
    else: missing.append("trend_alignment")
    if touched: evidence.append("RETRACEMENT_TOWARD_EMA20")
    else: missing.append("retracement_behavior")
    if reclaimed: evidence.append("RECLAIM_OR_HOLD_EMA20")
    else: missing.append("reclaim_or_hold")
    if distance > 1.25: missing.append("controlled_distance_from_mean")
    if not clean_structure: missing.append("clean_structure")
    return {
        "candidate": aligned and touched and reclaimed and clean_structure and distance <= 1.50,
        "evidence": evidence,
        "missing": missing,
        "distance_atr": round(distance, 4),
    }


def _breakout(bars: list[dict[str, Any]], atr: float, direction: str) -> dict[str, Any]:
    if direction not in {"BUY", "SELL"} or len(bars) <= BREAKOUT_LOOKBACK:
        return {"candidate": False, "evidence": [], "missing": ["breakout_history"]}
    prior = bars[-(BREAKOUT_LOOKBACK + 1):-1]
    high = max(float(b["high"]) for b in prior)
    low = min(float(b["low"]) for b in prior)
    last = bars[-1]
    close = float(last["close"])
    open_ = float(last["open"])
    rng = max(float(last["high"]) - float(last["low"]), 1e-9)
    body = abs(close - open_)
    expansion = rng >= 0.80 * atr or body >= 0.60 * atr
    broke = close > high if direction == "BUY" else close < low
    close_position = (close - float(last["low"])) / rng
    strong_close = close_position >= 0.65 if direction == "BUY" else close_position <= 0.35
    evidence: list[str] = []
    missing: list[str] = []
    if broke: evidence.append("CLOSED_RANGE_BREAK")
    else: missing.append("closed_break_of_range")
    if expansion: evidence.append("VOLATILITY_EXPANSION")
    else: missing.append("expansion")
    if strong_close: evidence.append("DIRECTIONAL_CLOSE")
    else: missing.append("directional_close")
    return {"candidate": broke and expansion and strong_close, "evidence": evidence, "missing": missing}


def _breakout_retest(bars: list[dict[str, Any]], atr: float, direction: str) -> dict[str, Any]:
    if direction not in {"BUY", "SELL"} or len(bars) < BREAKOUT_LOOKBACK + 3:
        return {"candidate": False, "evidence": [], "missing": ["breakout_retest_history"]}
    before = bars[-(BREAKOUT_LOOKBACK + 3):-3]
    level = max(float(b["high"]) for b in before) if direction == "BUY" else min(float(b["low"]) for b in before)
    breakout_bar = bars[-3]
    retest_bars = bars[-2:]
    broke = float(breakout_bar["close"]) > level if direction == "BUY" else float(breakout_bar["close"]) < level
    touched = any(
        float(b["low"]) <= level + 0.25 * atr if direction == "BUY" else float(b["high"]) >= level - 0.25 * atr
        for b in retest_bars
    )
    held = float(bars[-1]["close"]) >= level if direction == "BUY" else float(bars[-1]["close"]) <= level
    evidence: list[str] = []
    missing: list[str] = []
    if broke: evidence.append("PRIOR_CLOSED_BREAKOUT")
    else: missing.append("prior_breakout")
    if touched: evidence.append("LEVEL_RETEST")
    else: missing.append("retest")
    if held: evidence.append("RETEST_HOLD")
    else: missing.append("retest_hold")
    return {"candidate": broke and touched and held, "evidence": evidence, "missing": missing, "level": level}


def _impulse_continuation(bars: list[dict[str, Any]], atr: float, direction: str) -> dict[str, Any]:
    if direction not in {"BUY", "SELL"} or len(bars) < 5:
        return {"candidate": False, "evidence": [], "missing": ["impulse_history"]}
    recent = bars[-4:]
    impulse_index = max(range(3), key=lambda i: abs(float(recent[i]["close"]) - float(recent[i]["open"])))
    impulse_body = abs(float(recent[impulse_index]["close"]) - float(recent[impulse_index]["open"]))
    impulse_direction = _norm_direction("BUY" if float(recent[impulse_index]["close"]) > float(recent[impulse_index]["open"]) else "SELL")
    last = recent[-1]
    last_direction = _norm_direction("BUY" if float(last["close"]) > float(last["open"]) else "SELL")
    impulse = impulse_body >= 0.80 * atr and impulse_direction == direction
    follow_through = last_direction == direction
    evidence: list[str] = []
    missing: list[str] = []
    if impulse: evidence.append("DIRECTIONAL_PRIOR_IMPULSE")
    else: missing.append("meaningful_directional_impulse")
    if follow_through: evidence.append("DIRECTIONAL_FOLLOW_THROUGH")
    else: missing.append("follow_through")
    return {"candidate": impulse and follow_through, "evidence": evidence, "missing": missing}


def _setup_output(
    *,
    state: str,
    setup: str,
    direction: str,
    stage: str,
    maturity: str,
    thesis: str,
    quality: float,
    supporting: list[str],
    counter: list[str],
    missing: list[str],
    next_required: list[str],
    invalidation: list[str],
    candidates: list[str],
) -> EngineResult:
    reasons = list(dict.fromkeys(counter + ([] if state in {"MATURE", "TRIGGER_PENDING"} else ["SETUP_NOT_MATURE"])))
    gate = state == "MATURE"
    output = {
        "architecture": ARCHITECTURE,
        "version": VERSION,
        "question": QUESTION,
        "reasoning_role": "SETUP_ANALYST",
        "decision_authority": "E9",
        "trade_decision_authority": False,
        "state": state,
        "setup": setup,
        "setup_family": setup,
        "direction": direction,
        "stage": stage,
        "maturity": maturity,
        "thesis": thesis,
        "setup_quality": round(quality, 4),
        "candidate_setups": candidates,
        "supporting_evidence": list(dict.fromkeys(supporting)),
        "counter_evidence": list(dict.fromkeys(counter)),
        "missing_evidence": list(dict.fromkeys(missing)),
        "next_required_evidence": list(dict.fromkeys(next_required)),
        "invalidation": invalidation,
    }
    return EngineResult("E6", NAME, gate, round(quality * 100.0, 2), output, tuple(reasons))


def analyze_e6(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """E6 owns setup formation and lifecycle, not entry confirmation or trade decision."""
    bars = list(snapshot.get("bars") or [])
    if len(bars) < MIN_BARS:
        return _setup_output(
            state="WAIT", setup="NONE", direction="NEUTRAL", stage="UNRESOLVED", maturity="UNRESOLVED",
            thesis="NO_SETUP: insufficient closed-candle history", quality=0.0,
            supporting=[], counter=[f"CLOSED_CANDLES_BELOW_MINIMUM={MIN_BARS}"],
            missing=["sufficient_closed_candle_data"], next_required=["more closed candles"],
            invalidation=["new closed candle may change evidence"], candidates=[]
        )

    try:
        atr = _atr(bars)
        closes = [float(b["close"]) for b in bars]
        price = closes[-1]
        if atr <= 0 or price <= 0:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return _setup_output(
            state="WAIT", setup="NONE", direction="NEUTRAL", stage="UNRESOLVED", maturity="UNRESOLVED",
            thesis="NO_SETUP: invalid market data", quality=0.0,
            supporting=[], counter=["INVALID_MARKET_DATA"], missing=["valid_ohlc_data"],
            next_required=["valid closed candle"], invalidation=["new valid closed candle"], candidates=[]
        )

    e1 = _payload(upstream, "E1")
    e2 = _payload(upstream, "E2")
    e3 = _payload(upstream, "E3")
    e4 = _payload(upstream, "E4")
    e5 = _payload(upstream, "E5")

    direction, context_support, counter = _direction_context(e1, e2, e3)
    behavior = _candle_behavior(bars, atr, direction)
    pullback = _trend_pullback(bars, atr, direction, e3)
    breakout = _breakout(bars, atr, direction)
    retest = _breakout_retest(bars, atr, direction)
    impulse = _impulse_continuation(bars, atr, direction)

    candidates: list[tuple[str, dict[str, Any]]] = [
        ("BREAKOUT_RETEST", retest),
        ("BREAKOUT", breakout),
        ("TREND_PULLBACK", pullback),
        ("IMPULSE_CONTINUATION", impulse),
    ]
    viable = [(name, data) for name, data in candidates if data.get("candidate")]
    candidate_names = [name for name, data in candidates if data.get("evidence")]

    e2_opportunity = str(e2.get("opportunity", e2.get("opportunity_type", ""))).upper()
    e2_phase = str(e2.get("phase", e2.get("opportunity_maturity", ""))).upper()
    e2_thesis = str(e2.get("thesis", "")).upper()
    e4_text = str(e4).upper()
    e5_text = str(e5).upper()

    supporting = list(context_support)
    supporting.append(f"E2_OPPORTUNITY={e2_opportunity or 'UNSPECIFIED'}")
    supporting.append(f"E2_PHASE={e2_phase or 'UNSPECIFIED'}")
    supporting.append(f"CURRENT_CANDLE_BODY_ATR={behavior['body_atr']}")
    supporting.append(f"CURRENT_CANDLE_DIRECTIONAL_CLOSE={behavior['directional_close']}")

    if "REJECTION" in e4_text or "SWEEP" in e4_text:
        supporting.append("E4_LIQUIDITY_EVENT_PRESENT")
    if "ACCEPTED" in e5_text:
        supporting.append("E5_LOCATION_ACCEPTANCE_CONTEXT")
    if "CONSTRAINED" in e5_text or "ADVERSE" in e5_text:
        counter.append("LOCATION_CONSTRAINT")
    if "PENDING" in e4_text and ("SWEEP" in e4_text or "REJECTION" in e4_text):
        counter.append("LIQUIDITY_EVENT_NOT_TERMINALLY_CONFIRMED")
    if e2_phase in {"UNPROVEN", "WAIT", "UNRESOLVED"}:
        counter.append("OPPORTUNITY_MATURITY_UNPROVEN")

    # A professional setup must have its own price formation. Upstream direction
    # alone can never manufacture a setup.
    if not viable:
        missing: list[str] = []
        for _, data in candidates:
            missing.extend(data.get("missing", []))
        missing = list(dict.fromkeys(missing))
        if not missing:
            missing = ["setup_specific_price_formation"]
        thesis = "NO_VALID_SETUP_FORMED"
        if direction in {"BUY", "SELL"}:
            thesis = f"{direction}: context exists, but no setup-specific formation is complete"
        next_required = [
            "a setup-specific price sequence on a closed candle",
            "evidence that survives counter-evidence from E3-E5",
            "clear setup maturation before E7 confirmation",
        ]
        return _setup_output(
            state="WAIT", setup="NONE", direction=direction, stage="SEARCHING", maturity="UNRESOLVED",
            thesis=thesis, quality=0.0 if direction == "NEUTRAL" else 0.20,
            supporting=supporting, counter=counter, missing=missing,
            next_required=next_required,
            invalidation=["directional context reverses", "structure changes materially", "new closed candle invalidates the premise"],
            candidates=candidate_names,
        )

    # Select the most structurally complete formation. Retest outranks a raw
    # breakout because it contains an additional cause/effect sequence.
    setup, formation = viable[0]
    formation_evidence = list(formation.get("evidence", []))
    supporting.extend([f"FORMATION={x}" for x in formation_evidence])

    hard_conflict = any(x in counter for x in {
        "STRUCTURE_SLOPE_CONFLICT", "EXTERNAL_STRUCTURE_COUNTERTREND", "FAILED_STRUCTURE_BREAK"
    })
    mixed_structure = "STRUCTURE_MIXED" in counter
    location_constrained = "LOCATION_CONSTRAINT" in counter
    opportunity_unproven = "OPPORTUNITY_MATURITY_UNPROVEN" in counter
    liquidity_pending = "LIQUIDITY_EVENT_NOT_TERMINALLY_CONFIRMED" in counter

    # Formation is complete, but maturity depends on whether the environment
    # can support it. E6 does not call this an entry confirmation.
    if hard_conflict or mixed_structure or location_constrained:
        stage = "FORMING" if not hard_conflict else "CONFLICTED"
        maturity = "DEVELOPING" if not hard_conflict else "UNRESOLVED"
        quality = 0.35 if not hard_conflict else 0.15
        next_required = [
            "resolution of structural conflict" if hard_conflict else "location/space improvement",
            "closed-candle setup persistence",
            "E7 confirmation only after E6 maturity improves",
        ]
        return _setup_output(
            state="WAIT", setup=setup, direction=direction, stage=stage, maturity=maturity,
            thesis=f"{direction}_{setup}: formation exists but is structurally/environmentally constrained",
            quality=quality, supporting=supporting, counter=counter,
            missing=["environmental_acceptance"], next_required=next_required,
            invalidation=["setup formation fails", "structure confirms competing direction", "location becomes invalid"],
            candidates=candidate_names,
        )

    if opportunity_unproven or liquidity_pending:
        stage = "TESTING"
        maturity = "DEVELOPING"
        quality = 0.55
        missing = []
        if opportunity_unproven: missing.append("opportunity_maturity")
        if liquidity_pending: missing.append("terminal_liquidity_confirmation")
        return _setup_output(
            state="DEVELOPING", setup=setup, direction=direction, stage=stage, maturity=maturity,
            thesis=f"{direction}_{setup}: setup formation is present but auction context is not fully proven",
            quality=quality, supporting=supporting, counter=counter, missing=missing,
            next_required=["closed-candle persistence", "resolution of auction uncertainty", "E7 confirmation after maturity"],
            invalidation=["setup price sequence fails", "direction reverses", "structure breaks against thesis"],
            candidates=candidate_names,
        )

    # MATURE means the setup's own formation is complete and not vetoed by
    # upstream evidence. It still does NOT mean entry is confirmed.
    stage = "TRIGGER_PENDING"
    maturity = "MATURE"
    quality = 0.80
    if len(formation_evidence) >= 3:
        quality += 0.05
    if behavior["directional_close"]:
        quality += 0.05
    quality = min(0.95, quality)
    return _setup_output(
        state="MATURE", setup=setup, direction=direction, stage=stage, maturity=maturity,
        thesis=f"{direction}_{setup}: setup formation is mature; entry confirmation remains downstream",
        quality=quality, supporting=supporting,
        counter=counter,
        missing=["entry_confirmation"],
        next_required=["E7 closed-candle confirmation"],
        invalidation=["setup sequence fails", "direction reverses", "structure confirms competing direction", "location becomes structurally constrained"],
        candidates=candidate_names,
    )
