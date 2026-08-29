from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Setup Brain"
QUESTION = "What setup is forming, in what direction, and at what stage?"
ARCHITECTURE = "E6_PROFESSIONAL_SETUP_FORMATION_BRAIN_V5"
VERSION = "5.0"
MIN_BARS = 60
ATR_PERIOD = 14
EMA_FAST = 20
EMA_SLOW = 50
BREAKOUT_LOOKBACK = 12
PULLBACK_LOOKBACK = 6


def _payload(upstream: dict[str, EngineResult], name: str) -> dict[str, Any]:
    result = upstream.get(name)
    return result.output if result else {}


def _norm(value: Any) -> str:
    text = str(value or "").upper().strip()
    if text in {"UP", "BULLISH", "BUY", "LONG", "TREND_UP"}:
        return "BUY"
    if text in {"DOWN", "BEARISH", "SELL", "SHORT", "TREND_DOWN"}:
        return "SELL"
    return "NEUTRAL"


def _atr(bars: list[dict[str, Any]], period: int = ATR_PERIOD) -> float:
    if len(bars) < 2:
        return 0.0
    sample = bars[-(period + 1):]
    true_ranges: list[float] = []
    for i, bar in enumerate(sample):
        high = float(bar["high"])
        low = float(bar["low"])
        if i == 0:
            true_ranges.append(high - low)
        else:
            previous_close = float(sample[i - 1]["close"])
            true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return mean(true_ranges[-period:]) if true_ranges else 0.0


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    value = values[0]
    for item in values[1:]:
        value = alpha * item + (1.0 - alpha) * value
    return value


def _direction_context(e1: dict[str, Any], e2: dict[str, Any], e3: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    supporting: list[str] = []
    counter: list[str] = []

    candidates = [
        _norm(e2.get("direction")),
        _norm(e2.get("opportunity_direction")),
        _norm(e1.get("directional_pressure", e1.get("pressure"))),
    ]
    usable = [value for value in candidates if value != "NEUTRAL"]
    direction = usable[0] if usable and all(value == usable[0] for value in usable) else "NEUTRAL"

    if direction == "NEUTRAL":
        counter.append("NO_DIRECTIONAL_CONTEXT")
    else:
        supporting.append(f"DIRECTIONAL_CONTEXT={direction}")

    finding = str(e3.get("finding", e3.get("structure_state", ""))).upper()
    internal = str(e3.get("internal_state", e3.get("internal_count_state", ""))).upper()
    external = str(e3.get("external_state", e3.get("external_count_state", ""))).upper()
    slope = str(e3.get("slope_context", "")).upper()

    if "MIXED" in finding or "MIXED" in internal:
        counter.append("STRUCTURE_MIXED")
    if direction == "BUY" and external == "DOWN" or direction == "SELL" and external == "UP":
        counter.append("EXTERNAL_STRUCTURE_COUNTERTREND")
    if "FAILED_BOS" in finding:
        counter.append("FAILED_STRUCTURE_BREAK")
    if slope in {"UP", "DOWN"}:
        supporting.append(f"E3_SLOPE={slope}")
        slope_direction = "BUY" if slope == "UP" else "SELL"
        if direction != "NEUTRAL" and slope_direction != direction:
            counter.append("STRUCTURE_SLOPE_CONFLICT")

    return direction, supporting, list(dict.fromkeys(counter))


def _auction_state(e4: dict[str, Any]) -> tuple[bool, bool, str]:
    text = str(e4).upper()
    state = str(e4.get("auction_state", e4.get("state", ""))).upper()
    terminal = state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "REJECTED"} or "TERMINAL" in state
    pending = state == "PENDING" or "PENDING" in text
    event = str(e4.get("event", e4.get("finding", ""))).upper()
    return terminal, pending, event


def _location(e5: dict[str, Any]) -> tuple[bool, float, float]:
    long_space = float(e5.get("available_space_atr_long", 0.0) or 0.0)
    short_space = float(e5.get("available_space_atr_short", 0.0) or 0.0)
    text = str(e5).upper()
    constrained = any(token in text for token in ("LOCATION_CONSTRAINT", "SPACE_CONSTRAINED", "EXTENSION_RISK"))
    if long_space > 0 or short_space > 0:
        constrained = constrained or max(long_space, short_space) < 0.75
    return constrained, long_space, short_space


def _candle(bars: list[dict[str, Any]], atr: float, direction: str) -> dict[str, float | bool]:
    bar = bars[-1]
    open_price = float(bar["open"])
    high = float(bar["high"])
    low = float(bar["low"])
    close = float(bar["close"])
    candle_range = max(high - low, 1e-9)
    close_position = (close - low) / candle_range
    return {
        "body_atr": abs(close - open_price) / max(atr, 1e-9),
        "range_atr": candle_range / max(atr, 1e-9),
        "directional_close": close_position >= 0.65 if direction == "BUY" else close_position <= 0.35 if direction == "SELL" else False,
    }


