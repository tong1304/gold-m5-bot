from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Setup Brain"
QUESTION = "What setup is forming, in what direction, and at what stage?"
ARCHITECTURE = "E6_PROFESSIONAL_SETUP_FORMATION_BRAIN_V6"
VERSION = "6.0"
MIN_BARS = 60
ATR_PERIOD = 14
EMA_FAST = 20
EMA_SLOW = 50
BREAKOUT_LOOKBACK = 12
PULLBACK_LOOKBACK = 6


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


def _direction(e1: dict[str, Any], e2: dict[str, Any], e3: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    supporting: list[str] = []
    counter: list[str] = []
    values = [
        _norm(e2.get("direction")),
        _norm(e2.get("opportunity_direction")),
        _norm(e1.get("directional_pressure", e1.get("pressure"))),
    ]
    usable = [v for v in values if v != "NEUTRAL"]
    direction = usable[0] if usable and all(v == usable[0] for v in usable) else "NEUTRAL"
    if direction == "NEUTRAL":
        counter.append("NO_DIRECTIONAL_CONTEXT")
    else:
        supporting.append(f"DIRECTIONAL_CONTEXT={direction}")

    finding = _text(e3.get("finding", e3.get("structure_state")))
    internal = _text(e3.get("internal_state", e3.get("internal_count_state")))
    external = _text(e3.get("external_state", e3.get("external_count_state")))
    if "MIXED" in finding or "MIXED" in internal:
        counter.append("STRUCTURE_MIXED")
    if (direction == "BUY" and external == "DOWN") or (direction == "SELL" and external == "UP"):
        counter.append("EXTERNAL_STRUCTURE_COUNTERTREND")
    if "FAILED_BOS" in finding:
        counter.append("FAILED_STRUCTURE_BREAK")
    return direction, supporting, list(dict.fromkeys(counter))


def _auction(e4: dict[str, Any]) -> tuple[str, bool, bool]:
    state = _text(e4.get("auction_state", e4.get("state")))
    event = _text(e4.get("event", e4.get("finding")))
    terminal = state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "REJECTED"} or "TERMINAL" in state
    pending = state == "PENDING" or "PENDING" in _text(e4)
    return event, terminal, pending


def _location(e5: dict[str, Any]) -> tuple[bool, float, float]:
    long_space = float(e5.get("available_space_atr_long", 0.0) or 0.0)
    short_space = float(e5.get("available_space_atr_short", 0.0) or 0.0)
    text = _text(e5)
    constrained = any(x in text for x in ("LOCATION_CONSTRAINT", "SPACE_CONSTRAINED", "EXTENSION_RISK"))
    if long_space > 0 or short_space > 0:
        constrained = constrained or max(long_space, short_space) < 0.75
    return constrained, long_space, short_space


def _candle(bars: list[dict[str, Any]], atr: float, direction: str) -> tuple[float, float, bool]:
    b = bars[-1]
    o, h, l, c = map(float, (b["open"], b["high"], b["low"], b["close"]))
    rng = max(h - l, 1e-9)
    pos = (c - l) / rng
    directional = pos >= 0.65 if direction == "BUY" else pos <= 0.35 if direction == "SELL" else False
    return abs(c - o) / max(atr, 1e-9), rng / max(atr, 1e-9), directional


