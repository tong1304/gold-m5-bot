from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Setup Brain"
QUESTION = "What setup is forming, in what direction, and at what stage?"
ARCHITECTURE = "E6_PROFESSIONAL_SETUP_FORMATION_BRAIN_V9"
VERSION = "9.0"
MIN_BARS = 60
ATR_PERIOD = 14
EMA_FAST = 20
EMA_SLOW = 50
BREAKOUT_LOOKBACK = 12
PULLBACK_LOOKBACK = 6
MIN_SPACE_ATR = 0.75

SETUP_FAMILIES = ("LIQUIDITY_REVERSAL", "BREAKOUT_RETEST", "TREND_PULLBACK", "BREAKOUT", "IMPULSE_CONTINUATION")


def _payload(upstream: dict[str, EngineResult], name: str) -> dict[str, Any]:
    result = upstream.get(name)
    return result.output if result else {}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _norm(value: Any) -> str:
    text = _text(value)
    if text in {"UP", "BULLISH", "BUY", "LONG", "TREND_UP"}:
        return "BUY"
    if text in {"DOWN", "BEARISH", "SELL", "SHORT", "TREND_DOWN"}:
        return "SELL"
    return "NEUTRAL"


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
            prev = float(sample[i - 1]["close"])
            trs.append(max(high - low, abs(high - prev), abs(low - prev)))
    return mean(trs[-period:]) if trs else 0.0


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    value = values[0]
    for item in values[1:]:
        value = alpha * item + (1.0 - alpha) * value
    return value


def _auction_direction(event: str) -> str:
    if any(x in event for x in ("HIGH_SWEEP_REJECTION", "HIGH_FAILED_BREAK_RECLAIM")):
        return "SELL"
    if any(x in event for x in ("LOW_SWEEP_REJECTION", "LOW_FAILED_BREAK_RECLAIM")):
        return "BUY"
    if "HIGH_ACCEPTANCE" in event or "HIGH_BREAK" in event:
        return "BUY"
    if "LOW_ACCEPTANCE" in event or "LOW_BREAK" in event:
        return "SELL"
    return "NEUTRAL"


def _direction(e1: dict[str, Any], e2: dict[str, Any], e3: dict[str, Any], e4: dict[str, Any]) -> tuple[str, list[str], list[str], str]:
    supporting: list[str] = []
    counter: list[str] = []
    e2_dirs = [_norm(e2.get("direction")), _norm(e2.get("opportunity_direction"))]
    e2_dirs = [x for x in e2_dirs if x != "NEUTRAL"]
    pressure = _norm(e1.get("directional_pressure", e1.get("pressure")))
    external = _norm(e3.get("external_state", e3.get("external_count_state")))
    event = _text(e4.get("event", e4.get("finding")))
    auction = _auction_direction(event)

    if e2_dirs and len(set(e2_dirs)) == 1:
        direction = e2_dirs[0]
        source = "E2"
    elif pressure != "NEUTRAL" and external != "NEUTRAL" and pressure == external:
        direction = pressure
        source = "E1_E3_ALIGNMENT"
    elif auction != "NEUTRAL":
        direction = auction
        source = "E4_AUCTION"
    elif external != "NEUTRAL":
        direction = external
        source = "E3_STRUCTURE"
    elif pressure != "NEUTRAL":
        direction = pressure
        source = "E1_PRESSURE"
    else:
        direction = "NEUTRAL"
        source = "NONE"

    for label, value in (("E2", e2_dirs[0] if e2_dirs else "NEUTRAL"), ("E1_PRESSURE", pressure), ("E3_EXTERNAL", external), ("E4_AUCTION", auction)):
        if value != "NEUTRAL":
            supporting.append(f"{label}={value}")
    if direction != "NEUTRAL":
        supporting.append(f"DIRECTION_SOURCE={source}")
    if len(set(x for x in (pressure, external, auction) if x != "NEUTRAL")) > 1:
        counter.append("DIRECTIONAL_EVIDENCE_CONFLICT")
    finding = _text(e3.get("finding", e3.get("structure_state")))
    internal = _text(e3.get("internal_state", e3.get("internal_count_state")))
    if "MIXED" in finding or "MIXED" in internal:
        counter.append("STRUCTURE_MIXED")
    if (direction == "BUY" and external == "SELL") or (direction == "SELL" and external == "BUY"):
        counter.append("EXTERNAL_STRUCTURE_COUNTERTREND")
    if "FAILED_BOS" in finding:
        counter.append("FAILED_STRUCTURE_BREAK")
    return direction, supporting, list(dict.fromkeys(counter)), source