def _formation_scan(bars: list[dict[str, Any]], atr: float, direction: str, e3: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    if direction == "NEUTRAL":
        return [], [
            "TREND_PULLBACK:direction_missing",
            "BREAKOUT:direction_missing",
            "BREAKOUT_RETEST:direction_missing",
            "IMPULSE_CONTINUATION:direction_missing",
        ]

    closes = [float(bar["close"]) for bar in bars]
    ema20 = _ema(closes, EMA_FAST)
    ema50 = _ema(closes, EMA_SLOW)
    price = closes[-1]
    recent = bars[-PULLBACK_LOOKBACK:]
    touched = min(float(bar["low"]) for bar in recent) <= ema20 + 0.25 * atr if direction == "BUY" else max(float(bar["high"]) for bar in recent) >= ema20 - 0.25 * atr
    aligned = price > ema20 > ema50 if direction == "BUY" else price < ema20 < ema50
    held = price >= ema20 if direction == "BUY" else price <= ema20
    mixed = "MIXED" in str(e3).upper()

    formations: list[dict[str, Any]] = []
    rejected: list[str] = []

    pullback_missing = []
    if not aligned:
        pullback_missing.append("trend_alignment")
    if not touched:
        pullback_missing.append("retracement_behavior")
    if not held:
        pullback_missing.append("reclaim_or_hold")
    if aligned and touched and held and not mixed and abs(price - ema20) <= 1.5 * atr:
        formations.append({"name": "TREND_PULLBACK", "evidence": ["EMA20_EMA50_ALIGNMENT", "RETRACEMENT_TO_EMA20", "RECLAIM_OR_HOLD_EMA20"], "missing": []})
    else:
        rejected.append("TREND_PULLBACK:" + ("structure_mixed" if mixed else "formation_incomplete") + (":" + ",".join(pullback_missing) if pullback_missing else ""))

    prior = bars[-(BREAKOUT_LOOKBACK + 1):-1]
    range_high = max(float(bar["high"]) for bar in prior)
    range_low = min(float(bar["low"]) for bar in prior)
    last = bars[-1]
    open_price, high, low, close = map(float, (last["open"], last["high"], last["low"], last["close"]))
    broke = close > range_high if direction == "BUY" else close < range_low
    expansion = high - low >= 0.8 * atr or abs(close - open_price) >= 0.6 * atr
    close_position = (close - low) / max(high - low, 1e-9)
    directional_close = close_position >= 0.65 if direction == "BUY" else close_position <= 0.35
    breakout_missing = []
    if not broke:
        breakout_missing.append("closed_break_of_range")
    if not expansion:
        breakout_missing.append("volatility_expansion")
    if not directional_close:
        breakout_missing.append("directional_close")
    if broke and expansion and directional_close:
        formations.append({"name": "BREAKOUT", "evidence": ["CLOSED_RANGE_BREAK", "VOLATILITY_EXPANSION", "DIRECTIONAL_CLOSE"], "missing": []})
    else:
        rejected.append("BREAKOUT:formation_incomplete:" + ",".join(breakout_missing))

    before = bars[-(BREAKOUT_LOOKBACK + 3):-3]
    level = max(float(bar["high"]) for bar in before) if direction == "BUY" else min(float(bar["low"]) for bar in before)
    prior_break_bar = bars[-3]
    retest_bars = bars[-2:]
    prior_break = float(prior_break_bar["close"]) > level if direction == "BUY" else float(prior_break_bar["close"]) < level
    touched_level = any(float(bar["low"]) <= level + 0.25 * atr for bar in retest_bars) if direction == "BUY" else any(float(bar["high"]) >= level - 0.25 * atr for bar in retest_bars)
    held_level = close >= level if direction == "BUY" else close <= level
    retest_missing = []
    if not prior_break:
        retest_missing.append("prior_breakout")
    if not touched_level:
        retest_missing.append("retest")
    if not held_level:
        retest_missing.append("retest_hold")
    if prior_break and touched_level and held_level:
        formations.append({"name": "BREAKOUT_RETEST", "evidence": ["PRIOR_CLOSED_BREAKOUT", "LEVEL_RETEST", "RETEST_HOLD"], "missing": []})
    else:
        rejected.append("BREAKOUT_RETEST:sequence_incomplete:" + ",".join(retest_missing))

    recent4 = bars[-4:]
    bodies = [abs(float(bar["close"]) - float(bar["open"])) for bar in recent4[:3]]
    largest_index = max(range(len(bodies)), key=bodies.__getitem__)
    impulse = recent4[largest_index]
    impulse_direction = "BUY" if float(impulse["close"]) > float(impulse["open"]) else "SELL"
    follow_direction = "BUY" if close > open_price else "SELL"
    impulse_ok = bodies[largest_index] >= 0.8 * atr and impulse_direction == direction
    follow_ok = follow_direction == direction and directional_close
    if impulse_ok and follow_ok:
        formations.append({"name": "IMPULSE_CONTINUATION", "evidence": ["DIRECTIONAL_PRIOR_IMPULSE", "DIRECTIONAL_FOLLOW_THROUGH"], "missing": []})
    else:
        rejected.append("IMPULSE_CONTINUATION:sequence_incomplete")

    return formations, rejected


def _result(state: str, setup: str, direction: str, stage: str, maturity: str, thesis: str, quality: float,
            supporting: list[str], counter: list[str], missing: list[str], next_required: list[str],
            invalidation: list[str], candidates: list[str], rejected: list[str]) -> EngineResult:
    quality = max(0.0, min(100.0, quality))
    reasons = list(dict.fromkeys(counter + ([] if maturity == "MATURE" else ["SETUP_NOT_MATURE"])))
    output = {
        "architecture": ARCHITECTURE,
        "version": VERSION,
        "question": QUESTION,
        "role": "SETUP_ANALYST",
        "reasoning_role": "SETUP_FORMATION_REASONER",
        "decision_authority": "E9",
        "trade_decision_authority": False,
        "state": state,
        "setup": setup,
        "setup_family": setup,
        "direction": direction,
        "stage": stage,
        "lifecycle": stage,
        "maturity": maturity,
        "thesis": thesis,
        "setup_quality": round(quality, 2),
        "candidate_setups": candidates,
        "rejected_setups": rejected,
        "supporting_evidence": list(dict.fromkeys(supporting)),
        "counter_evidence": list(dict.fromkeys(counter)),
        "missing_evidence": list(dict.fromkeys(missing)),
        "next_required_evidence": list(dict.fromkeys(next_required)),
        "invalidation": list(dict.fromkeys(invalidation)),
        "observations": [
            f"candidate_setups={','.join(candidates) if candidates else 'NONE'}",
            f"rejected_setups={len(rejected)}",
            f"supporting_evidence={','.join(supporting) if supporting else 'NONE'}",
            f"counter_evidence={','.join(counter) if counter else 'NONE'}",
            f"missing_evidence={','.join(missing) if missing else 'NONE'}",
            f"next_required_evidence={','.join(next_required) if next_required else 'NONE'}",
            f"lifecycle={stage}",
            f"maturity={maturity}",
            f"setup_quality={quality:.2f}",
        ],
    }
    return EngineResult("E6", NAME, maturity == "MATURE", quality, output, tuple(reasons))


def analyze_e6(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """Reason about setup formation only. E7 owns entry confirmation; E9 owns decisions."""
    bars = list(snapshot.get("bars") or [])
    if len(bars) < MIN_BARS:
        return _result("WAIT", "NONE", "NEUTRAL", "UNRESOLVED", "UNRESOLVED", "NO_SETUP: insufficient closed-candle history", 0.0, [], [f"CLOSED_CANDLES_BELOW_MINIMUM={MIN_BARS}"], ["sufficient_closed_candle_data"], ["more closed candles"], ["new closed candle may change evidence"], [], [])

    try:
        atr = _atr(bars)
        if atr <= 0:
            raise ValueError("invalid atr")
    except (KeyError, TypeError, ValueError):
        return _result("WAIT", "NONE", "NEUTRAL", "UNRESOLVED", "UNRESOLVED", "NO_SETUP: invalid market data", 0.0, [], ["INVALID_MARKET_DATA"], ["valid_ohlc_data"], ["valid closed candle"], ["new valid closed candle"], [], [])

    e1 = _payload(upstream, "E1")
    e2 = _payload(upstream, "E2")
    e3 = _payload(upstream, "E3")
    e4 = _payload(upstream, "E4")
    e5 = _payload(upstream, "E5")

    direction, supporting, counter = _direction_context(e1, e2, e3)
    terminal_auction, pending_auction, auction_event = _auction_state(e4)
    location_constrained, long_space, short_space = _location(e5)
    opportunity_text = str(e2).upper()

    if pending_auction and any(token in str(e4).upper() for token in ("SWEEP", "REJECTION", "ACCEPTANCE", "FAILED_BREAK")):
        counter.append("LIQUIDITY_EVENT_NOT_TERMINALLY_CONFIRMED")
    if not terminal_auction and auction_event:
        supporting.append(f"E4_EVENT={auction_event}")
    if location_constrained:
        counter.append("LOCATION_CONSTRAINT")
    if "UNRESOLVED" in opportunity_text or "UNPROVEN" in opportunity_text:
        counter.append("OPPORTUNITY_MATURITY_UNPROVEN")
    if long_space > 0 or short_space > 0:
        supporting.append(f"STRUCTURAL_SPACE_LONG_ATR={long_space:.3f}")
        supporting.append(f"STRUCTURAL_SPACE_SHORT_ATR={short_space:.3f}")

    candle = _candle(bars, atr, direction)
    supporting.extend([
        f"CURRENT_CANDLE_BODY_ATR={candle['body_atr']:.3f}",
        f"CURRENT_CANDLE_RANGE_ATR={candle['range_atr']:.3f}",
        f"CURRENT_CANDLE_DIRECTIONAL_CLOSE={candle['directional_close']}",
    ])
    counter = list(dict.fromkeys(counter))

    formations, rejected = _formation_scan(bars, atr, direction, e3)
    candidates = [formation["name"] for formation in formations]

    # A candidate is not mature merely because price resembles a pattern. E6 requires
    # the setup's own sequence plus coherent upstream context and usable location.
    if not formations:
        missing = ["setup_specific_price_formation"]
        if "NO_DIRECTIONAL_CONTEXT" in counter:
            missing.append("directional_context_convergence")
        next_required = [
            "setup-specific closed-candle price sequence",
            "evidence that survives E3-E5 counter-evidence",
            "setup maturation before E7 confirmation",
        ]
        thesis = f"{direction}: context exists, but no setup-specific formation is complete" if direction != "NEUTRAL" else "NO_VALID_SETUP_FORMED"
        return _result("WAIT", "NONE", direction, "SEARCHING", "UNRESOLVED", thesis, 20.0 if direction != "NEUTRAL" else 0.0, supporting, counter, missing, next_required, ["formation fails to develop", "direction or structure changes"], candidates, rejected)

    # Prefer the most complete formation: retest > pullback > breakout > impulse.
    priority = {"BREAKOUT_RETEST": 0, "TREND_PULLBACK": 1, "BREAKOUT": 2, "IMPULSE_CONTINUATION": 3}
    formation = sorted(formations, key=lambda item: priority.get(item["name"], 99))[0]
    setup = formation["name"]
    supporting.extend(f"FORMATION={item}" for item in formation["evidence"])

    hard_conflict = any(token in counter for token in ("STRUCTURE_SLOPE_CONFLICT", "EXTERNAL_STRUCTURE_COUNTERTREND", "FAILED_STRUCTURE_BREAK", "LOCATION_CONSTRAINT"))
    unresolved_context = any(token in counter for token in ("NO_DIRECTIONAL_CONTEXT", "LIQUIDITY_EVENT_NOT_TERMINALLY_CONFIRMED", "OPPORTUNITY_MATURITY_UNPROVEN"))

    missing = list(formation.get("missing") or [])
    next_required: list[str] = []
    if not terminal_auction:
        missing.append("terminal_liquidity_auction_confirmation")
        next_required.append("terminal liquidity acceptance/rejection")
    if "OPPORTUNITY_MATURITY_UNPROVEN" in counter:
        missing.append("opportunity_maturity")
        next_required.append("closed-candle opportunity acceptance/follow-through")
    if location_constrained:
        missing.append("usable_structural_space")
        next_required.append("price relocation into usable structural space")

    if hard_conflict:
        state, stage, maturity = "WAIT", "CONFLICTED", "UNRESOLVED"
        thesis = f"{direction}_{setup}: formation exists, but counter-evidence prevents maturation"
        quality = 30.0
    elif unresolved_context:
        state, stage, maturity = "WAIT", "TESTING", "DEVELOPING"
        thesis = f"{direction}_{setup}: formation is developing; upstream confirmation is incomplete"
        quality = 52.0
    else:
        state, stage, maturity = "MATURE", "TRIGGER_PENDING", "MATURE"
        thesis = f"{direction}_{setup}: setup formation is established; entry confirmation remains downstream"
        quality = 78.0

    next_required.extend(["E7 closed-candle entry confirmation"])
    invalidation = ["setup-specific formation failure on a closed candle", "directional or structural conflict invalidates the thesis"]
    return _result(state, setup, direction, stage, maturity, thesis, quality, supporting, counter, list(dict.fromkeys(missing)), list(dict.fromkeys(next_required)), invalidation, candidates, rejected)
