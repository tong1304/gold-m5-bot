from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Setup Brain"
QUESTION = "What setup is forming, in what direction, and at what stage?"
ARCHITECTURE = "E6_PROFESSIONAL_SETUP_FORMATION_BRAIN_V2"
VERSION = "2.0"
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
    """Use upstream direction as context, never as the setup itself."""
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
    if "CHOCH" in finding or "CHOCH" in str(e3.get("external_bos", "")).upper():
        counter.append("STRUCTURE_TRANSITION_EVIDENCE")
    return direction, support, counter


def _candle_behavior(bars: list[dict[str, Any]], atr: float, direction: str) -> dict[str, Any]:
    last = bars[-1]
    body = abs(float(last["close"]) - float(last["open"]))
    rng = max(float(last["high"]) - float(last["low"]), 1e-9)
    close_position = (float(last["close"]) - float(last["low"])) / rng
    impulse = body >= 0.60 * atr
    directional_close = close_position >= 0.65 if direction == "BUY" else close_position <= 0.35 if direction == "SELL" else False
    return {
        "body_atr": round(body / max(atr, 1e-9), 4),
        "range_atr": round(rng / max(atr, 1e-9), 4),
        "close_position": round(close_position, 4),
        "impulse": impulse,
        "directional_close": directional_close,
    }


def _trend_pullback(bars: list[dict[str, Any]], atr: float, direction: str, e3: dict[str, Any]) -> dict[str, Any]:
    if direction not in {"BUY", "SELL"} or len(bars) < EMA_SLOW + 5:
        return {"candidate": False, "evidence": [], "missing": ["directional_context_or_history"]}

    closes = [float(b["close"]) for b in bars]
    e20 = _ema(closes, EMA_FAST)
    e50 = _ema(closes, EMA_SLOW)
    price = closes[-1]
    recent = bars[-PULLBACK_LOOKBACK:]
    recent_low = min(float(b["low"]) for b in recent)
    recent_high = max(float(b["high"]) for b in recent)
    distance = abs(price - e20) / max(atr, 1e-9)
    trend_aligned = price > e20 > e50 if direction == "BUY" else price < e20 < e50
    touched_mean = recent_low <= e20 + 0.25 * atr if direction == "BUY" else recent_high >= e20 - 0.25 * atr
    reclaimed = price >= e20 if direction == "BUY" else price <= e20
    structure_ok = "MIXED" not in str(e3.get("finding", "")).upper()
    candidate = trend_aligned and touched_mean and reclaimed and structure_ok
    evidence: list[str] = []
    missing: list[str] = []
    if trend_aligned:
        evidence.append("TREND_ALIGNMENT_EMA20_EMA50")
    else:
        missing.append("trend_alignment")
    if touched_mean:
        evidence.append("RETRACEMENT_TOWARD_EMA20")
    else:
        missing.append("retracement_behavior")
    if reclaimed:
        evidence.append("RECLAIM_OR_HOLD_EMA20")
    else:
        missing.append("reclaim_or_hold")
    if not structure_ok:
        missing.append("clean_structure")
    if distance > 1.25:
        missing.append("controlled_distance_from_mean")
    return {"candidate": candidate, "evidence": evidence, "missing": missing, "ema20": e20, "ema50": e50, "distance_atr": distance}


def _breakout(bars: list[dict[str, Any]], atr: float, direction: str) -> dict[str, Any]:
    if direction not in {"BUY", "SELL"} or len(bars) <= BREAKOUT_LOOKBACK:
        return {"candidate": False, "evidence": [], "missing": ["breakout_history"]}
    prior = bars[-(BREAKOUT_LOOKBACK + 1):-1]
    high = max(float(b["high"]) for b in prior)
    low = min(float(b["low"]) for b in prior)
    last = bars[-1]
    close = float(last["close"])
    rng = max(float(last["high"]) - float(last["low"]), 1e-9)
    body = abs(close - float(last["open"]))
    expansion = rng >= 0.80 * atr or body >= 0.60 * atr
    if direction == "BUY":
        broke = close > high
        strong_close = (close - float(last["low"])) / rng >= 0.65
    else:
        broke = close < low
        strong_close = (close - float(last["low"])) / rng <= 0.35
    candidate = broke and expansion and strong_close
    evidence = []
    missing = []
    if broke: evidence.append("CLOSED_RANGE_BREAK")
    else: missing.append("closed_break_of_range")
    if expansion: evidence.append("VOLATILITY_EXPANSION")
    else: missing.append("expansion")
    if strong_close: evidence.append("DIRECTIONAL_CLOSE")
    else: missing.append("directional_close")
    return {"candidate": candidate, "evidence": evidence, "missing": missing, "prior_high": high, "prior_low": low}


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
    candidate = broke and touched and held
    evidence = []
    missing = []
    if broke: evidence.append("PRIOR_CLOSED_BREAKOUT")
    else: missing.append("prior_breakout")
    if touched: evidence.append("LEVEL_RETEST")
    else: missing.append("retest")
    if held: evidence.append("RETEST_HOLD")
    else: missing.append("retest_hold")
    return {"candidate": candidate, "evidence": evidence, "missing": missing, "level": level}


