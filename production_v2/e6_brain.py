from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Setup Brain"
QUESTION = "What setup is forming, in what direction, and at what stage?"
ARCHITECTURE = "E6_PROFESSIONAL_SETUP_FORMATION_BRAIN_V4"
VERSION = "4.0"
MIN_BARS = 60
ATR_PERIOD = 14
EMA_FAST = 20
EMA_SLOW = 50
BREAKOUT_LOOKBACK = 12
PULLBACK_LOOKBACK = 6


def _atr(bars: list[dict[str, Any]], period: int = ATR_PERIOD) -> float:
    if len(bars) < 2:
        return 0.0
    sample = bars[-(period + 1):]
    trs: list[float] = []
    for i, b in enumerate(sample):
        h, l = float(b["high"]), float(b["low"])
        if i == 0:
            trs.append(h - l)
        else:
            pc = float(sample[i - 1]["close"])
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return mean(trs[-period:]) if trs else 0.0


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    a = 2.0 / (period + 1.0)
    x = values[0]
    for v in values[1:]:
        x = a * v + (1.0 - a) * x
    return x


def _payload(upstream: dict[str, EngineResult], name: str) -> dict[str, Any]:
    r = upstream.get(name)
    return r.output if r else {}


def _norm(v: Any) -> str:
    s = str(v or "").upper().strip()
    if s in {"UP", "BULLISH", "BUY", "LONG", "TREND_UP"}: return "BUY"
    if s in {"DOWN", "BEARISH", "SELL", "SHORT", "TREND_DOWN"}: return "SELL"
    return "NEUTRAL"


