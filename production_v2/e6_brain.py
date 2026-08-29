from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Setup Brain"
QUESTION = "What setup is forming, in what direction, and at what stage?"
ARCHITECTURE = "E6_PROFESSIONAL_SETUP_FORMATION_BRAIN_V12"
VERSION = "12.0"
MIN_BARS = 60
ATR_PERIOD = 14
EMA_FAST = 20
EMA_SLOW = 50
BREAKOUT_LOOKBACK = 12
PULLBACK_LOOKBACK = 6
MIN_SPACE_ATR = 0.75

SETUP_FAMILIES = (
    "LIQUIDITY_REVERSAL",
    "BREAKOUT_RETEST",
    "TREND_PULLBACK",
    "BREAKOUT",
    "IMPULSE_CONTINUATION",
)

HARD_BLOCKERS = {
    "OPPORTUNITY_MATURITY_UNPROVEN",
    "DIRECTIONAL_EVIDENCE_CONFLICT",
    "EXTERNAL_STRUCTURE_COUNTERTREND",
    "FAILED_STRUCTURE_BREAK",
    "STRUCTURE_MIXED",
    "LIQUIDITY_EVENT_PENDING",
    "LOCATION_CONSTRAINT",
}


def _payload(upstream: dict[str, EngineResult], name: str) -> dict[str, Any]:
    result = upstream.get(name)
    return result.output if result else {}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _norm(value: Any) -> str:
    text = _text(value)
    if text in {"UP", "BULLISH", "BUY", "BUYERS", "LONG", "TREND_UP"}:
        return "BUY"
    if text in {"DOWN", "BEARISH", "SELL", "SELLERS", "SHORT", "TREND_DOWN"}:
        return "SELL"
    return "NEUTRAL"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _atr(bars: list[dict[str, Any]], period: int = ATR_PERIOD) -> float:
    if len(bars) < 2:
        return 0.0
    sample = bars[-(period + 1):]
    trs: list[float] = []
    for i, bar in enumerate(sample):
        h, l = _num(bar.get("high")), _num(bar.get("low"))
        if i == 0:
            trs.append(max(0.0, h - l))
        else:
            p = _num(sample[i - 1].get("close"))
            trs.append(max(h - l, abs(h - p), abs(l - p)))
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
    if "HIGH_SWEEP_REJECTION" in event or "HIGH_FAILED_BREAK_RECLAIM" in event:
        return "SELL"
    if "LOW_SWEEP_REJECTION" in event or "LOW_FAILED_BREAK_RECLAIM" in event:
        return "BUY"
    if "HIGH_ACCEPTANCE" in event or "HIGH_BREAK" in event:
        return "BUY"
    if "LOW_ACCEPTANCE" in event or "LOW_BREAK" in event:
        return "SELL"
    return "NEUTRAL"


def _evidence_direction(e1: dict[str, Any], e2: dict[str, Any], e3: dict[str, Any], e4: dict[str, Any]) -> tuple[str, list[str], list[str], str]:
    supporting: list[str] = []
    counter: list[str] = []
    e2_finding = _text(e2.get("finding", e2.get("state", "")))
    e2_dirs = [_norm(e2.get("direction")), _norm(e2.get("opportunity_direction"))]
    e2_dirs = [x for x in e2_dirs if x != "NEUTRAL"]
    e2_resolved = bool(e2_dirs) and "UNRESOLVED" not in e2_finding and "UNPROVEN" not in e2_finding
    pressure = _norm(e1.get("directional_pressure", e1.get("pressure")))
    external = _norm(e3.get("external_state", e3.get("external_count_state")))
    event = _text(e4.get("event", e4.get("finding")))
    auction = _auction_direction(event)

    if e2_resolved and len(set(e2_dirs)) == 1:
        direction, source = e2_dirs[0], "E2_RESOLVED"
    elif pressure != "NEUTRAL" and external != "NEUTRAL" and pressure == external:
        direction, source = pressure, "E1_E3_ALIGNMENT"
    elif external != "NEUTRAL" and auction == external:
        direction, source = external, "E3_E4_ALIGNMENT"
    elif external != "NEUTRAL":
        direction, source = external, "E3_STRUCTURE"
    elif pressure != "NEUTRAL":
        direction, source = pressure, "E1_PRESSURE"
    else:
        direction, source = "NEUTRAL", "NONE"

    for label, value in (("E2", e2_dirs[0] if e2_dirs else "NEUTRAL"), ("E1_PRESSURE", pressure), ("E3_EXTERNAL", external), ("E4_AUCTION", auction)):
        if value != "NEUTRAL":
            supporting.append(f"{label}={value}")
    if direction != "NEUTRAL":
        supporting.append(f"DIRECTION_SOURCE={source}")

    independent = [x for x in (pressure, external, auction) if x != "NEUTRAL"]
    if len(set(independent)) > 1:
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
    pending = state == "PENDING" or "PENDING" in event
    age = max(0, int(_num(e4.get("event_age_bars"), 0)))
    return event, terminal, pending, age