def _impulse_continuation(bars: list[dict[str, Any]], atr: float, direction: str) -> dict[str, Any]:
    if direction not in {"BUY", "SELL"} or len(bars) < 5:
        return {"candidate": False, "evidence": [], "missing": ["impulse_history"]}
    recent = bars[-4:]
    bodies = [abs(float(b["close"]) - float(b["open"])) for b in recent]
    impulse = max(bodies[:-1]) >= 0.80 * atr
    last = recent[-1]
    if direction == "BUY":
        continuation = float(last["close"]) > float(last["open"])
    else:
        continuation = float(last["close"]) < float(last["open"])
    candidate = impulse and continuation
    evidence = ["PRIOR_IMPULSE"] if impulse else []
    if continuation: evidence.append("DIRECTIONAL_FOLLOW_THROUGH")
    missing = []
    if not impulse: missing.append("meaningful_impulse")
    if not continuation: missing.append("follow_through")
    return {"candidate": candidate, "evidence": evidence, "missing": missing}


def _score_setup(
    direction: str,
    formation: list[str],
    context_support: list[str],
    counter: list[str],
    e4: dict[str, Any],
    e5: dict[str, Any],
    stage: str,
) -> tuple[float, list[str], list[str]]:
    """Score evidence quality, not probability of profit."""
    score = 0.0
    support = list(formation) + list(context_support)
    reasons = list(counter)
    if formation:
        score += min(0.50, 0.10 * len(formation))
    if direction in {"BUY", "SELL"}:
        score += 0.10
    if stage in {"TESTING", "TRIGGER_PENDING"}:
        score += 0.10
    e4_text = str(e4).upper()
    e5_text = str(e5).upper()
    if "REJECTION" in e4_text or "SWEEP" in e4_text:
        score += 0.10
        support.append("E4_LIQUIDITY_CONTEXT_SUPPORT")
    if "SPACE" in e5_text and "CONSTRAINED" not in e5_text:
        score += 0.10
        support.append("E5_LOCATION_SPACE_SUPPORT")
    if any(x in e5_text for x in ("ADVERSE", "SPACE_CONSTRAINED", "VERY_CONSTRAINED")):
        score -= 0.15
        reasons.append("LOCATION_CONSTRAINT")
    if any(x in counter for x in ("STRUCTURE_SLOPE_CONFLICT", "EXTERNAL_STRUCTURE_COUNTERTREND")):
        score -= 0.25
    if "STRUCTURE_MIXED" in counter:
        score -= 0.15
    return round(max(0.0, min(1.0, score)), 4), support, list(dict.fromkeys(reasons))


def _incomplete(reason: str) -> EngineResult:
    output = {
        "architecture": ARCHITECTURE,
        "version": VERSION,
        "question": QUESTION,
        "reasoning_role": "SETUP_ANALYST",
        "decision_authority": "E9",
        "trade_decision_authority": False,
        "state": "WAIT",
        "setup": "NONE",
        "setup_family": "NONE",
        "direction": "NEUTRAL",
        "stage": "UNRESOLVED",
        "maturity": "UNRESOLVED",
        "thesis": "UNRESOLVED",
        "setup_quality": 0.0,
        "supporting_evidence": [],
        "counter_evidence": [reason],
        "missing_evidence": ["sufficient_closed_candle_data"],
        "next_required_evidence": ["sufficient closed candles"],
        "invalidation": ["new closed candle invalidates the premise"],
    }
    return EngineResult("E6", NAME, None, 0.0, output, ("INSUFFICIENT_DATA",))


