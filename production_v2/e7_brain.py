from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Confirmation / Trigger Brain"
QUESTION = "Does the setup have a valid closed-candle confirmation, or what is still missing?"
ARCHITECTURE = "E7_PROFESSIONAL_SETUP_AWARE_CONFIRMATION_BRAIN_V5"
VERSION = "5.0"
ATR_PERIOD = 14
MIN_BARS = 5
FOLLOW_THROUGH_MAX_AGE = 3
VALID_STATES = {"PASS", "FAIL", "PENDING", "UNAVAILABLE"}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _direction(value: Any) -> str:
    t = _text(value)
    if t in {"BUY", "BULLISH", "UP", "LONG", "BUYERS"}:
        return "BUY"
    if t in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS"}:
        return "SELL"
    return "NEUTRAL"


def _atr(bars: list[dict[str, Any]], period: int = ATR_PERIOD) -> float:
    if len(bars) < 2:
        return 0.0
    trs = []
    for i in range(max(1, len(bars) - period), len(bars)):
        h = _num(bars[i].get("high"))
        l = _num(bars[i].get("low"))
        pc = _num(bars[i - 1].get("close"))
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return mean(trs) if trs else 0.0


def _candle(bar: dict[str, Any], previous: dict[str, Any], atr: float) -> dict[str, Any]:
    o, h, l, c = (_num(bar.get(k)) for k in ("open", "high", "low", "close"))
    _, _, _, pc = (_num(previous.get(k)) for k in ("open", "high", "low", "close"))
    rng = max(h - l, 1e-9)
    body = abs(c - o)
    a = max(atr, 1e-9)
    pos = max(0.0, min(1.0, (c - l) / rng))
    return {
        "open": o, "high": h, "low": l, "close": c,
        "range": rng, "body": body, "body_atr": body / a,
        "close_position": pos, "bullish": c > o, "bearish": c < o,
        "bullish_engulf": o <= pc and c >= _num(previous.get("open")) and c > o,
        "bearish_engulf": o >= pc and c <= _num(previous.get("open")) and c < o,
        "bullish_displacement": c > o and body / a >= 0.55 and pos >= 0.65,
        "bearish_displacement": c < o and body / a >= 0.55 and pos <= 0.35,
    }


def _e4(e4: dict[str, Any]) -> dict[str, Any]:
    event = _text(e4.get("event", e4.get("finding")))
    state = _text(e4.get("auction_state", e4.get("state")))
    direction = _direction(e4.get("direction"))
    level = _num(e4.get("event_level"))
    age = max(0, int(_num(e4.get("event_age_bars"))))
    if direction == "NEUTRAL":
        if any(x in event for x in ("HIGH_FAILED_BREAK_RECLAIM", "HIGH_SWEEP_REJECTION")):
            direction = "SELL"
        elif any(x in event for x in ("LOW_FAILED_BREAK_RECLAIM", "LOW_SWEEP_REJECTION")):
            direction = "BUY"
        elif any(x in event for x in ("HIGH_ACCEPTANCE", "HIGH_BREAK")):
            direction = "BUY"
        elif any(x in event for x in ("LOW_ACCEPTANCE", "LOW_BREAK")):
            direction = "SELL"
    terminal = state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "REJECTED"} or "TERMINAL" in state
    return {
        "event": event, "state": state, "direction": direction, "level": level,
        "age": age, "terminal": terminal,
        "pending": state == "PENDING" or "PENDING" in event,
        "event_id": str(e4.get("event_id") or e4.get("event_candle_id") or ""),
        "quality": _num(e4.get("auction_quality")),
    }


def _base(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION,
        "role": "CONFIRMATION_ANALYST", "reasoning_role": "CONFIRMATION_ANALYST",
        "decision_authority": "E9", "trade_decision_authority": False,
        "closed_candle_only": True, "lookahead": False,
        "bar_count": len(snapshot.get("bars") or []),
    }


def _empty(snapshot: dict[str, Any], reason: str) -> EngineResult:
    out = {
        **_base(snapshot), "state": "WAIT", "confirmation": "UNRESOLVED",
        "trigger_status": "NOT_EVALUATED", "direction": "NEUTRAL", "setup": "NONE",
        "trigger_observed": False, "confirmation_strength": "NONE", "confirmation_score": 0.0,
        "supporting_evidence": [], "counter_evidence": [reason],
        "observed_evidence": [f"context=INSUFFICIENT reason={reason}"],
        "missing_evidence": ["valid setup thesis", "valid closed-candle confirmation"],
        "next_required_evidence": ["a valid closed candle proving the setup thesis"],
        "next_required_event": "VALID_CLOSED_CANDLE_PROVING_SETUP_THESIS",
        "invalidation": ["new closed candle invalidates or replaces the current thesis"],
        "proof_gates": {}, "evidence_ledger": {},
        "confirmation_lifecycle": "WAIT",
        "reasoning_trace": {"conclusion": "Confirmation cannot be evaluated from current context."},
    }
    return EngineResult("E7", NAME, False, 0.0, out, ("INSUFFICIENT_CONTEXT",))