def _location(e5: dict[str, Any]) -> tuple[float, float, bool]:
    long_space = _num(e5.get("available_space_atr_long"))
    short_space = _num(e5.get("available_space_atr_short"))
    text = _text(e5)
    explicit = any(x in text for x in ("LOCATION_CONSTRAINT", "SPACE_CONSTRAINED", "EXTENSION_RISK"))
    return long_space, short_space, explicit


def _candle(bars: list[dict[str, Any]], atr: float, direction: str) -> tuple[float, float, bool, float]:
    b = bars[-1]
    o, h, l, c = (_num(b.get(k)) for k in ("open", "high", "low", "close"))
    rng = max(h - l, 1e-9)
    pos = (c - l) / rng
    directional = pos >= 0.65 if direction == "BUY" else pos <= 0.35 if direction == "SELL" else False
    return abs(c - o) / max(atr, 1e-9), rng / max(atr, 1e-9), directional, pos


def _candidate(name: str, strength: float, stage: str, evidence: list[str], missing: list[str], invalidation: list[str]) -> dict[str, Any]:
    return {"name": name, "strength": strength, "formation_stage": stage, "evidence": evidence, "missing": missing, "invalidation": invalidation}


def _candidate_scan(bars: list[dict[str, Any]], atr: float, direction: str, e1: dict[str, Any], e3: dict[str, Any], e4: dict[str, Any], e5: dict[str, Any], terminal: bool) -> tuple[list[dict[str, Any]], list[str]]:
    """Build hypotheses from causal sequences. E6 may recognize formation, never authorize entry."""
    if direction == "NEUTRAL":
        return [], [f"{x}:direction_missing" for x in SETUP_FAMILIES]

    found: list[dict[str, Any]] = []
    rejected: list[str] = []
    event = _text(e4.get("event", e4.get("finding")))
    response = _norm(e4.get("response_actor"))
    e1_state = _text(e1.get("trend_state", e1.get("finding", "")))
    e3_finding = _text(e3.get("finding", e3.get("structure_state")))
    external = _norm(e3.get("external_state", e3.get("external_count_state")))
    bos = _text(e3.get("bos", e3.get("break_of_structure", "")))
    long_space, short_space, location_constraint = _location(e5)
    usable = long_space if direction == "BUY" else short_space
    o, h, l, c = (_num(bars[-1].get(k)) for k in ("open", "high", "low", "close"))
    rng = max(h - l, 1e-9)
    pos = (c - l) / rng
    dclose = pos >= 0.65 if direction == "BUY" else pos <= 0.35

    # Liquidity reversal: recognize the setup as forming as soon as the causal event exists.
    # Confirmation is a separate stage; do not require the current candle to prove everything.
    liquidity_event = any(x in event for x in ("SWEEP_REJECTION", "FAILED_BREAK_RECLAIM"))
    reversal_dir = "SELL" if "HIGH_" in event else "BUY" if "LOW_" in event else "NEUTRAL"
    if liquidity_event and reversal_dir == direction:
        rejection_close = pos <= 0.40 if direction == "SELL" else pos >= 0.60
        evidence = ["E4_LIQUIDITY_EVENT", f"EVENT={event}"]
        missing: list[str] = []
        if response == direction:
            evidence.append("RESPONSE_ACTOR_ALIGNED")
        else:
            missing.append("aligned_auction_response")
        if rejection_close:
            evidence.append("CURRENT_CLOSED_CANDLE_REJECTION")
        else:
            missing.append("directional_closed_candle_rejection")
        if terminal:
            evidence.append("TERMINAL_AUCTION_STATE")
        else:
            missing.append("terminal_liquidity_auction_confirmation")
        if usable < MIN_SPACE_ATR:
            missing.append("usable_structural_space")
        if location_constraint:
            missing.append("location_quality")
        if not missing and terminal:
            stage, strength = "MATURE", 92.0
        elif rejection_close and response == direction:
            stage, strength = "VALIDATING", 80.0
        else:
            stage, strength = "FORMING", 65.0
        found.append(_candidate("LIQUIDITY_REVERSAL", strength, stage, evidence, missing, ["loss_of_reclaim", "contrary_closed_candle_acceptance", "protected_level_break_against_setup"]))
    elif liquidity_event:
        rejected.append("LIQUIDITY_REVERSAL:event_direction_conflict")

    # Breakout-retest: explicit sequence, with E3 failure as a veto.
    if len(bars) >= BREAKOUT_LOOKBACK + 4:
        before = bars[-(BREAKOUT_LOOKBACK + 3):-3]
        level = max(_num(x.get("high")) for x in before) if direction == "BUY" else min(_num(x.get("low")) for x in before)
        prior_break = _num(bars[-3].get("close")) > level if direction == "BUY" else _num(bars[-3].get("close")) < level
        retest = any(_num(x.get("low")) <= level + 0.25 * atr for x in bars[-2:]) if direction == "BUY" else any(_num(x.get("high")) >= level - 0.25 * atr for x in bars[-2:])
        hold = c >= level if direction == "BUY" else c <= level
        if prior_break and retest and "FAILED_BOS" not in e3_finding:
            missing = [] if hold else ["retest_hold_close"]
            if external != direction: missing.append("structural_direction_alignment")
            if usable < MIN_SPACE_ATR: missing.append("usable_structural_space")
            stage = "MATURE" if not missing else "VALIDATING"
            found.append(_candidate("BREAKOUT_RETEST", 88.0 if stage == "MATURE" else 72.0, stage, ["PRIOR_CLOSED_BREAKOUT", "LEVEL_RETEST"] + (["RETEST_HOLD"] if hold else []), missing, ["failed_retest", "close_back_inside_prior_range"]))
        else:
            rejected.append("BREAKOUT_RETEST:sequence_incomplete")

    # Trend pullback requires actual trend state + structural alignment; EMA geometry alone is insufficient.
    closes = [_num(x.get("close")) for x in bars]
    ema20, ema50, price = _ema(closes, EMA_FAST), _ema(closes, EMA_SLOW), closes[-1]
    recent = bars[-PULLBACK_LOOKBACK:]
    touched = min(_num(x.get("low")) for x in recent) <= ema20 + 0.25 * atr if direction == "BUY" else max(_num(x.get("high")) for x in recent) >= ema20 - 0.25 * atr
    aligned = price > ema20 > ema50 if direction == "BUY" else price < ema20 < ema50
    held = price >= ema20 if direction == "BUY" else price <= ema20
    trend_context = ("UP" in e1_state or "DOWN" in e1_state or "TREND" in e1_state) and "NONE" not in e1_state
    if aligned and touched and trend_context and external == direction and "MIXED" not in e3_finding and "FAILED_BOS" not in e3_finding:
        missing = [] if held else ["closed_candle_hold_at_ema20"]
        if usable < MIN_SPACE_ATR: missing.append("usable_structural_space")
        stage = "MATURE" if not missing else "VALIDATING"
        found.append(_candidate("TREND_PULLBACK", 84.0 if stage == "MATURE" else 70.0, stage, ["TREND_CONTEXT", "EMA20_EMA50_ALIGNMENT", "RETRACEMENT_TO_EMA20"] + (["RECLAIM_OR_HOLD_EMA20"] if held else []), missing, ["protected_structure_failure", "trend_alignment_lost"]))
    else:
        rejected.append("TREND_PULLBACK:formation_incomplete")

    # Breakout requires E3's independent BOS. E6 never creates BOS from raw OHLC.
    prior = bars[-(BREAKOUT_LOOKBACK + 1):-1]
    rh, rl = max(_num(x.get("high")) for x in prior), min(_num(x.get("low")) for x in prior)
    broke = c > rh if direction == "BUY" else c < rl
    expansion = h - l >= 0.8 * atr or abs(c - o) >= 0.6 * atr
    e3_bos = any(x in bos for x in ("BREAK", "BOS")) and "NO_BREAK" not in bos and "FAILED_BOS" not in e3_finding
    if broke and expansion and dclose and external == direction and e3_bos:
        missing = [] if usable >= MIN_SPACE_ATR else ["usable_structural_space"]
        stage = "MATURE" if not missing else "VALIDATING"
        found.append(_candidate("BREAKOUT", 86.0 if stage == "MATURE" else 68.0, stage, ["E3_CONFIRMED_BOS", "CLOSED_RANGE_BREAK", "VOLATILITY_EXPANSION", "DIRECTIONAL_CLOSE"], missing, ["breakout_rejection", "close_back_inside_range"]))
    else:
        rejected.append("BREAKOUT:formation_incomplete_or_E3_BOS_missing")

    # Impulse continuation requires an impulse AND follow-through; one large candle is not enough.
    recent4 = bars[-4:]
    bodies = [abs(_num(x.get("close")) - _num(x.get("open"))) for x in recent4[:3]]
    idx = max(range(len(bodies)), key=bodies.__getitem__)
    impulse = recent4[idx]
    impulse_dir = "BUY" if _num(impulse.get("close")) > _num(impulse.get("open")) else "SELL"
    follow_dir = "BUY" if c > o else "SELL"
    if bodies[idx] >= 0.8 * atr and impulse_dir == direction and external == direction and trend_context:
        missing = [] if follow_dir == direction and dclose else ["directional_closed_candle_follow_through"]
        if usable < MIN_SPACE_ATR: missing.append("usable_structural_space")
        stage = "MATURE" if not missing else "FORMING"
        found.append(_candidate("IMPULSE_CONTINUATION", 80.0 if stage == "MATURE" else 65.0, stage, ["TREND_CONTEXT", "DIRECTIONAL_PRIOR_IMPULSE"] + (["DIRECTIONAL_FOLLOW_THROUGH"] if follow_dir == direction else []), missing, ["impulse_failure", "countertrend_close"]))
    else:
        rejected.append("IMPULSE_CONTINUATION:sequence_incomplete")
    return found, rejected