def _direction_context(e1: dict[str, Any], e2: dict[str, Any], e3: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    support, counter = [], []
    d2 = _norm(e2.get("direction"))
    d1 = _norm(e1.get("directional_pressure", e1.get("pressure")))
    direction = d2 if d2 != "NEUTRAL" else d1
    if direction == "NEUTRAL":
        counter.append("NO_DIRECTIONAL_CONTEXT")
    else:
        support.append(f"DIRECTIONAL_CONTEXT={direction}")
    finding = str(e3.get("finding", e3.get("structure_state", ""))).upper()
    slope = str(e3.get("slope_context", "")).upper()
    external = str(e3.get("external_count_state", "")).upper()
    if "MIXED" in finding or "MIXED" in str(e3.get("internal_count_state", "")).upper():
        counter.append("STRUCTURE_MIXED")
    if direction == "BUY" and external == "DOWN" or direction == "SELL" and external == "UP":
        counter.append("EXTERNAL_STRUCTURE_COUNTERTREND")
    if "FAILED_BOS" in finding:
        counter.append("FAILED_STRUCTURE_BREAK")
    if slope in {"UP", "DOWN"}:
        sd = "BUY" if slope == "UP" else "SELL"
        support.append(f"E3_SLOPE={slope}")
        if direction != "NEUTRAL" and sd != direction:
            counter.append("STRUCTURE_SLOPE_CONFLICT")
    return direction, support, list(dict.fromkeys(counter))


def _closed_candle(bars: list[dict[str, Any]], atr: float, direction: str) -> dict[str, Any]:
    b = bars[-1]
    o, h, l, c = map(float, (b["open"], b["high"], b["low"], b["close"]))
    rng = max(h - l, 1e-9)
    pos = (c - l) / rng
    return {
        "body_atr": round(abs(c - o) / max(atr, 1e-9), 4),
        "range_atr": round(rng / max(atr, 1e-9), 4),
        "directional_close": (pos >= .65 if direction == "BUY" else pos <= .35 if direction == "SELL" else False),
    }


def _formation_scan(bars: list[dict[str, Any]], atr: float, direction: str, e3: dict[str, Any]) -> tuple[list[tuple[str, list[str], list[str]]], list[str]]:
    candidates: list[tuple[str, list[str], list[str]]] = []
    rejected: list[str] = []
    if direction == "NEUTRAL":
        return candidates, [
            "TREND_PULLBACK:direction_missing", "BREAKOUT:direction_missing",
            "BREAKOUT_RETEST:direction_missing", "IMPULSE_CONTINUATION:direction_missing"
        ]
    closes = [float(b["close"]) for b in bars]
    e20, e50, price = _ema(closes, EMA_FAST), _ema(closes, EMA_SLOW), closes[-1]
    recent = bars[-PULLBACK_LOOKBACK:]
    touched = (min(float(b["low"]) for b in recent) <= e20 + .25 * atr if direction == "BUY"
               else max(float(b["high"]) for b in recent) >= e20 - .25 * atr)
    aligned = price > e20 > e50 if direction == "BUY" else price < e20 < e50
    held = price >= e20 if direction == "BUY" else price <= e20
    mixed = "MIXED" in str(e3.get("finding", "")).upper()
    pb_ev = (["EMA20_EMA50_ALIGNMENT"] if aligned else []) + (["RETRACEMENT_TO_EMA20"] if touched else []) + (["RECLAIM_OR_HOLD_EMA20"] if held else [])
    pb_missing = ([] if aligned else ["trend_alignment"]) + ([] if touched else ["retracement_behavior"]) + ([] if held else ["reclaim_or_hold"])
    if aligned and touched and held and not mixed and abs(price - e20) <= 1.5 * atr:
        candidates.append(("TREND_PULLBACK", pb_ev, pb_missing))
    else:
        rejected.append("TREND_PULLBACK:" + ("structure_mixed" if mixed else "formation_incomplete"))

    prior = bars[-(BREAKOUT_LOOKBACK + 1):-1]
    rh, rl = max(float(b["high"]) for b in prior), min(float(b["low"]) for b in prior)
    last = bars[-1]
    c, o, h, l = map(float, (last["close"], last["open"], last["high"], last["low"]))
    broke = c > rh if direction == "BUY" else c < rl
    expansion = h - l >= .8 * atr or abs(c - o) >= .6 * atr
    pos = (c - l) / max(h - l, 1e-9)
    strong = pos >= .65 if direction == "BUY" else pos <= .35
    bx_ev = (["CLOSED_RANGE_BREAK"] if broke else []) + (["VOLATILITY_EXPANSION"] if expansion else []) + (["DIRECTIONAL_CLOSE"] if strong else [])
    bx_missing = ([] if broke else ["closed_break_of_range"]) + ([] if expansion else ["expansion"]) + ([] if strong else ["directional_close"])
    if broke and expansion and strong:
        candidates.append(("BREAKOUT", bx_ev, bx_missing))
    else:
        rejected.append("BREAKOUT:formation_incomplete")

    before = bars[-(BREAKOUT_LOOKBACK + 3):-3]
    level = max(float(b["high"]) for b in before) if direction == "BUY" else min(float(b["low"]) for b in before)
    br = bars[-3]
    rb = bars[-2:]
    prior_break = float(br["close"]) > level if direction == "BUY" else float(br["close"]) < level
    touched_level = any(float(b["low"]) <= level + .25 * atr if direction == "BUY" else float(b["high"]) >= level - .25 * atr for b in rb)
    held_level = c >= level if direction == "BUY" else c <= level
    rt_ev = (["PRIOR_CLOSED_BREAKOUT"] if prior_break else []) + (["LEVEL_RETEST"] if touched_level else []) + (["RETEST_HOLD"] if held_level else [])
    rt_missing = ([] if prior_break else ["prior_breakout"]) + ([] if touched_level else ["retest"]) + ([] if held_level else ["retest_hold"])
    if prior_break and touched_level and held_level:
        candidates.append(("BREAKOUT_RETEST", rt_ev, rt_missing))
    else:
        rejected.append("BREAKOUT_RETEST:sequence_incomplete")

    recent4 = bars[-4:]
    bodies = [abs(float(x["close"]) - float(x["open"])) for x in recent4[:3]]
    i = max(range(len(bodies)), key=bodies.__getitem__)
    imp_dir = _norm("BUY" if float(recent4[i]["close"]) > float(recent4[i]["open"]) else "SELL")
    follow = _norm("BUY" if c > o else "SELL") == direction
    imp = bodies[i] >= .8 * atr and imp_dir == direction
    if imp and follow:
        candidates.append(("IMPULSE_CONTINUATION", ["DIRECTIONAL_PRIOR_IMPULSE", "DIRECTIONAL_FOLLOW_THROUGH"], []))
    else:
        rejected.append("IMPULSE_CONTINUATION:sequence_incomplete")
    return candidates, rejected


def _result(state: str, setup: str, direction: str, stage: str, maturity: str, thesis: str, quality: float,
            supporting: list[str], counter: list[str], missing: list[str], next_required: list[str],
            invalidation: list[str], candidates: list[str], rejected: list[str]) -> EngineResult:
    reasons = list(dict.fromkeys(counter + ([] if state == "MATURE" else ["SETUP_NOT_MATURE"])))
    out = {
        "architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION,
        "role": "SETUP_ANALYST", "reasoning_role": "SETUP_FORMATION_REASONER",
        "decision_authority": "E9", "trade_decision_authority": False,
        "state": state, "setup": setup, "setup_family": setup, "direction": direction,
        "stage": stage, "lifecycle": stage, "maturity": maturity, "thesis": thesis,
        "setup_quality": round(max(0.0, min(1.0, quality)), 4),
        "candidate_setups": candidates, "rejected_setups": rejected,
        "supporting_evidence": list(dict.fromkeys(supporting)),
        "counter_evidence": list(dict.fromkeys(counter)),
        "missing_evidence": list(dict.fromkeys(missing)),
        "next_required_evidence": list(dict.fromkeys(next_required)),
        "invalidation": list(dict.fromkeys(invalidation)),
        "observations": [
            f"candidate_setups={','.join(candidates) if candidates else 'NONE'}",
            f"rejected_setups={len(rejected)}", f"supporting_evidence={','.join(supporting) if supporting else 'NONE'}",
            f"counter_evidence={','.join(counter) if counter else 'NONE'}",
            f"missing_evidence={','.join(missing) if missing else 'NONE'}",
            f"next_required_evidence={','.join(next_required) if next_required else 'NONE'}",
            f"lifecycle={stage}", f"maturity={maturity}", f"setup_quality={quality:.2f}",
        ],
    }
    return EngineResult("E6", NAME, state == "MATURE", round(max(0.0, min(1.0, quality)) * 100.0, 2), out, tuple(reasons))


def analyze_e6(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """E6 reasons about setup formation only; E7 owns entry confirmation and E9 owns decisions."""
    bars = list(snapshot.get("bars") or [])
    if len(bars) < MIN_BARS:
        return _result("WAIT", "NONE", "NEUTRAL", "UNRESOLVED", "UNRESOLVED", "NO_SETUP: insufficient closed-candle history", 0.0, [], [f"CLOSED_CANDLES_BELOW_MINIMUM={MIN_BARS}"], ["sufficient_closed_candle_data"], ["more closed candles"], ["new closed candle may change evidence"], [], [])
    try:
        atr = _atr(bars)
        if atr <= 0: raise ValueError
    except (KeyError, TypeError, ValueError):
        return _result("WAIT", "NONE", "NEUTRAL", "UNRESOLVED", "UNRESOLVED", "NO_SETUP: invalid market data", 0.0, [], ["INVALID_MARKET_DATA"], ["valid_ohlc_data"], ["valid closed candle"], ["new valid closed candle"], [], [])

    e1, e2, e3, e4, e5 = (_payload(upstream, x) for x in ("E1", "E2", "E3", "E4", "E5"))
    direction, supporting, counter = _direction_context(e1, e2, e3)
    candle = _closed_candle(bars, atr, direction)
    supporting += [f"CURRENT_CANDLE_BODY_ATR={candle['body_atr']}", f"CURRENT_CANDLE_RANGE_ATR={candle['range_atr']}", f"CURRENT_CANDLE_DIRECTIONAL_CLOSE={candle['directional_close']}"]
    e4s, e5s, e2s = str(e4).upper(), str(e5).upper(), str(e2).upper()
    if "PENDING" in e4s and ("SWEEP" in e4s or "REJECTION" in e4s): counter.append("LIQUIDITY_EVENT_NOT_TERMINALLY_CONFIRMED")
    if "CONSTRAINED" in e5s or "EXTENSION_RISK" in e5s: counter.append("LOCATION_CONSTRAINT")
    if "UNRESOLVED" in e2s or "UNPROVEN" in e2s: counter.append("OPPORTUNITY_MATURITY_UNPROVEN")
    if "SWEEP" in e4s or "REJECTION" in e4s: supporting.append("E4_LIQUIDITY_EVENT_PRESENT")
    if "ACCEPTED" in e5s: supporting.append("E5_LOCATION_ACCEPTANCE_CONTEXT")
    counter = list(dict.fromkeys(counter))

    formations, rejected = _formation_scan(bars, atr, direction, e3)
    candidate_names = [x[0] for x in formations]
    if not formations:
        missing = ["setup_specific_price_formation"]
        if "NO_DIRECTIONAL_CONTEXT" in counter: missing.append("directional_context_convergence")
        next_required = ["setup-specific closed-candle price sequence", "evidence that survives E3-E5 counter-evidence", "setup maturation before E7 confirmation"]
        thesis = f"{direction}: context exists, but no setup-specific formation is complete" if direction != "NEUTRAL" else "NO_VALID_SETUP_FORMED"
        return _result("WAIT", "NONE", direction, "SEARCHING", "UNRESOLVED", thesis, .20 if direction != "NEUTRAL" else 0.0, supporting, counter, missing, next_required, ["formation fails to develop", "direction or structure changes"], candidate_names, rejected)

    setup, formation_evidence, formation_missing = formations[0]
    supporting += [f"FORMATION={x}" for x in formation_evidence]
    hard = any(x in counter for x in ("STRUCTURE_SLOPE_CONFLICT", "EXTERNAL_STRUCTURE_COUNTERTREND", "FAILED_STRUCTURE_BREAK", "LOCATION_CONSTRAINT"))
    pending = any(x in counter for x in ("LIQUIDITY_EVENT_NOT_TERMINALLY_CONFIRMED", "OPPORTUNITY_MATURITY_UNPROVEN"))
    if hard:
        return _result("WAIT", setup, direction, "CONFLICTED", "UNRESOLVED", f"{direction}_{setup}: formation exists but counter-evidence prevents maturation", .25, supporting, counter, formation_missing + ["environmental_resolution"], ["resolve structural/location conflict", "closed-candle persistence", "E7 confirmation after maturity"], ["formation failure", "competing structure confirmed"], candidate_names, rejected)
    if pending:
        missing = formation_missing + [x.lower() for x in counter if x in {"LIQUIDITY_EVENT_NOT_TERMINALLY_CONFIRMED", "OPPORTUNITY_MATURITY_UNPROVEN"}]
        return _result("DEVELOPING", setup, direction, "TESTING", "DEVELOPING", f"{direction}_{setup}: formation exists but auction/opportunity context is not fully proven", .55, supporting, counter, missing, ["closed-candle persistence", "resolve auction/opportunity uncertainty", "E7 confirmation after maturity"], ["setup sequence fails", "direction reverses"], candidate_names, rejected)

    return _result("MATURE", setup, direction, "TRIGGER_PENDING", "MATURE", f"{direction}_{setup}: setup formation is mature; entry confirmation remains downstream", .90, supporting, counter, ["entry_confirmation"], ["E7 closed-candle confirmation"], ["setup sequence fails", "direction reverses", "structure confirms competing direction"], candidate_names, rejected)