def analyze_e6(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """Professional setup formation analysis.

    E6 owns setup identification and lifecycle only. It consumes E1-E5 as
    evidence/context, does not override them, does not perform entry
    confirmation, and never makes the final trade decision. E9 remains the
    decision authority.
    """
    bars = list(snapshot.get("bars") or [])
    if len(bars) < MIN_BARS:
        return _incomplete(f"closed candles below minimum {MIN_BARS}")

    try:
        atr = _atr(bars)
        if atr <= 0:
            return _incomplete("ATR_INVALID")
        closes = [float(b["close"]) for b in bars]
        price = closes[-1]
    except (KeyError, TypeError, ValueError):
        return _incomplete("INVALID_MARKET_DATA")

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

    candidates = [
        ("TREND_PULLBACK", pullback),
        ("BREAKOUT_RETEST", retest),
        ("BREAKOUT", breakout),
        ("IMPULSE_CONTINUATION", impulse),
    ]
    active = [(name, data) for name, data in candidates if data.get("candidate")]

    # Avoid manufacturing a setup from proximity to EMA or one large candle.
    if not active:
        setup = "NONE"
        stage = "NONE"
        maturity = "UNRESOLVED"
        thesis = "NO_VALID_SETUP_FORMING"
        setup_quality = 0.0
        formation: list[str] = []
        missing = list(dict.fromkeys(
            pullback.get("missing", []) +
            breakout.get("missing", []) +
            retest.get("missing", []) +
            impulse.get("missing", [])
        ))
    else:
        # Prefer the most complete lifecycle state over generic impulse.
        priority = {"BREAKOUT_RETEST": 4, "TREND_PULLBACK": 3, "BREAKOUT": 2, "IMPULSE_CONTINUATION": 1}
        setup, data = max(active, key=lambda item: priority[item[0]])
        formation = list(data.get("evidence", []))
        if setup == "BREAKOUT_RETEST":
            stage = "TRIGGER_PENDING"
        elif setup in {"TREND_PULLBACK", "BREAKOUT"}:
            stage = "TESTING"
        else:
            stage = "FORMING"
        quality, support, scored_counter = _score_setup(
            direction, formation, context_support, counter, e4, e5, stage
        )
        setup_quality = quality
        context_support = support
        counter = scored_counter
        missing = list(data.get("missing", []))
        if setup == "IMPULSE_CONTINUATION":
            missing.append("controlled_retracement_or_confirmation")
        if setup == "BREAKOUT":
            missing.append("retest_or_continuation_acceptance")
        maturity = "MATURE" if setup_quality >= 0.70 and not any(
            x in counter for x in ("STRUCTURE_SLOPE_CONFLICT", "EXTERNAL_STRUCTURE_COUNTERTREND", "STRUCTURE_MIXED", "LOCATION_CONSTRAINT")
        ) else "DEVELOPING"
        thesis = f"{direction}_{setup}" if direction in {"BUY", "SELL"} else "UNRESOLVED"

    # E6 must never confuse confirmation with setup formation.
    confirmation_boundary = (
        "E7_OWNS_ENTRY_CONFIRMATION; E6_ONLY_DESCRIBES_SETUP"
    )
    if setup == "NONE":
        gate = False
        score = 15.0 if direction == "NEUTRAL" else 30.0
        reasons = ["NO_VALID_SETUP_FORMING"]
    else:
        gate = maturity == "MATURE"
        score = round(setup_quality * 100.0, 2)
        reasons = [] if gate else ["SETUP_NOT_MATURE"]
        reasons.extend(counter)

    # Strong evidence of location/liquidity can support a setup, but cannot
    # create one when the price-action formation itself is absent.
    e4_support = "REJECTION" in str(e4).upper() or "SWEEP" in str(e4).upper()
    e5_constrained = any(x in str(e5).upper() for x in ("ADVERSE", "SPACE_CONSTRAINED", "VERY_CONSTRAINED"))
    supporting = list(dict.fromkeys(context_support + formation))
    if e4_support:
        supporting.append("E4_LIQUIDITY_CONTEXT_SUPPORT")
    if not e5_constrained and setup != "NONE":
        supporting.append("E5_LOCATION_NOT_OBVIOUSLY_BLOCKED")
    supporting.append(confirmation_boundary)

    invalidation = [
        "directional thesis reverses",
        "setup structure is broken",
        "price accepts the counter-direction beyond the setup boundary",
        "location or available space becomes structurally constrained",
        "new closed candle invalidates the formation",
    ]
    next_required = []
    if setup == "NONE":
        next_required.append("clear price-action setup formation")
    elif setup == "TREND_PULLBACK":
        next_required.extend(["controlled rejection/hold from pullback area", "E7 confirmation"])
    elif setup == "BREAKOUT":
        next_required.extend(["acceptance above/below broken level or clean retest", "E7 confirmation"])
    elif setup == "BREAKOUT_RETEST":
        next_required.append("E7 confirmation of continuation")
    elif setup == "IMPULSE_CONTINUATION":
        next_required.extend(["controlled retracement or continuation structure", "E7 confirmation"])

    output = {
        "architecture": ARCHITECTURE,
        "version": VERSION,
        "question": QUESTION,
        "reasoning_role": "SETUP_ANALYST",
        "decision_authority": "E9",
        "trade_decision_authority": False,
        "state": maturity if setup != "NONE" else "WAIT",
        "setup": setup,
        "setup_family": setup,
        "direction": direction,
        "stage": stage,
        "maturity": maturity,
        "thesis": thesis,
        "setup_quality": setup_quality,
        "confidence": setup_quality,
        "atr": round(atr, 6),
        "price": price,
        "price_behavior": behavior,
        "formation_evidence": formation,
        "supporting_evidence": supporting,
        "counter_evidence": list(dict.fromkeys(counter)),
        "missing_evidence": list(dict.fromkeys(missing)),
        "next_required_evidence": list(dict.fromkeys(next_required)),
        "candidate_setups": [name for name, data in candidates if data.get("candidate")],
        "setup_selection_rule": "MOST_COMPLETE_VALID_LIFECYCLE_WITHOUT_OVERRIDING_UPSTREAM_CONFLICTS",
        "upstream_context_used": ["E1", "E2", "E3", "E4", "E5"],
        "upstream_decision_authority_preserved": True,
        "confirmation_boundary": confirmation_boundary,
        "invalidation": invalidation,
        "gate_passed": gate,
    }
    reason_codes = tuple(dict.fromkeys(reasons))
    return EngineResult("E6", NAME, gate, score, output, reason_codes)