def analyze_e7(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    bars = list(snapshot.get("bars") or [])
    e6 = upstream.get("E6")
    if len(bars) < MIN_BARS or not e6:
        return _empty(snapshot, "MISSING_SETUP_CONTEXT")

    e6o = dict(e6.output or {})
    e4o = dict((upstream.get("E4").output if upstream.get("E4") else {}) or {})
    e3o = dict((upstream.get("E3").output if upstream.get("E3") else {}) or {})
    e5o = dict((upstream.get("E5").output if upstream.get("E5") else {}) or {})
    direction = _direction(e6o.get("direction", e6o.get("direction_thesis")))
    setup = _text(e6o.get("setup", e6o.get("setup_family"))) or "NONE"
    thesis = str(e6o.get("candidate_setup_thesis") or e6o.get("thesis") or "")
    atr = max(_atr(bars), 1e-9)
    c = _candle(bars[-1], bars[-2], atr)
    p = _candle(bars[-2], bars[-3], atr)
    auction = _e4(e4o)

    if direction not in {"BUY", "SELL"}:
        out = {
            **_base(snapshot), "state": "UNRESOLVED", "confirmation": "UNRESOLVED",
            "trigger_status": "NOT_EVALUATED", "direction": "NEUTRAL", "setup": setup,
            "candidate_setup_thesis": thesis, "trigger_observed": False,
            "confirmation_strength": "NONE", "confirmation_score": 20.0,
            "supporting_evidence": [], "counter_evidence": ["SETUP_DIRECTION_UNRESOLVED"],
            "observed_evidence": ["direction_resolved=FAIL observed=NEUTRAL required=BUY_or_SELL"],
            "missing_evidence": ["directional setup thesis"],
            "next_required_evidence": ["E6 must expose a resolved BUY/SELL thesis"],
            "next_required_event": "E6_RESOLVED_DIRECTIONAL_THESIS",
            "invalidation": ["new closed candle changes the setup thesis"],
            "proof_gates": {"direction_resolved": "FAIL"},
            "evidence_ledger": {"direction_resolved": {
                "state": "FAIL", "observed": direction, "required": "BUY or SELL",
                "interpretation": "No directional thesis is available."
            }},
            "confirmation_lifecycle": "UNRESOLVED",
            "reasoning_trace": {"conclusion": "No directional thesis can be confirmed."},
        }
        return EngineResult("E7", NAME, False, 20.0, out, ("SETUP_DIRECTION_UNRESOLVED",))

    buy = direction == "BUY"
    support: list[str] = []
    counter: list[str] = []
    missing: list[str] = []
    invalid: list[str] = []
    ledger: dict[str, dict[str, Any]] = {}
    proof: dict[str, str] = {}

    def rec(name: str, state: str, observed: Any = None, required: Any = None, why: str = "") -> None:
        normalized = _text(state) if _text(state) in VALID_STATES else "UNAVAILABLE"
        ledger[name] = {
            "state": normalized,
            "observed": observed,
            "required": required,
            "interpretation": why,
        }
        if normalized == "PASS":
            support.append(name.upper())
        elif normalized == "FAIL":
            counter.append(name.upper())
        else:
            missing.append(name)

    def gate(name: str, state: str, missing_name: str, observed: Any = None,
             required: Any = "PASS", why: str = "") -> None:
        normalized = _text(state) if _text(state) in VALID_STATES else "UNAVAILABLE"
        proof[name] = normalized
        rec("setup." + name, normalized, observed if observed is not None else normalized, required, why)
        if normalized in {"PENDING", "UNAVAILABLE"}:
            missing.append(missing_name)

    directional = bool(c["bullish"] if buy else c["bearish"])
    close_ok = bool(c["close_position"] >= 0.65 if buy else c["close_position"] <= 0.35)
    displacement = bool(c["bullish_displacement"] if buy else c["bearish_displacement"])
    engulf = bool(c["bullish_engulf"] if buy else c["bearish_engulf"])
    trigger = directional and close_ok and (displacement or engulf)

    rec("directional_closed_candle", "PASS" if directional else "FAIL", directional, True,
        "Closed candle agrees with E6 thesis direction.")
    rec("close_location", "PASS" if close_ok else "FAIL", round(float(c["close_position"]), 4),
        ">=0.65 BUY / <=0.35 SELL", "Close must finish on the thesis side of the candle.")
    rec("meaningful_directional_displacement", "PASS" if displacement else "PENDING",
        round(float(c["body_atr"]), 4), ">=0.55 ATR",
        "Displacement is evidence, not permission by itself.")
    rec("engulfing_response", "PASS" if engulf else "UNAVAILABLE", engulf, True,
        "Engulfing is optional corroboration.")

    internal = _direction(e3o.get("internal_state", e3o.get("internal_count_state")))
    external = _direction(e3o.get("external_state", e3o.get("external_count_state")))
    finding = _text(e3o.get("finding", e3o.get("structure_state")))
    rec("internal_structure", "PASS" if internal == direction else "FAIL" if internal != "NEUTRAL" else "UNAVAILABLE",
        internal, direction, "Internal structure corroboration.")
    rec("external_structure", "PASS" if external == direction else "FAIL" if external != "NEUTRAL" else "UNAVAILABLE",
        external, direction, "External structure corroboration.")
    if "MIXED" in finding or "TRANSITION" in finding:
        counter.append("STRUCTURE_NOT_RESOLVED")
    space = _num(e5o.get("available_space_atr_long" if buy else "available_space_atr_short"))
    rec("structural_space", "PASS" if space >= 0.75 else "FAIL" if space > 0 else "UNAVAILABLE",
        round(space, 4), ">=0.75 ATR", "Enough structural room must exist for a survivable confirmation.")

    family = setup.replace(" ", "_")
    if "LIQUIDITY_REVERSAL" in family:
        event_ok = bool(auction["event"] and any(x in auction["event"] for x in ("SWEEP_REJECTION", "FAILED_BREAK_RECLAIM")))
        gate("liquidity_event", "PASS" if event_ok else "FAIL", "liquidity_sweep_or_failed_break_reclaim",
             auction["event"], "SWEEP_REJECTION or FAILED_BREAK_RECLAIM")
        gate("liquidity_response", "PASS" if auction["direction"] == direction else "FAIL" if auction["direction"] in {"BUY", "SELL"} else "PENDING",
             "liquidity_response_aligned_with_thesis", auction["direction"], direction)
        gate("auction_terminality", "PASS" if auction["terminal"] else "PENDING" if auction["pending"] else "FAIL",
             "terminal_auction_confirmation", auction["state"], "TERMINAL")
        if auction["level"]:
            reclaimed = c["close"] > auction["level"] if buy else c["close"] < auction["level"]
            gate("level_reclaim", "PASS" if reclaimed else "FAIL", "closed_candle_reclaim_of_liquidity_level",
                 round(c["close"], 6), auction["level"])
        else:
            gate("level_reclaim", "UNAVAILABLE", "liquidity_level", None, "event level")
    elif "BREAKOUT_RETEST" in family or "BREAKOUT" in family:
        bos = _text(e3o.get("bos", e3o.get("break_of_structure"))) in {"BREAK", "BOS", "YES"}
        gate("structure_break", "PASS" if bos else "FAIL", "confirmed_structure_break", bos, True)
        gate("break_acceptance_close", "PASS" if close_ok else "FAIL", "closed_candle_acceptance_beyond_level",
             c["close_position"], ">=0.65 BUY / <=0.35 SELL")
        gate("breakout_displacement", "PASS" if displacement else "PENDING", "breakout_displacement",
             c["body_atr"], ">=0.55 ATR")
        if "BREAKOUT_RETEST" in family:
            gate("retest_continuation", "PASS" if displacement and directional else "PENDING",
                 "continuation_after_retest", {"directional": directional, "displacement": displacement}, True)
    elif "TREND_PULLBACK" in family:
        trend = _direction(e3o.get("trend_state", e3o.get("direction")))
        gate("trend_alignment", "PASS" if trend == direction else "FAIL" if trend != "NEUTRAL" else "PENDING",
             "trend_direction_alignment", trend, direction)
        gate("pullback_response", "PASS" if directional else "FAIL",
             "pullback_rejection_and_continuation", directional, True)
        gate("continuation_displacement", "PASS" if displacement else "PENDING",
             "continuation_displacement", c["body_atr"], ">=0.55 ATR")
    elif "AUCTION_ACCEPTANCE_CONTINUATION" in family:
        gate("terminal_auction_acceptance", "PASS" if auction["terminal"] else "PENDING" if auction["pending"] else "FAIL",
             "terminal_auction_acceptance", auction["state"], "TERMINAL")
        gate("directional_acceptance_close", "PASS" if close_ok else "FAIL",
             "directional_acceptance_close", c["close_position"], ">=0.65 BUY / <=0.35 SELL")
        gate("continuation_displacement", "PASS" if displacement else "PENDING",
             "continuation_displacement", c["body_atr"], ">=0.55 ATR")
    else:
        gate("setup_definition", "FAIL", "setup_specific_confirmation_definition", setup, "known setup family")
        counter.append("UNKNOWN_SETUP_CONFIRMATION_RULE")

    prev_directional = bool(p["bullish"] if buy else p["bearish"])
    prev_close_ok = bool(p["close_position"] >= 0.65 if buy else p["close_position"] <= 0.35)
    prev_displacement = bool(p["bullish_displacement"] if buy else p["bearish_displacement"])
    prev_engulf = bool(p["bullish_engulf"] if buy else p["bearish_engulf"])
    prev_trigger = prev_directional and prev_close_ok and (prev_displacement or prev_engulf)
    follow = "PASS" if prev_trigger and directional and close_ok else "FAIL" if prev_trigger else "PENDING" if trigger else "UNAVAILABLE"
    rec("follow_through", follow,
        {"previous_trigger": prev_trigger, "current_directional_close": directional, "current_close_ok": close_ok},
        "next closed candle continues thesis", "Follow-through requires sequential closed-candle evidence.")

    if auction["event"]:
        fresh = auction["age"] <= FOLLOW_THROUGH_MAX_AGE
        rec("liquidity_event_freshness", "PASS" if fresh else "FAIL", auction["age"],
            f"<= {FOLLOW_THROUGH_MAX_AGE} bars", "A confirmation event must remain temporally relevant.")
        if not fresh:
            invalid.append("LIQUIDITY_EVENT_STALE")

    if (buy and c["bearish"] and c["close_position"] <= 0.35) or ((not buy) and c["bullish"] and c["close_position"] >= 0.65):
        invalid.append("DIRECT_CLOSED_CANDLE_THESIS_REJECTION")
    if auction["direction"] in {"BUY", "SELL"} and auction["direction"] != direction:
        invalid.append("AUCTION_RESPONSE_REVERSES_SETUP_DIRECTION")

    invalidated = bool(invalid)
    setup_specific = bool(proof) and all(v == "PASS" for v in proof.values())
    confirmed = bool(trigger and setup_specific and follow == "PASS" and not invalidated)

    unique_support = list(dict.fromkeys(support))
    unique_counter = list(dict.fromkeys(counter + [x.upper() for x in invalid]))
    unique_missing = list(dict.fromkeys(missing))

    score = 25.0 + min(35.0, len(unique_support) * 4.0) - min(25.0, len(unique_counter) * 5.0) - min(20.0, len(unique_missing) * 2.0)
    if trigger:
        score += 12
    if setup_specific:
        score += 8
    if follow == "PASS":
        score += 15
    if invalidated:
        score -= 25
    score = max(0.0, min(100.0, score))

    if invalidated:
        state, status, strength = "INVALIDATED", "CONFLICTED", "NONE"
    elif confirmed:
        state, status, strength = "CONFIRMED", "CONFIRMED", "STRONG" if score >= 80 else "MODERATE"
    elif trigger or prev_trigger or any(v == "PENDING" for v in proof.values()):
        state, status, strength = "DEVELOPING", "TRIGGER_OBSERVED_NOT_PROVEN", "MODERATE" if score >= 60 else "WEAK"
    else:
        state, status, strength = "WAITING", "NOT_CONFIRMED", "WEAK"

    if state == "CONFIRMED":
        next_required = ["no additional E7 proof gate; E8/E9 independently validate economics and execution"]
        next_event = "HANDOFF_TO_E8_E9_INDEPENDENT_VALIDATION"
    elif state == "INVALIDATED":
        next_required = ["a fresh E6 thesis and a new closed-candle proof sequence"]
        next_event = "FRESH_E6_THESIS_AND_NEW_CLOSED_CANDLE_SEQUENCE"
    else:
        next_required = unique_missing or ["another closed candle proving continuation of the thesis"]
        next_event = next_required[0]

    observed_evidence = [
        f"closed_candle.direction={direction} observed={'PASS' if directional else 'FAIL'}",
        f"close_position={c['close_position']:.4f} state={'PASS' if close_ok else 'FAIL'}",
        f"body_atr={c['body_atr']:.4f} state={'PASS' if displacement else 'PENDING'}",
        f"candle_direction={'BULLISH' if c['bullish'] else 'BEARISH' if c['bearish'] else 'NEUTRAL'}",
        f"trigger={'OBSERVED' if trigger else 'NOT_OBSERVED'}",
        f"trigger_is_confirmation=False",
        f"setup={setup or 'NONE'}",
        f"auction.event={auction['event'] or 'NONE'}",
        f"auction.state={auction['state'] or 'UNAVAILABLE'}",
        f"auction.direction={auction['direction']}",
        f"auction.age_bars={auction['age']}",
        f"structural_space_atr={space:.4f}",
        f"follow_through={follow}",
    ]

    missing_evidence = unique_missing
    if not confirmed and not invalidated and not missing_evidence:
        missing_evidence = ["confirmation proof remains incomplete"]

    confirmation_lifecycle = state
    reasoning = {
        "conclusion": "Closed-candle evidence confirms the setup thesis." if confirmed else
                      "Closed-candle evidence invalidates the current setup thesis." if invalidated else
                      "The thesis is alive but confirmation proof is incomplete.",
        "decision_path": [
            "E6 thesis is the hypothesis, not confirmation.",
            "Only the latest closed candle is used; no lookahead.",
            "Trigger evidence is explicitly separated from confirmation.",
            "Setup-specific proof gates must pass before confirmation.",
            "Follow-through and counter-evidence can prevent confirmation.",
            "Invalidation overrides a positive trigger.",
            "E7 reports proof; E9 retains trade-decision authority.",
        ],
        "why_not_confirmed": [] if confirmed else (list(dict.fromkeys(invalid)) if invalidated else missing_evidence),
        "next_required_event": next_event,
    }

    out = {
        **_base(snapshot),
        "state": state,
        "confirmation": "CONFIRMED" if confirmed else "INVALIDATED" if invalidated else "DEVELOPING" if state == "DEVELOPING" else "UNRESOLVED",
        "trigger_status": status,
        "direction": direction,
        "setup": setup,
        "candidate_setup_thesis": thesis,
        "trigger_observed": trigger,
        "confirmation_strength": strength,
        "confirmation_score": round(score, 2),
        "supporting_evidence": unique_support,
        "counter_evidence": unique_counter,
        "observed_evidence": observed_evidence,
        "missing_evidence": missing_evidence,
        "next_required_evidence": next_required,
        "next_required_event": next_event,
        "invalidation": list(dict.fromkeys(invalid or ["new closed candle invalidates or replaces the current thesis"])),
        "confirmation_lifecycle": confirmation_lifecycle,
        "proof_gates": proof,
        "evidence_ledger": ledger,
        "observations": observed_evidence,
        "reasoning_trace": reasoning,
        "event_context": {
            "event": auction["event"], "event_id": auction["event_id"],
            "event_level": auction["level"], "event_age_bars": auction["age"],
            "auction_state": auction["state"], "auction_direction": auction["direction"],
        },
        "professional_confirmation": {
            "hypothesis": thesis or setup,
            "proof_state": state,
            "confirmation_lifecycle": confirmation_lifecycle,
            "trigger_is_not_confirmation": True,
            "closed_candle_required": True,
            "lookahead_used": False,
            "evidence_count": len(ledger),
            "pass_count": sum(v["state"] == "PASS" for v in ledger.values()),
            "fail_count": sum(v["state"] == "FAIL" for v in ledger.values()),
            "pending_count": sum(v["state"] == "PENDING" for v in ledger.values()),
            "unavailable_count": sum(v["state"] == "UNAVAILABLE" for v in ledger.values()),
            "observed_evidence_count": len(observed_evidence),
            "missing_evidence_count": len(missing_evidence),
            "next_required_event": next_event,
        },
    }

    reasons = ["EVIDENCE_LEDGER_EVALUATED", "CLOSED_CANDLE_ONLY", "TRIGGER_SEPARATED_FROM_CONFIRMATION", "OBSERVED_EVIDENCE_EXPOSED", "MISSING_EVIDENCE_EXPOSED", "NEXT_REQUIRED_EVENT_EXPOSED"]
    if invalidated:
        reasons += ["CONFIRMATION_INVALIDATED", "COUNTER_EVIDENCE_PRESENT"]
    elif confirmed:
        reasons += ["ALL_REQUIRED_PROOF_GATES_PASS", "FOLLOW_THROUGH_CONFIRMED"]
    else:
        reasons += ["PROOF_GATES_INCOMPLETE"]
    return EngineResult("E7", NAME, confirmed, round(score, 2), out, tuple(dict.fromkeys(reasons)))