def _auction(e4: dict[str, Any]) -> tuple[str, bool, bool, int]:
    state = _text(e4.get("auction_state", e4.get("state")))
    event = _text(e4.get("event", e4.get("finding")))
    terminal = state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "REJECTED"} or "TERMINAL" in state
    pending = state == "PENDING" or "PENDING" in _text(e4)
    try:
        age = max(0, int(e4.get("event_age_bars", 0) or 0))
    except (TypeError, ValueError):
        age = 0
    return event, terminal, pending, age


def _location(e5: dict[str, Any]) -> tuple[float, float, bool]:
    long_space = float(e5.get("available_space_atr_long", 0.0) or 0.0)
    short_space = float(e5.get("available_space_atr_short", 0.0) or 0.0)
    text = _text(e5)
    explicit = any(x in text for x in ("LOCATION_CONSTRAINT", "SPACE_CONSTRAINED", "EXTENSION_RISK"))
    return long_space, short_space, explicit


def _candle(bars: list[dict[str, Any]], atr: float, direction: str) -> tuple[float, float, bool, float]:
    b = bars[-1]
    o, h, l, c = map(float, (b["open"], b["high"], b["low"], b["close"]))
    rng = max(h - l, 1e-9)
    pos = (c - l) / rng
    directional = pos >= 0.65 if direction == "BUY" else pos <= 0.35 if direction == "SELL" else False
    return abs(c - o) / max(atr, 1e-9), rng / max(atr, 1e-9), directional, pos