def _candidate_scan(bars: list[dict[str, Any]], atr: float, direction: str, e3: dict[str, Any], e4: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    names = ["TREND_PULLBACK", "BREAKOUT_RETEST", "BREAKOUT", "IMPULSE_CONTINUATION"]
    if direction == "NEUTRAL":
        return [], [f"{n}:direction_missing" for n in names]

    closes = [float(b["close"]) for b in bars]
    ema20, ema50, price = _ema(closes, EMA_FAST), _ema(closes, EMA_SLOW), closes[-1]
    recent = bars[-PULLBACK_LOOKBACK:]
    touched = (min(float(b["low"]) for b in recent) <= ema20 + 0.25 * atr) if direction == "BUY" else (max(float(b["high"]) for b in recent) >= ema20 - 0.25 * atr)
    aligned = price > ema20 > ema50 if direction == "BUY" else price < ema20 < ema50
    held = price >= ema20 if direction == "BUY" else price <= ema20
    mixed = "MIXED" in _text(e3)

    found: list[dict[str, Any]] = []
    rejected: list[str] = []

    missing: list[str] = []
    if not aligned: missing.append("trend_alignment")
    if not touched: missing.append("retracement_behavior")
    if not held: missing.append("reclaim_or_hold")
    if aligned and touched and held and not mixed and abs(price - ema20) <= 1.5 * atr:
        found.append({"name": "TREND_PULLBACK", "evidence": ["EMA20_EMA50_ALIGNMENT", "RETRACEMENT_TO_EMA20", "RECLAIM_OR_HOLD_EMA20"]})
    else:
        rejected.append("TREND_PULLBACK:" + ("structure_mixed" if mixed else "formation_incomplete") + (":" + ",".join(missing) if missing else ""))

    prior = bars[-(BREAKOUT_LOOKBACK + 1):-1]
    rh, rl = max(float(b["high"]) for b in prior), min(float(b["low"]) for b in prior)
    last = bars[-1]
    o, h, l, c = map(float, (last["open"], last["high"], last["low"], last["close"]))
    broke = c > rh if direction == "BUY" else c < rl
    expansion = h - l >= 0.8 * atr or abs(c - o) >= 0.6 * atr
    pos = (c - l) / max(h - l, 1e-9)
    dclose = pos >= 0.65 if direction == "BUY" else pos <= 0.35
    miss = []
    if not broke: miss.append("closed_break_of_range")
    if not expansion: miss.append("volatility_expansion")
    if not dclose: miss.append("directional_close")
    if broke and expansion and dclose:
        found.append({"name": "BREAKOUT", "evidence": ["CLOSED_RANGE_BREAK", "VOLATILITY_EXPANSION", "DIRECTIONAL_CLOSE"]})
    else:
        rejected.append("BREAKOUT:formation_incomplete:" + ",".join(miss))

    before = bars[-(BREAKOUT_LOOKBACK + 3):-3]
    level = max(float(b["high"]) for b in before) if direction == "BUY" else min(float(b["low"]) for b in before)
    prior_break = float(bars[-3]["close"]) > level if direction == "BUY" else float(bars[-3]["close"]) < level
    retest = any(float(b["low"]) <= level + 0.25 * atr for b in bars[-2:]) if direction == "BUY" else any(float(b["high"]) >= level - 0.25 * atr for b in bars[-2:])
    hold = c >= level if direction == "BUY" else c <= level
    miss = []
    if not prior_break: miss.append("prior_breakout")
    if not retest: miss.append("retest")
    if not hold: miss.append("retest_hold")
    if prior_break and retest and hold:
        found.append({"name": "BREAKOUT_RETEST", "evidence": ["PRIOR_CLOSED_BREAKOUT", "LEVEL_RETEST", "RETEST_HOLD"]})
    else:
        rejected.append("BREAKOUT_RETEST:sequence_incomplete:" + ",".join(miss))

    recent4 = bars[-4:]
    bodies = [abs(float(b["close"]) - float(b["open"])) for b in recent4[:3]]
    idx = max(range(len(bodies)), key=bodies.__getitem__)
    impulse = recent4[idx]
    impulse_dir = "BUY" if float(impulse["close"]) > float(impulse["open"]) else "SELL"
    follow_dir = "BUY" if c > o else "SELL"
    if bodies[idx] >= 0.8 * atr and impulse_dir == direction and follow_dir == direction and dclose:
        found.append({"name": "IMPULSE_CONTINUATION", "evidence": ["DIRECTIONAL_PRIOR_IMPULSE", "DIRECTIONAL_FOLLOW_THROUGH"]})
    else:
        rejected.append("IMPULSE_CONTINUATION:sequence_incomplete")

    event = _text(e4.get("event", e4.get("finding")))
    if any(x in event for x in ("SWEEP", "REJECTION", "ACCEPTANCE", "FAILED_BREAK")):
        rejected.append("LIQUIDITY_EVENT_REQUIRES_E4_CONFIRMATION")
    return found, rejected


def _result(state: str, setup: str, direction: str, stage: str, maturity: str, thesis: str, quality: float, supporting: list[str], counter: list[str], missing: list[str], next_required: list[str], invalidation: list[str], candidates: list[str], rejected: list[str]) -> EngineResult:
    quality = max(0.0, min(100.0, quality))
    reasons = list(dict.fromkeys(counter + ([] if maturity == "MATURE" else ["SETUP_NOT_MATURE"])))
    output = {
        "architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION,
        "role": "SETUP_ANALYST", "reasoning_role": "SETUP_FORMATION_REASONER",
        "decision_authority": "E9", "trade_decision_authority": False,
        "state": state, "setup": setup, "setup_family": setup, "direction": direction,
        "stage": stage, "lifecycle": stage, "maturity": maturity, "thesis": thesis,
        "setup_quality": round(quality, 2), "candidate_setups": candidates, "rejected_setups": rejected,
        "supporting_evidence": list(dict.fromkeys(supporting)), "counter_evidence": list(dict.fromkeys(counter)),
        "missing_evidence": list(dict.fromkeys(missing)), "next_required_evidence": list(dict.fromkeys(next_required)),
        "invalidation": list(dict.fromkeys(invalidation)),
        "observations": [
            f"candidate_setups={','.join(candidates) if candidates else 'NONE'}",
            f"rejected_setups={len(rejected)}", f"supporting_evidence={','.join(supporting) if supporting else 'NONE'}",
            f"counter_evidence={','.join(counter) if counter else 'NONE'}", f"missing_evidence={','.join(missing) if missing else 'NONE'}",
            f"next_required_evidence={','.join(next_required) if next_required else 'NONE'}",
            f"lifecycle={stage}", f"maturity={maturity}", f"setup_quality={quality:.2f}",
        ],
    }
    return EngineResult("E6", NAME, maturity == "MATURE", quality, output, tuple(reasons))


def analyze_e6(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """E6 identifies, ranks and invalidates setup formations. It never confirms entry or decides trades."""
    bars = list(snapshot.get("bars") or [])
    if len(bars) < MIN_BARS:
        return _result("WAIT", "NONE", "NEUTRAL", "UNRESOLVED", "UNRESOLVED", "NO_SETUP: insufficient closed-candle history", 0.0, [], [f"CLOSED_CANDLES_BELOW_MINIMUM={MIN_BARS}"], ["sufficient_closed_candle_data"], ["more closed candles"], ["history remains insufficient"], [], [])
    try:
        atr = _atr(bars)
        if atr <= 0: raise ValueError("invalid atr")
    except (KeyError, TypeError, ValueError):
        return _result("WAIT", "NONE", "NEUTRAL", "UNRESOLVED", "UNRESOLVED", "NO_SETUP: invalid market data", 0.0, [], ["INVALID_MARKET_DATA"], ["valid_ohlc_data"], ["valid closed candle"], ["valid market data"], [], [])

    e1, e2, e3, e4, e5 = (_payload(upstream, n) for n in ("E1", "E2", "E3", "E4", "E5"))
    direction, supporting, counter = _direction(e1, e2, e3)
    event, terminal, pending = _auction(e4)
    constrained, long_space, short_space = _location(e5)
    opportunity = _text(e2)

    if event: supporting.append(f"E4_EVENT={event}")
    if pending and not terminal: counter.append("LIQUIDITY_EVENT_NOT_TERMINALLY_CONFIRMED")
    if not terminal and event: supporting.append("AUCTION_STATE=PENDING")
    if constrained: counter.append("LOCATION_CONSTRAINT")
    if "UNRESOLVED" in opportunity or "UNPROVEN" in opportunity: counter.append("OPPORTUNITY_MATURITY_UNPROVEN")
    if long_space or short_space:
        supporting += [f"STRUCTURAL_SPACE_LONG_ATR={long_space:.3f}", f"STRUCTURAL_SPACE_SHORT_ATR={short_space:.3f}"]

    body, rng, dclose = _candle(bars, atr, direction)
    supporting += [f"CURRENT_CANDLE_BODY_ATR={body:.3f}", f"CURRENT_CANDLE_RANGE_ATR={rng:.3f}", f"CURRENT_CANDLE_DIRECTIONAL_CLOSE={dclose}"]
    formations, rejected = _candidate_scan(bars, atr, direction, e3, e4)
    candidates = [x["name"] for x in formations]
    counter = list(dict.fromkeys(counter))

    # E6 must report the actual formation map even when upstream vetoes prevent maturity.
    # This is the key professional distinction: candidate != mature != executable.
    if not formations:
        missing = ["setup_specific_price_formation"]
        next_required = ["a valid setup-specific closed-candle sequence"]
        if direction == "NEUTRAL": next_required.append("directional context convergence")
        if not terminal: next_required.append("terminal liquidity acceptance/rejection")
        if constrained: next_required.append("usable structural space")
        if "UNPROVEN" in opportunity or "UNRESOLVED" in opportunity: next_required.append("closed-candle opportunity acceptance/follow-through")
        thesis = "NO_VALID_SETUP_FORMED" if direction == "NEUTRAL" else f"{direction}: no complete setup family; remain in search"
        return _result("WAIT", "NONE", direction, "SEARCHING", "UNRESOLVED", thesis, 15.0 if direction != "NEUTRAL" else 0.0, supporting, counter, missing, next_required, ["price sequence invalidates the candidate", "directional context changes"], candidates, rejected)

    priority = {"BREAKOUT_RETEST": 0, "TREND_PULLBACK": 1, "BREAKOUT": 2, "IMPULSE_CONTINUATION": 3}
    selected = sorted(formations, key=lambda x: priority.get(x["name"], 99))[0]
    setup = selected["name"]
    supporting += [f"FORMATION={x}" for x in selected["evidence"]]

    hard = any(x in counter for x in ("STRUCTURE_MIXED", "EXTERNAL_STRUCTURE_COUNTERTREND", "FAILED_STRUCTURE_BREAK", "LOCATION_CONSTRAINT"))
    incomplete = any(x in counter for x in ("LIQUIDITY_EVENT_NOT_TERMINALLY_CONFIRMED", "OPPORTUNITY_MATURITY_UNPROVEN"))
    missing: list[str] = []
    next_required: list[str] = []
    if not terminal:
        missing.append("terminal_liquidity_auction_confirmation"); next_required.append("terminal liquidity acceptance/rejection")
    if "OPPORTUNITY_MATURITY_UNPROVEN" in counter:
        missing.append("opportunity_maturity"); next_required.append("closed-candle opportunity acceptance/follow-through")
    if constrained:
        missing.append("usable_structural_space"); next_required.append("price relocation into usable structural space")

    if hard:
        state, stage, maturity, quality = "WAIT", "CONFLICTED", "UNRESOLVED", 35.0
        thesis = f"{direction}_{setup}: candidate exists but counter-evidence blocks maturation"
    elif incomplete:
        state, stage, maturity, quality = "WAIT", "DEVELOPING", "DEVELOPING", 58.0
        thesis = f"{direction}_{setup}: candidate formation is present; upstream auction/opportunity evidence is incomplete"
    else:
        state, stage, maturity, quality = "MATURE", "TRIGGER_PENDING", "MATURE", 82.0
        thesis = f"{direction}_{setup}: formation is established; E7 must independently prove entry"

    next_required.append("E7 closed-candle entry confirmation")
    invalidation = ["setup-specific formation failure on a closed candle", "directional or structural conflict invalidates the thesis"]
    return _result(state, setup, direction, stage, maturity, thesis, quality, supporting, counter, missing, next_required, invalidation, candidates, rejected)
