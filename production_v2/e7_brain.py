from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Confirmation / Trigger Brain"
QUESTION = "Does the setup have a valid closed-candle confirmation, or what is still missing?"
ARCHITECTURE = "E7_PROFESSIONAL_SETUP_AWARE_CONFIRMATION_BRAIN_V8"
VERSION = "8.0"
ATR_PERIOD = 14
MIN_BARS = 5
FOLLOW_THROUGH_MAX_AGE = 3
MIN_DISPLACEMENT_ATR = 0.55
MIN_CLOSE_POSITION = 0.65
MIN_STRUCTURAL_SPACE_ATR = 0.75
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
    if t in {"BUY", "BULLISH", "UP", "LONG", "BUYERS", "TREND_UP"}:
        return "BUY"
    if t in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS", "TREND_DOWN"}:
        return "SELL"
    return "NEUTRAL"


def _dedupe(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(v) for v in values if v))


def _atr(bars: list[dict[str, Any]], period: int = ATR_PERIOD) -> float:
    if len(bars) < 2:
        return 0.0
    trs: list[float] = []
    start = max(1, len(bars) - period)
    for i in range(start, len(bars)):
        h = _num(bars[i].get("high"))
        l = _num(bars[i].get("low"))
        pc = _num(bars[i - 1].get("close"))
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return mean(trs) if trs else 0.0


def _candle(bar: dict[str, Any], previous: dict[str, Any], atr: float) -> dict[str, Any]:
    o = _num(bar.get("open")); h = _num(bar.get("high")); l = _num(bar.get("low")); c = _num(bar.get("close"))
    po = _num(previous.get("open")); pc = _num(previous.get("close"))
    rng = max(h - l, 1e-9)
    body = abs(c - o)
    body_atr = body / max(atr, 1e-9)
    close_position = max(0.0, min(1.0, (c - l) / rng))
    return {
        "open": o, "high": h, "low": l, "close": c, "range": rng, "body": body,
        "body_atr": body_atr, "close_position": close_position,
        "bullish": c > o, "bearish": c < o,
        "bullish_engulf": o <= pc and c >= po and c > o,
        "bearish_engulf": o >= pc and c <= po and c < o,
        "bullish_displacement": c > o and body_atr >= MIN_DISPLACEMENT_ATR and close_position >= MIN_CLOSE_POSITION,
        "bearish_displacement": c < o and body_atr >= MIN_DISPLACEMENT_ATR and close_position <= 1.0 - MIN_CLOSE_POSITION,
    }


def _e4(e4: dict[str, Any]) -> dict[str, Any]:
    event = _text(e4.get("event", e4.get("finding")))
    state = _text(e4.get("auction_state", e4.get("state")))
    direction = _direction(e4.get("direction"))
    level = _num(e4.get("event_level"))
    age = max(0, int(_num(e4.get("event_age_bars"))))
    if direction == "NEUTRAL":
        if any(x in event for x in ("HIGH_FAILED_BREAK_RECLAIM", "HIGH_SWEEP_REJECTION", "HIGH_REJECTION")):
            direction = "SELL"
        elif any(x in event for x in ("LOW_FAILED_BREAK_RECLAIM", "LOW_SWEEP_REJECTION", "LOW_REJECTION")):
            direction = "BUY"
        elif any(x in event for x in ("HIGH_ACCEPTANCE", "HIGH_BREAK")):
            direction = "BUY"
        elif any(x in event for x in ("LOW_ACCEPTANCE", "LOW_BREAK")):
            direction = "SELL"
    terminal = state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "REJECTED"} or "TERMINAL" in state
    return {
        "event": event, "state": state, "direction": direction, "level": level, "age": age,
        "terminal": terminal, "pending": state == "PENDING" or "PENDING" in event,
        "event_id": str(e4.get("event_id") or e4.get("event_candle_id") or ""),
        "quality": _num(e4.get("auction_quality")),
        "response_actor": _text(e4.get("response_actor")),
    }


def _base(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION,
        "role": "CONFIRMATION_ANALYST", "reasoning_role": "CONFIRMATION_ANALYST",
        "decision_authority": "E9", "trade_decision_authority": False,
        "closed_candle_only": True, "lookahead": False, "bar_count": len(snapshot.get("bars") or []),
    }