def _candidate_scan(bars: list[dict[str, Any]], atr: float, direction: str, e3: dict[str, Any], e4: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    if direction == "NEUTRAL":
        return [], [f"{name}:direction_missing" for name in SETUP_FAMILIES]
    found: list[dict[str, Any]] = []
    rejected: list[str] = []
    event = _text(e4.get("event", e4.get("finding")))
    finding = _text(e3.get("finding", e3.get("structure_state")))
    response = _norm(e4.get("response_actor"))
    b = bars[-1]
    o, h, l, c = map(float, (b["open"], b["high"], b["low"], b["close"]))
    rng = max(h - l, 1e-9)
    pos = (c - l) / rng

    liquidity_event = any(x in event for x in ("SWEEP_REJECTION", "FAILED_BREAK_RECLAIM"))
    high_event = "HIGH_" in event
    low_event = "LOW_" in event
    reversal_dir = "SELL" if high_event else "BUY" if low_event else "NEUTRAL"
    rejection_close = pos <= 0.40 if reversal_dir == "SELL" else pos >= 0.60 if reversal_dir == "BUY" else False
    if liquidity_event and reversal_dir == direction:
        evidence = ["E4_LIQUIDITY_EVENT", f"EVENT={event}"]
        if response == direction:
            evidence.append("RESPONSE_ACTOR_ALIGNED")
        if rejection_close:
            evidence.append("CURRENT_CLOSED_CANDLE_REJECTION")
        else:
            rejected.append("LIQUIDITY_REVERSAL:directional_close_pending")
        strength = 92 if rejection_close and response == direction else 78 if rejection_close else 68
        found.append({"name": "LIQUIDITY_REVERSAL", "evidence": evidence, "strength": strength, "price_response": rejection_close})
    elif liquidity_event:
        rejected.append("LIQUIDITY_REVERSAL:event_direction_conflict")

    if len(bars) >= BREAKOUT_LOOKBACK + 4:
        before = bars[-(BREAKOUT_LOOKBACK + 3):-3]
        level = max(float(x["high"]) for x in before) if direction == "BUY" else min(float(x["low"]) for x in before)
        prior_break = float(bars[-3]["close"]) > level if direction == "BUY" else float(bars[-3]["close"]) < level
        retest = any(float(x["low"]) <= level + 0.25 * atr for x in bars[-2:]) if direction == "BUY" else any(float(x["high"]) >= level - 0.25 * atr for x in bars[-2:])
        hold = c >= level if direction == "BUY" else c <= level
        if prior_break and retest and hold:
            found.append({"name": "BREAKOUT_RETEST", "evidence": ["PRIOR_CLOSED_BREAKOUT", "LEVEL_RETEST", "RETEST_HOLD"], "strength": 88, "price_response": True})
        else:
            missing = []
            if not prior_break: missing.append("prior_breakout")
            if not retest: missing.append("retest")
            if not hold: missing.append("retest_hold")
            rejected.append("BREAKOUT_RETEST:sequence_incomplete:" + ",".join(missing))

    closes = [float(x["close"]) for x in bars]
    ema20, ema50, price = _ema(closes, EMA_FAST), _ema(closes, EMA_SLOW), closes[-1]
    recent = bars[-PULLBACK_LOOKBACK:]
    touched = min(float(x["low"]) for x in recent) <= ema20 + 0.25 * atr if direction == "BUY" else max(float(x["high"]) for x in recent) >= ema20 - 0.25 * atr
    aligned = price > ema20 > ema50 if direction == "BUY" else price < ema20 < ema50
    held = price >= ema20 if direction == "BUY" else price <= ema20
    mixed = "MIXED" in finding
    if aligned and touched and held and not mixed and abs(price - ema20) <= 1.5 * atr:
        found.append({"name": "TREND_PULLBACK", "evidence": ["EMA20_EMA50_ALIGNMENT", "RETRACEMENT_TO_EMA20", "RECLAIM_OR_HOLD_EMA20"], "strength": 80, "price_response": True})
    else:
        rejected.append("TREND_PULLBACK:formation_incomplete")

    prior = bars[-(BREAKOUT_LOOKBACK + 1):-1]
    rh, rl = max(float(x["high"]) for x in prior), min(float(x["low"]) for x in prior)
    broke = c > rh if direction == "BUY" else c < rl
    expansion = h - l >= 0.8 * atr or abs(c - o) >= 0.6 * atr
    dclose = pos >= 0.65 if direction == "BUY" else pos <= 0.35
    if broke and expansion and dclose:
        found.append({"name": "BREAKOUT", "evidence": ["CLOSED_RANGE_BREAK", "VOLATILITY_EXPANSION", "DIRECTIONAL_CLOSE"], "strength": 84, "price_response": True})
    else:
        rejected.append("BREAKOUT:formation_incomplete")

    recent4 = bars[-4:]
    bodies = [abs(float(x["close"]) - float(x["open"])) for x in recent4[:3]]
    idx = max(range(len(bodies)), key=bodies.__getitem__)
    impulse = recent4[idx]
    impulse_dir = "BUY" if float(impulse["close"]) > float(impulse["open"]) else "SELL"
    follow_dir = "BUY" if c > o else "SELL"
    if bodies[idx] >= 0.8 * atr and impulse_dir == direction and follow_dir == direction and dclose:
        found.append({"name": "IMPULSE_CONTINUATION", "evidence": ["DIRECTIONAL_PRIOR_IMPULSE", "DIRECTIONAL_FOLLOW_THROUGH"], "strength": 76, "price_response": True})
    else:
        rejected.append("IMPULSE_CONTINUATION:sequence_incomplete")
    return found, rejected


def _result(state: str, setup: str, direction: str, stage: str, maturity: str, thesis: str, quality: float, supporting: list[str], counter: list[str], missing: list[str], next_required: list[str], invalidation: list[str], candidates: list[str], rejected: list[str], selected_strength: float = 0.0) -> EngineResult:
    quality = max(0.0, min(100.0, quality))
    reasons = list(dict.fromkeys(counter + ([] if maturity == "MATURE" else ["SETUP_NOT_MATURE"])))
    output = {
        "architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION,
        "role": "SETUP_ANALYST", "reasoning_role": "SETUP_FORMATION_REASONER",
        "decision_authority": "E9", "trade_decision_authority": False,
        "state": state, "setup": setup, "setup_family": setup, "direction": direction,
        "stage": stage, "lifecycle": stage, "maturity": maturity, "thesis": thesis,
        "setup_quality": round(quality, 2), "candidate_strength": round(selected_strength, 2),
        "candidate_setups": candidates, "rejected_setups": rejected,
        "supporting_evidence": list(dict.fromkeys(supporting)), "counter_evidence": list(dict.fromkeys(counter)),
        "missing_evidence": list(dict.fromkeys(missing)), "next_required_evidence": list(dict.fromkeys(next_required)),
        "invalidation": list(dict.fromkeys(invalidation)),
        "observations": [
            f"candidate_setups={','.join(candidates) if candidates else 'NONE'}",
            f"selected_setup={setup}", f"selected_direction={direction}", f"rejected_setups={len(rejected)}",
            f"supporting_evidence={','.join(supporting) if supporting else 'NONE'}",
            f"counter_evidence={','.join(counter) if counter else 'NONE'}",
            f"missing_evidence={','.join(missing) if missing else 'NONE'}",
            f"next_required_evidence={','.join(next_required) if next_required else 'NONE'}",
            f"lifecycle={stage}", f"maturity={maturity}", f"setup_quality={quality:.2f}",
        ],
    }
    return EngineResult("E6", NAME, maturity == "MATURE", quality, output, tuple(reasons))


def analyze_e6(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """Form and grade a setup thesis without making the entry decision."""
    bars = list(snapshot.get("bars") or [])
    if len(bars) < MIN_BARS:
        return _result("WAIT", "NONE", "NEUTRAL", "UNRESOLVED", "UNRESOLVED", "NO_SETUP: insufficient closed-candle history", 0.0, [], [f"CLOSED_CANDLES_BELOW_MINIMUM={MIN_BARS}"], ["sufficient_closed_candle_data"], ["more closed candles"], ["history remains insufficient"], [], [])
    try:
        atr = _atr(bars)
        if atr <= 0:
            raise ValueError("invalid atr")
        for bar in bars[-MIN_BARS:]:
            for key in ("open", "high", "low", "close"):
                float(bar[key])
    except (KeyError, TypeError, ValueError):
        return _result("WAIT", "NONE", "NEUTRAL", "UNRESOLVED", "UNRESOLVED", "NO_SETUP: invalid market data", 0.0, [], ["INVALID_MARKET_DATA"], ["valid_ohlc_data"], ["valid closed candle"], ["valid market data"], [], [])

    e1, e2, e3, e4, e5 = (_payload(upstream, n) for n in ("E1", "E2", "E3", "E4", "E5"))
    direction, supporting, counter, direction_source = _direction(e1, e2, e3, e4)
    event, terminal, pending, event_age = _auction(e4)
    long_space, short_space, explicit_location_constraint = _location(e5)
    opportunity = _text(e2.get("finding", e2.get("state", "")))
    e3_finding = _text(e3.get("finding", e3.get("structure_state")))
    e3_internal = _text(e3.get("internal_state", e3.get("internal_count_state")))

    if event:
        supporting.append(f"E4_EVENT={event}")
        supporting.append(f"E4_EVENT_AGE_BARS={event_age}")
    if pending and not terminal:
        counter.append("LIQUIDITY_EVENT_PENDING")
    if "MIXED" in e3_finding or "MIXED" in e3_internal:
        counter.append("STRUCTURE_MIXED")
    if "UNRESOLVED" in opportunity or "UNPROVEN" in opportunity:
        counter.append("OPPORTUNITY_MATURITY_UNPROVEN")
    if long_space or short_space:
        supporting += [f"STRUCTURAL_SPACE_LONG_ATR={long_space:.3f}", f"STRUCTURAL_SPACE_SHORT_ATR={short_space:.3f}"]
    if explicit_location_constraint:
        counter.append("LOCATION_CONSTRAINT")

    body, rng, dclose, candle_pos = _candle(bars, atr, direction)
    supporting += [f"CURRENT_CANDLE_BODY_ATR={body:.3f}", f"CURRENT_CANDLE_RANGE_ATR={rng:.3f}", f"CURRENT_CANDLE_DIRECTIONAL_CLOSE={dclose}", f"CURRENT_CANDLE_CLOSE_POSITION={candle_pos:.3f}"]

    formations, rejected = _candidate_scan(bars, atr, direction, e3, e4)
    counter = list(dict.fromkeys(counter))
    formations.sort(key=lambda x: (x.get("strength", 0), x.get("price_response", False)), reverse=True)
    candidates = [x["name"] for x in formations]

    if not formations:
        missing = ["setup_specific_price_formation"]
        next_required = ["a valid setup-specific closed-candle sequence"]
        if direction == "NEUTRAL":
            next_required.insert(0, "directional context convergence")
        if event and not terminal:
            next_required.append("terminal liquidity acceptance/rejection")
        if direction == "BUY" and long_space < MIN_SPACE_ATR:
            next_required.append("usable long structural space")
        if direction == "SELL" and short_space < MIN_SPACE_ATR:
            next_required.append("usable short structural space")
        if "OPPORTUNITY_MATURITY_UNPROVEN" in counter:
            next_required.append("closed-candle opportunity acceptance/follow-through")
        return _result("WAIT", "NONE", direction, "SEARCHING", "UNRESOLVED", "NO_VALID_SETUP_FORMED" if direction == "NEUTRAL" else f"{direction}: setup not yet formed; remain patient", 10.0 if direction != "NEUTRAL" else 0.0, supporting, counter, missing, next_required, ["setup-specific formation failure", "directional or structural thesis invalidation"], candidates, rejected)

    selected = formations[0]
    setup = selected["name"]
    strength = float(selected.get("strength", 0.0))
    supporting += [f"FORMATION={x}" for x in selected["evidence"]]

    missing: list[str] = []
    next_required: list[str] = []
    direction_space = short_space if direction == "SELL" else long_space
    if direction_space < MIN_SPACE_ATR:
        missing.append("usable_structural_space")
        next_required.append("price relocation into usable structural space")
    if event and not terminal:
        missing.append("terminal_liquidity_auction_confirmation")
        next_required.append("terminal liquidity acceptance/rejection")
    if "OPPORTUNITY_MATURITY_UNPROVEN" in counter:
        missing.append("opportunity_maturity")
        next_required.append("closed-candle opportunity acceptance/follow-through")
    if "DIRECTIONAL_EVIDENCE_CONFLICT" in counter:
        missing.append("directional_evidence_convergence")
        next_required.append("closed-candle directional convergence")
    if "STRUCTURE_MIXED" in counter:
        missing.append("structural_alignment")
        next_required.append("clear protected-level structural confirmation")
    if setup == "LIQUIDITY_REVERSAL" and not selected.get("price_response", False):
        missing.append("directional_rejection_close")
        next_required.append("directional closed-candle rejection")

    hard_conflict = any(x in counter for x in ("EXTERNAL_STRUCTURE_COUNTERTREND", "FAILED_STRUCTURE_BREAK"))
    if hard_conflict:
        state, stage, maturity, quality = "WAIT", "CONFLICTED", "UNRESOLVED", min(55.0, strength)
        thesis = f"{direction}_{setup}: candidate exists, but structural counter-evidence blocks the thesis"
    elif missing:
        state, stage, maturity, quality = "WAIT", "DEVELOPING", "DEVELOPING", min(78.0, strength)
        thesis = f"{direction}_{setup}: formation is present; {', '.join(missing)} remains unresolved"
    else:
        state, stage, maturity, quality = "MATURE", "TRIGGER_PENDING", "MATURE", min(92.0, strength)
        thesis = f"{direction}_{setup}: setup formation is mature; E7 must independently prove entry confirmation"

    next_required.append("E7 closed-candle entry confirmation")
    invalidation = [
        "setup-specific formation failure on a subsequent closed candle",
        "protected-level break against the setup thesis",
        "auction response changes from acceptance/rejection to contrary acceptance",
        "directional evidence becomes structurally contradictory",
    ]
    return _result(state, setup, direction, stage, maturity, thesis, quality, supporting, counter, missing, next_required, invalidation, candidates, rejected, strength)