def _result(state: str, setup: str, direction: str, stage: str, maturity: str, thesis: str, quality: float, supporting: list[str], counter: list[str], missing: list[str], next_required: list[str], invalidation: list[str], candidates: list[str], rejected: list[str], selected_strength: float = 0.0, confidence: float = 0.0, trace: dict[str, Any] | None = None, candidate_states: list[dict[str, Any]] | None = None) -> EngineResult:
    quality = max(0.0, min(100.0, quality))
    confidence = max(0.0, min(100.0, confidence))
    reasons = list(dict.fromkeys(counter + ([] if maturity == "MATURE" else ["SETUP_NOT_MATURE"])))
    output = {
        "architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION,
        "role": "SETUP_ANALYST", "reasoning_role": "SETUP_FORMATION_REASONER",
        "decision_authority": "E9", "trade_decision_authority": False,
        "state": state, "setup_state": state, "setup": setup, "setup_family": setup,
        "direction": direction, "stage": stage, "formation_stage": stage, "lifecycle": stage,
        "maturity": maturity, "thesis": thesis, "setup_quality": round(quality, 2),
        "confidence": round(confidence, 2), "candidate_strength": round(selected_strength, 2),
        "candidate_setups": candidates, "rejected_setups": rejected,
        "candidate_states": candidate_states or [],
        "supporting_evidence": list(dict.fromkeys(supporting)),
        "counter_evidence": list(dict.fromkeys(counter)),
        "missing_evidence": list(dict.fromkeys(missing)),
        "next_required_evidence": list(dict.fromkeys(next_required)),
        "invalidation": list(dict.fromkeys(invalidation)),
        "observations": [
            f"candidate_setups={','.join(candidates) if candidates else 'NONE'}",
            f"selected_setup={setup}", f"selected_direction={direction}",
            f"selected_stage={stage}", f"rejected_setups={len(rejected)}",
            f"supporting_evidence={','.join(supporting) if supporting else 'NONE'}",
            f"counter_evidence={','.join(counter) if counter else 'NONE'}",
            f"missing_evidence={','.join(missing) if missing else 'NONE'}",
            f"next_required_evidence={','.join(next_required) if next_required else 'NONE'}",
            f"lifecycle={stage}", f"maturity={maturity}", f"setup_quality={quality:.2f}",
            f"confidence={confidence:.2f}",
        ],
    }
    if trace:
        output["reasoning_trace"] = trace
    return EngineResult("E6", NAME, maturity == "MATURE", quality, output, tuple(reasons))