def _professional_reasoning(*, conclusion: str, thesis: str, observed: list[str], missing: list[str],
                            support: list[str], counter: list[str], invalidation: list[str],
                            lifecycle: dict[str, Any], next_event: str, ledger: dict[str, Any],
                            proof: dict[str, Any]) -> dict[str, Any]:
    states = [v.get("state") for v in ledger.values() if isinstance(v, dict)]
    return {
        "question": QUESTION, "conclusion": conclusion, "hypothesis": thesis,
        "evidence": observed, "observed_evidence": observed, "missing_evidence": missing,
        "supporting_evidence": support, "counter_evidence": counter, "invalidation": invalidation,
        "confirmation_lifecycle": lifecycle, "next_required_event": next_event, "proof_gates": proof,
        "evidence_ledger_summary": {
            "total": len(states), "pass": sum(s == "PASS" for s in states),
            "fail": sum(s == "FAIL" for s in states), "pending": sum(s == "PENDING" for s in states),
            "unavailable": sum(s == "UNAVAILABLE" for s in states),
        },
        "decision_path": [
            "E6 thesis is a hypothesis; E7 must independently prove it.",
            "Only completed candles are admissible; the current open candle is never used.",
            "A trigger is a candidate event, not confirmation.",
            "Confirmation requires setup-specific proof plus follow-through when the setup needs it.",
            "Counter-evidence and invalidation outrank a positive trigger.",
            "A confirmation remains valid only while its lifecycle has not expired or invalidated.",
            "E7 reports evidence; E9 retains trade-decision authority.",
        ],
        "reasoning_trace_version": "E7_V8_EXPLICIT_AUDIT",
    }


def _empty(snapshot: dict[str, Any], reason: str) -> EngineResult:
    observed = [f"context=INSUFFICIENT reason={reason}"]
    missing = ["valid directional setup thesis", "valid closed-candle confirmation"]
    next_event = "E6_RESOLVED_THESIS_AND_CLOSED_CANDLE_PROOF"
    lifecycle = {"state": "WAIT", "trigger": "NOT_OBSERVED", "confirmation": "NOT_PROVEN",
                 "follow_through": "UNAVAILABLE", "invalidation": "NONE", "next_required_event": next_event}
    out = {
        **_base(snapshot), "state": "WAIT", "confirmation": "UNRESOLVED", "trigger_status": "NOT_EVALUATED",
        "direction": "NEUTRAL", "setup": "NONE", "candidate_setup_thesis": "", "trigger_observed": False,
        "confirmation_strength": "NONE", "confirmation_score": 0.0, "supporting_evidence": [],
        "counter_evidence": [reason], "observed_evidence": observed, "missing_evidence": missing,
        "next_required_evidence": missing, "next_required_event": next_event,
        "invalidation": ["new closed candle may replace the thesis"], "proof_gates": {},
        "evidence_ledger": {}, "confirmation_lifecycle": lifecycle, "observations": observed,
        "reasoning_trace": {"conclusion": "Confirmation cannot be evaluated from current context.",
                            "why_not_confirmed": missing, "next_required_event": next_event},
    }
    out["professional_reasoning"] = _professional_reasoning(
        conclusion=out["reasoning_trace"]["conclusion"], thesis="", observed=observed, missing=missing,
        support=[], counter=[reason], invalidation=out["invalidation"], lifecycle=lifecycle,
        next_event=next_event, ledger={}, proof={})
    return EngineResult("E7", NAME, False, 0.0, out, ("INSUFFICIENT_CONTEXT",))


def _setup_family(setup: str) -> str:
    s = _text(setup)
    aliases = {
        "TREND_PULLBACK": "TREND_PULLBACK_CONTINUATION",
        "PULLBACK": "TREND_PULLBACK_CONTINUATION",
        "IMPULSE_CONTINUATION": "IMPULSE_CONTINUATION",
        "AUCTION_ACCEPTANCE": "AUCTION_ACCEPTANCE_CONTINUATION",
    }
    return aliases.get(s, s)