def analyze_e6(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """Professional setup-formation reasoning. E6 identifies lifecycle; E7/E8/E9 retain execution authority."""
    bars = list(snapshot.get("bars") or [])
    if len(bars) < MIN_BARS:
        return _result("NO_SETUP", "NONE", "NEUTRAL", "SEARCHING", "UNRESOLVED", "NO_SETUP: insufficient closed-candle history", 0.0, [], [f"CLOSED_CANDLES_BELOW_MINIMUM={MIN_BARS}"], ["sufficient_closed_candle_data"], ["more closed candles"], ["history remains insufficient"], [], [], confidence=100.0)
    try:
        atr = _atr(bars)
        if atr <= 0: raise ValueError("invalid atr")
        for bar in bars[-MIN_BARS:]:
            for key in ("open", "high", "low", "close"):
                float(bar[key])
    except (KeyError, TypeError, ValueError):
        return _result("NO_SETUP", "NONE", "NEUTRAL", "SEARCHING", "UNRESOLVED", "NO_SETUP: invalid market data", 0.0, [], ["INVALID_MARKET_DATA"], ["valid_ohlc_data"], ["valid closed candle"], ["valid market data"], [], [], confidence=100.0)

    e1, e2, e3, e4, e5 = (_payload(upstream, n) for n in ("E1", "E2", "E3", "E4", "E5"))
    direction, supporting, counter, direction_source = _evidence_direction(e1, e2, e3, e4)
    event, terminal, pending, event_age = _auction(e4)
    long_space, short_space, location_constraint = _location(e5)
    opportunity = _text(e2.get("finding", e2.get("state", "")))
    e3_finding = _text(e3.get("finding", e3.get("structure_state")))
    e3_internal = _text(e3.get("internal_state", e3.get("internal_count_state")))
    e3_external = _norm(e3.get("external_state", e3.get("external_count_state")))

    if event: supporting += [f"E4_EVENT={event}", f"E4_EVENT_AGE_BARS={event_age}"]
    if pending and not terminal: counter.append("LIQUIDITY_EVENT_PENDING")
    if "MIXED" in e3_finding or "MIXED" in e3_internal: counter.append("STRUCTURE_MIXED")
    if "UNRESOLVED" in opportunity or "UNPROVEN" in opportunity: counter.append("OPPORTUNITY_MATURITY_UNPROVEN")
    if long_space or short_space: supporting += [f"STRUCTURAL_SPACE_LONG_ATR={long_space:.3f}", f"STRUCTURAL_SPACE_SHORT_ATR={short_space:.3f}"]
    if location_constraint: counter.append("LOCATION_CONSTRAINT")

    body, rng, dclose, candle_pos = _candle(bars, atr, direction)
    supporting += [f"CURRENT_CANDLE_BODY_ATR={body:.3f}", f"CURRENT_CANDLE_RANGE_ATR={rng:.3f}", f"CURRENT_CANDLE_DIRECTIONAL_CLOSE={dclose}", f"CURRENT_CANDLE_CLOSE_POSITION={candle_pos:.3f}"]

    formations, rejected = _candidate_scan(bars, atr, direction, e1, e3, e4, e5, terminal)
    counter = list(dict.fromkeys(counter))
    formations.sort(key=lambda x: (x.get("strength", 0), x.get("formation_stage") == "MATURE"), reverse=True)
    candidates = [x["name"] for x in formations]
    candidate_states = [{"setup": x["name"], "stage": x["formation_stage"], "strength": x["strength"], "missing": x["missing"]} for x in formations]

    trace = {
        "direction_source": direction_source, "e1_state": _text(e1.get("finding", e1.get("state", ""))),
        "e1_trend_state": _text(e1.get("trend_state", "")), "e2_state": opportunity,
        "e3_state": e3_finding, "e3_external": e3_external, "e3_bos": _text(e3.get("bos", e3.get("break_of_structure", ""))),
        "e4_event": event, "e4_auction_state": _text(e4.get("auction_state", e4.get("state", ""))),
        "e4_event_age_bars": event_age, "e4_event_id": e4.get("event_id") or e4.get("event_candle_id"),
        "e5_state": _text(e5.get("finding", e5.get("state", ""))), "closed_candle_only": True,
        "lookahead": False, "hard_blockers": sorted(x for x in counter if x in HARD_BLOCKERS),
    }

    if not formations:
        missing = ["setup_specific_causal_sequence"]
        next_required = ["a valid setup-specific closed-candle sequence"]
        if direction == "NEUTRAL": next_required.insert(0, "directional context convergence")
        if event and not terminal: missing.append("terminal_liquidity_auction_confirmation"); next_required.append("terminal liquidity acceptance/rejection")
        if direction == "BUY" and long_space < MIN_SPACE_ATR: missing.append("usable_long_structural_space"); next_required.append("usable long structural space")
        if direction == "SELL" and short_space < MIN_SPACE_ATR: missing.append("usable_short_structural_space"); next_required.append("usable short structural space")
        if "OPPORTUNITY_MATURITY_UNPROVEN" in counter: missing.append("opportunity_maturity"); next_required.append("closed-candle opportunity acceptance/follow-through")
        if "DIRECTIONAL_EVIDENCE_CONFLICT" in counter: missing.append("directional_evidence_convergence"); next_required.append("closed-candle directional convergence")
        if "STRUCTURE_MIXED" in counter: missing.append("structural_alignment"); next_required.append("clear protected-level structural confirmation")
        state = "FORMING" if direction != "NEUTRAL" else "NO_SETUP"
        stage = "FORMING" if state == "FORMING" else "SEARCHING"
        thesis = "NO_SETUP: no causal setup sequence is identified" if state == "NO_SETUP" else f"{direction}: no setup family has completed its causal sequence; monitor the missing evidence"
        return _result(state, "NONE", direction, stage, "UNRESOLVED", thesis, 8.0 if state == "FORMING" else 0.0, supporting, counter, missing, list(dict.fromkeys(next_required)), ["directional thesis invalidation", "setup-specific formation failure"], candidates, rejected, confidence=82.0 if state == "FORMING" else 90.0, trace=trace)

    selected = formations[0]
    setup = selected["name"]
    strength = float(selected["strength"])
    supporting += [f"FORMATION={x}" for x in selected["evidence"]]
    missing = list(selected["missing"])
    next_required = list(selected["missing"])
    direction_space = short_space if direction == "SELL" else long_space
    if "LIQUIDITY_EVENT_PENDING" in counter and "terminal_liquidity_auction_confirmation" not in missing:
        missing.append("terminal_liquidity_auction_confirmation"); next_required.append("terminal liquidity acceptance/rejection")
    if "OPPORTUNITY_MATURITY_UNPROVEN" in counter:
        missing.append("opportunity_maturity"); next_required.append("closed-candle opportunity acceptance/follow-through")
    if "DIRECTIONAL_EVIDENCE_CONFLICT" in counter:
        missing.append("directional_evidence_convergence"); next_required.append("closed-candle directional convergence")
    if "STRUCTURE_MIXED" in counter:
        missing.append("structural_alignment"); next_required.append("clear protected-level structural confirmation")
    if "LOCATION_CONSTRAINT" in counter:
        missing.append("location_quality"); next_required.append("usable structural space")
    if direction_space < MIN_SPACE_ATR and "usable_structural_space" not in missing:
        missing.append("usable_structural_space"); next_required.append("price relocation into usable structural space")

    blockers = [x for x in counter if x in HARD_BLOCKERS]
    formation_stage = _text(selected.get("formation_stage", "FORMING"))
    # Maturity is deliberately impossible while any hard blocker or required evidence remains.
    if formation_stage == "MATURE" and not missing and not blockers:
        state, stage, maturity, quality = "MATURE", "TRIGGER_PENDING", "MATURE", min(92.0, strength)
        thesis = f"{direction}_{setup}: causal formation is mature; E7 must independently prove entry confirmation"
    elif formation_stage in {"VALIDATING", "MATURE"}:
        state, stage, maturity, quality = "FORMING", formation_stage, "DEVELOPING", min(82.0, strength)
        thesis = f"{direction}_{setup}: setup is validating but not trade-ready; required evidence remains explicit"
    else:
        state, stage, maturity, quality = "FORMING", "FORMING", "DEVELOPING", min(75.0, strength)
        thesis = f"{direction}_{setup}: setup is forming; causal sequence has not reached validation"

    next_required.append("E7 closed-candle entry confirmation")
    invalidation = list(selected.get("invalidation", [])) + ["directional evidence becomes structurally contradictory", "location loses sufficient structural space"]
    confidence = min(96.0, max(55.0, strength + 6.0 - 7.0 * len(blockers)))
    return _result(state, setup, direction, stage, maturity, thesis, quality, supporting, counter, list(dict.fromkeys(missing)), list(dict.fromkeys(next_required)), list(dict.fromkeys(invalidation)), candidates, rejected, strength, confidence, trace, candidate_states)