def analyze_e7(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    bars = list(snapshot.get("bars") or [])
    e6 = upstream.get("E6")
    if len(bars) < MIN_BARS or not e6:
        return _empty(snapshot, "MISSING_SETUP_CONTEXT")

    e6o = dict(e6.output or {})
    e3o = dict((upstream.get("E3").output if upstream.get("E3") else {}) or {})
    e4o = dict((upstream.get("E4").output if upstream.get("E4") else {}) or {})
    e5o = dict((upstream.get("E5").output if upstream.get("E5") else {}) or {})

    direction = _direction(e6o.get("direction", e6o.get("direction_thesis")))
    setup = _setup_family(e6o.get("setup", e6o.get("setup_family"))) or "NONE"
    thesis = str(e6o.get("candidate_setup_thesis") or e6o.get("thesis") or "")
    maturity = _text(e6o.get("maturity", e6o.get("stage", e6o.get("formation_stage")))) or "UNRESOLVED"
    atr = max(_atr(bars), 1e-9)
    current = _candle(bars[-1], bars[-2], atr)
    previous = _candle(bars[-2], bars[-3], atr)
    auction = _e4(e4o)

    observed: list[str] = []
    missing: list[str] = []
    support: list[str] = []
    counter: list[str] = []
    invalid: list[str] = []
    ledger: dict[str, dict[str, Any]] = {}
    proof: dict[str, Any] = {}

    def rec(name: str, state: str, observed_value: Any, required: Any, interpretation: str) -> str:
        state = _text(state) if _text(state) in VALID_STATES else "UNAVAILABLE"
        ledger[name] = {"state": state, "observed": observed_value, "required": required, "interpretation": interpretation}
        observed.append(f"{name}={observed_value}")
        if state == "PASS":
            support.append(name.upper())
        elif state == "FAIL":
            counter.append(name.upper())
        else:
            missing.append(name)
        return state

    if direction not in {"BUY", "SELL"}:
        rec("direction_resolved", "FAIL", "NEUTRAL", "BUY or SELL", "E6 has not supplied a directional hypothesis.")
        next_event = "E6_RESOLVED_DIRECTIONAL_THESIS"
        lifecycle = {"state": "UNRESOLVED", "trigger": "NOT_OBSERVED", "confirmation": "NOT_PROVEN",
                     "follow_through": "UNAVAILABLE", "invalidation": "NONE", "next_required_event": next_event}
        out = {**_base(snapshot), "state": "UNRESOLVED", "confirmation": maturity if maturity != "UNRESOLVED" else "UNRESOLVED",
               "trigger_status": "NOT_CONFIRMED", "direction": "NEUTRAL", "setup": setup,
               "candidate_setup_thesis": thesis, "trigger_observed": False, "confirmation_strength": "NONE",
               "confirmation_score": 0.0, "supporting_evidence": support, "counter_evidence": counter,
               "observed_evidence": observed, "missing_evidence": missing,
               "next_required_evidence": ["E6 must expose a resolved BUY/SELL thesis"],
               "next_required_event": next_event, "invalidation": ["new closed candle changes the setup thesis"],
               "proof_gates": {"direction_resolved": "FAIL"}, "evidence_ledger": ledger,
               "confirmation_lifecycle": lifecycle, "observations": observed,
               "reasoning_trace": {"conclusion": "No directional thesis can be confirmed.",
                                   "why_not_confirmed": missing, "next_required_event": next_event}}
        out["professional_reasoning"] = _professional_reasoning(
            conclusion=out["reasoning_trace"]["conclusion"], thesis=thesis, observed=observed,
            missing=missing, support=support, counter=counter, invalidation=out["invalidation"],
            lifecycle=lifecycle, next_event=next_event, ledger=ledger, proof=out["proof_gates"])
        return EngineResult("E7", NAME, False, 0.0, out, ("SETUP_DIRECTION_UNRESOLVED",))

    buy = direction == "BUY"
    close_ok = current["close_position"] >= MIN_CLOSE_POSITION if buy else current["close_position"] <= 1.0 - MIN_CLOSE_POSITION
    directional = current["bullish"] if buy else current["bearish"]
    displacement = current["bullish_displacement"] if buy else current["bearish_displacement"]
    engulf = current["bullish_engulf"] if buy else current["bearish_engulf"]
    trigger = bool(directional and close_ok and (displacement or engulf))

    rec("directional_closed_candle", "PASS" if directional else "FAIL", directional, True,
        "Latest closed candle direction agrees with E6.")
    rec("close_location", "PASS" if close_ok else "FAIL", round(current["close_position"], 4),
        ">=0.65 BUY / <=0.35 SELL", "Close must finish decisively on the thesis side.")
    rec("directional_displacement", "PASS" if displacement else "PENDING", round(current["body_atr"], 4),
        f">={MIN_DISPLACEMENT_ATR} ATR", "Displacement is a trigger component, not confirmation alone.")
    rec("engulfing_response", "PASS" if engulf else "UNAVAILABLE", engulf, True,
        "Optional corroborating response; absence does not veto displacement.")
    rec("closed_candle_trigger", "PASS" if trigger else "FAIL", trigger, True,
        "Trigger means a candidate closed-candle event exists; it is not confirmation.")

    protected_high = _num(e3o.get("protected_high"))
    protected_low = _num(e3o.get("protected_low"))
    structure_finding = _text(e3o.get("finding", e3o.get("structure_state")))
    external = _direction(e3o.get("external_state", e3o.get("external_count_state")))
    internal = _direction(e3o.get("internal_state", e3o.get("internal_count_state")))
    structure_conflict = "MIXED" in structure_finding or "TRANSITION" in structure_finding or (
        external in {"BUY", "SELL"} and internal in {"BUY", "SELL"} and external != internal
    )
    structure_aligned = not structure_conflict and (external in {"NEUTRAL", direction} or internal in {"NEUTRAL", direction})
    rec("structure_alignment", "PASS" if structure_aligned else "FAIL", structure_finding or "UNAVAILABLE",
        f"aligned_with={direction}", "Structure must not directly contradict the setup thesis.")

    if buy and protected_low and current["close"] < protected_low:
        invalid.append(f"CLOSE_BELOW_PROTECTED_LOW={protected_low:.5f}")
    if not buy and protected_high and current["close"] > protected_high:
        invalid.append(f"CLOSE_ABOVE_PROTECTED_HIGH={protected_high:.5f}")
    if invalid:
        rec("thesis_invalidation", "FAIL", invalid[-1], "no protected-level invalidation", "A closed-candle structural break invalidates the thesis.")
    else:
        rec("thesis_invalidation", "PASS", "NONE", "no protected-level invalidation", "No closed-candle structural invalidation is present.")

    space = _num(e5o.get("available_space_atr_long" if buy else "available_space_atr_short"), 0.0)
    space_ok = space >= MIN_STRUCTURAL_SPACE_ATR if e5o else False
    rec("structural_space", "PASS" if space_ok else "PENDING", round(space, 4),
        f">={MIN_STRUCTURAL_SPACE_ATR} ATR", "Space is an economic filter; it does not create confirmation.")

    event_direction_ok = auction["direction"] in {"NEUTRAL", direction}
    event_fresh = auction["age"] <= FOLLOW_THROUGH_MAX_AGE
    event_present = bool(auction["event"] and "NO_CONFIRMED" not in auction["event"] and "NO_LIQUIDITY" not in auction["event"])
    event_terminal = bool(auction["terminal"])
    response_present = auction["response_actor"] not in {"", "UNKNOWN", "NONE", "UNCLEAR"}
    rec("auction_direction", "PASS" if event_direction_ok else "FAIL", auction["direction"], direction,
        "Auction event must not oppose the setup direction.")
    rec("auction_freshness", "PASS" if event_fresh else "FAIL", auction["age"], f"<= {FOLLOW_THROUGH_MAX_AGE} bars",
        "A stale event cannot confirm a new trigger.")
    rec("auction_event", "PASS" if event_present else "PENDING", auction["event"] or "NONE",
        "setup-relevant event", "The setup must have an identifiable event or explicit trigger evidence.")

    setup_gates: dict[str, str] = {}
    if "AUCTION_ACCEPTANCE" in setup:
        acceptance_event = "ACCEPTANCE" in auction["event"]
        acceptance_proof = event_present and event_direction_ok and (event_terminal or (trigger and response_present))
        follow = trigger and (current["close_position"] >= MIN_CLOSE_POSITION if buy else current["close_position"] <= 1.0 - MIN_CLOSE_POSITION)
        setup_gates["auction_acceptance"] = rec("setup.auction_acceptance", "PASS" if acceptance_proof else "PENDING",
            {"event": auction["event"], "terminal": event_terminal, "response": response_present},
            "terminal acceptance or closed-candle acceptance + response", "Acceptance is not complete until the auction proves acceptance.")
        setup_gates["directional_follow_through"] = rec("setup.directional_follow_through", "PASS" if follow else "PENDING",
            trigger, "closed-candle directional follow-through", "The acceptance thesis needs price to continue in the thesis direction.")
        if not acceptance_event:
            missing.append("setup-specific acceptance event")
    elif "LIQUIDITY_REVERSAL" in setup:
        sweep = any(x in auction["event"] for x in ("SWEEP", "FAILED_BREAK_RECLAIM", "REJECTION"))
        reclaim = trigger and event_direction_ok
        setup_gates["liquidity_sweep"] = rec("setup.liquidity_sweep", "PASS" if sweep else "PENDING", sweep,
            "sweep/rejection/failed-break event", "A reversal requires evidence that liquidity was actually taken.")
        setup_gates["reclaim_response"] = rec("setup.reclaim_response", "PASS" if reclaim else "PENDING", reclaim,
            "closed-candle reclaim in thesis direction", "Reclaim separates a reversal thesis from a mere wick.")
    elif "BREAKOUT_RETEST" in setup:
        bos = _text(e3o.get("bos", e3o.get("break_of_structure"))) in {"BREAK", "BOS", "YES", "CONFIRMED"} or "BREAK" in auction["event"]
        retest = "RETEST" in auction["event"] or (trigger and event_present)
        setup_gates["break_event"] = rec("setup.break_event", "PASS" if bos else "PENDING", bos,
            "confirmed break", "Retest logic is invalid without a causal break.")
        setup_gates["retest_response"] = rec("setup.retest_response", "PASS" if retest else "PENDING", retest,
            "retest followed by directional close", "The retest must reject/hold and continue.")
    elif "BREAKOUT" in setup:
        bos = _text(e3o.get("bos", e3o.get("break_of_structure"))) in {"BREAK", "BOS", "YES", "CONFIRMED"} or "BREAK" in auction["event"]
        expansion = trigger and displacement
        setup_gates["break_event"] = rec("setup.break_event", "PASS" if bos else "PENDING", bos,
            "confirmed break", "Breakout requires a closed-candle break, not an intrabar touch.")
        setup_gates["expansion"] = rec("setup.expansion", "PASS" if expansion else "PENDING", expansion,
            "directional displacement", "Expansion demonstrates participation after the break.")
    elif "TREND_PULLBACK" in setup:
        pullback = "PULLBACK" in _text(e6o.get("candidate_setup_thesis", "")) or "PULLBACK" in setup
        continuation = trigger and structure_aligned
        setup_gates["pullback_context"] = rec("setup.pullback_context", "PASS" if pullback else "PENDING", pullback,
            "pullback context", "Continuation cannot be confirmed without a pullback context.")
        setup_gates["continuation_close"] = rec("setup.continuation_close", "PASS" if continuation else "PENDING", continuation,
            "closed-candle continuation", "The continuation candle must agree with structure and direction.")
    else:
        setup_gates["generic_setup_proof"] = rec("setup.generic_setup_proof", "PASS" if trigger else "PENDING", trigger,
            "closed-candle setup-specific proof", "Unknown setup families require an explicit closed-candle proof.")

    if trigger:
        follow_through = "PENDING_NEXT_CLOSED_CANDLE"
        rec("follow_through", "PENDING", "TRIGGER_ON_LATEST_CLOSED_CANDLE", "subsequent closed candle", "The next candle does not exist yet; confirmation cannot borrow future evidence.")
        missing.append("FOLLOW_THROUGH_CLOSED_CANDLE")
        next_event = "NEXT_CLOSED_CANDLE_THESIS_FOLLOW_THROUGH"
    elif previous["bullish"] if buy else previous["bearish"]:
        prev_close_ok = previous["close_position"] >= MIN_CLOSE_POSITION if buy else previous["close_position"] <= 1.0 - MIN_CLOSE_POSITION
        follow_through = "PENDING_CURRENT_CANDLE" if prev_close_ok else "NOT_PROVEN"
        rec("follow_through", "PENDING" if prev_close_ok else "FAIL", prev_close_ok,
            "current closed candle follows previous trigger", "Follow-through must be observed after the trigger, never assumed.")
        next_event = "CURRENT_CLOSED_CANDLE_FOLLOW_THROUGH" if prev_close_ok else "NEW_SETUP_SPECIFIC_TRIGGER"
    else:
        follow_through = "NOT_OBSERVED"
        rec("follow_through", "PENDING", "NOT_OBSERVED", "closed-candle follow-through", "No valid trigger has yet started a confirmation lifecycle.")
        next_event = "VALID_CLOSED_CANDLE_TRIGGER"

    if structure_conflict:
        counter.append("STRUCTURE_COUNTER_EVIDENCE")
    if auction["pending"] and not auction["terminal"]:
        counter.append("AUCTION_PENDING")
    if space and space < MIN_STRUCTURAL_SPACE_ATR:
        counter.append("STRUCTURAL_SPACE_CONSTRAINED")
    if direction == "BUY" and current["bearish"]:
        counter.append("BEARISH_CLOSED_CANDLE_COUNTER_EVIDENCE")
    if direction == "SELL" and current["bullish"]:
        counter.append("BULLISH_CLOSED_CANDLE_COUNTER_EVIDENCE")
    counter = _dedupe(counter)

    invalidated = bool(invalid)
    if invalidated:
        confirmation = "INVALIDATED"
        state = "INVALIDATED"
        trigger_status = "INVALIDATED"
        score = 0.0
        next_event = "E6_NEW_SETUP_AFTER_INVALIDATION"
        missing.append("new valid setup thesis")
    else:
        all_setup_pass = all(v == "PASS" for v in setup_gates.values()) if setup_gates else False
        hard_conflicts = any(x in counter for x in ("STRUCTURE_COUNTER_EVIDENCE", "BEARISH_CLOSED_CANDLE_COUNTER_EVIDENCE", "BULLISH_CLOSED_CANDLE_COUNTER_EVIDENCE"))
        follow_proven = event_terminal and event_direction_ok and event_fresh
        confirmation_allowed = trigger and all_setup_pass and structure_aligned and space_ok and not hard_conflicts and follow_proven
        if confirmation_allowed:
            confirmation = "CONFIRMED"
            state = "CONFIRMED"
            trigger_status = "CONFIRMED"
            score = 92.0
            next_event = "MONITOR_CONFIRMED_THESIS_INVALIDATION"
        else:
            confirmation = maturity if maturity != "UNRESOLVED" else "DEVELOPING"
            state = "WAIT"
            trigger_status = "TRIGGER_OBSERVED" if trigger else "NOT_CONFIRMED"
            score = min(79.0, 45.0 + 8.0 * sum(v == "PASS" for v in proof.values()))
            if trigger and not follow_proven:
                missing.append("FOLLOW_THROUGH_CLOSED_CANDLE")
                next_event = "NEXT_CLOSED_CANDLE_THESIS_FOLLOW_THROUGH"
            elif not trigger:
                next_event = "VALID_CLOSED_CANDLE_TRIGGER"

    proof = {k: v for k, v in setup_gates.items()}
    proof.update({
        "trigger": "PASS" if trigger else "FAIL",
        "structure_alignment": "PASS" if structure_aligned else "FAIL",
        "structural_space": "PASS" if space_ok else "PENDING",
        "auction_terminal": "PASS" if auction["terminal"] else "PENDING",
        "follow_through": "PASS" if (auction["terminal"] and trigger) else "PENDING",
        "invalidation": "FAIL" if invalidated else "PASS",
    })
    proof_pass = sum(v == "PASS" for v in proof.values())
    proof_total = max(1, len(proof))
    observed = _dedupe(observed + [
        f"setup={setup}", f"direction={direction}", f"maturity={maturity}",
        f"trigger={trigger}", f"auction_event={auction['event'] or 'NONE'}",
        f"auction_state={auction['state'] or 'NONE'}", f"auction_age_bars={auction['age']}",
        f"current_body_atr={current['body_atr']:.4f}", f"current_close_position={current['close_position']:.4f}",
        f"proof_pass_ratio={proof_pass}/{proof_total}",
    ])
    missing = _dedupe(missing)
    support = _dedupe(support)
    invalid = _dedupe(invalid)
    next_required = _dedupe(missing[:])
    lifecycle = {
        "state": state, "trigger": "OBSERVED" if trigger else "NOT_OBSERVED",
        "confirmation": confirmation, "follow_through": follow_through,
        "invalidation": invalid or "NONE", "next_required_event": next_event,
        "setup": setup, "direction": direction, "event_age_bars": auction["age"],
    }
    conclusion = (
        "Closed-candle evidence confirms the setup."
        if confirmation == "CONFIRMED" else
        "Closed-candle evidence invalidates the current setup thesis."
        if confirmation == "INVALIDATED" else
        "The thesis is still a hypothesis; confirmation is not yet proven."
    )
    reasons = []
    if confirmation == "CONFIRMED":
        reasons.append("CONFIRMATION_PROVEN")
    elif confirmation == "INVALIDATED":
        reasons.append("CONFIRMATION_INVALIDATED")
    else:
        reasons.append("PROOF_GATES_INCOMPLETE")
    if trigger:
        reasons.append("TRIGGER_OBSERVED_NOT_AUTOMATIC_CONFIRMATION")
    else:
        reasons.append("VALID_CLOSED_CANDLE_TRIGGER_MISSING")
    if missing:
        reasons.append("MISSING_EVIDENCE_EXPOSED")
    if counter:
        reasons.append("COUNTER_EVIDENCE_PRESENT")
    reasons += [
        "CLOSED_CANDLE_ONLY", "SETUP_SPECIFIC_PROOF_EVALUATED", "FOLLOW_THROUGH_EVALUATED",
        "INVALIDATION_EVALUATED", "CONFIRMATION_LIFECYCLE_EXPOSED", "EVIDENCE_LEDGER_EVALUATED",
        "OBSERVED_EVIDENCE_EXPOSED", "NEXT_REQUIRED_EVENT_EXPOSED", "TRIGGER_SEPARATED_FROM_CONFIRMATION",
        "PROFESSIONAL_REASONING_EXPOSED",
    ]

    out = {
        **_base(snapshot), "state": state, "confirmation": confirmation,
        "trigger_status": trigger_status, "direction": direction, "setup": setup,
        "setup_family": setup, "candidate_setup_thesis": thesis, "maturity": maturity,
        "trigger_observed": trigger, "confirmation_strength": "HIGH" if confirmation == "CONFIRMED" else "NONE" if confirmation == "INVALIDATED" else "DEVELOPING",
        "confirmation_score": round(score, 2), "supporting_evidence": support,
        "counter_evidence": counter, "observed_evidence": observed, "missing_evidence": missing,
        "next_required_evidence": next_required, "next_required_event": next_event,
        "invalidation": invalid or ["closed-candle structural break or setup-specific contradiction"],
        "proof_gates": proof, "evidence_ledger": ledger, "confirmation_lifecycle": lifecycle,
        "trigger": {
            "observed": trigger, "direction": direction, "closed_candle": True,
            "body_atr": round(current["body_atr"], 4), "close_position": round(current["close_position"], 4),
            "is_confirmation": False,
        },
        "follow_through": {"state": follow_through, "required": "subsequent closed-candle evidence"},
        "reasoning_trace": {
            "conclusion": conclusion, "why_not_confirmed": missing,
            "observed": observed, "counter_evidence": counter,
            "next_required_event": next_event, "setup_specific_proof": setup_gates,
        },
        "observations": observed, "reason_codes": _dedupe(reasons),
    }
    out["professional_reasoning"] = _professional_reasoning(
        conclusion=conclusion, thesis=thesis, observed=observed, missing=missing,
        support=support, counter=counter, invalidation=out["invalidation"],
        lifecycle=lifecycle, next_event=next_event, ledger=ledger, proof=proof)

    gate_passed = confirmation == "CONFIRMED"
    return EngineResult("E7", NAME, gate_passed, score, out, tuple(_dedupe(reasons)))
