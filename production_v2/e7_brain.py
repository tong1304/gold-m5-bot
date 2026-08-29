from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Confirmation / Trigger Brain"
QUESTION = "Does the setup have a valid closed-candle confirmation, or what is still missing?"
ARCHITECTURE = "E7_PROFESSIONAL_SETUP_AWARE_CONFIRMATION_BRAIN_V11"
VERSION = "11.0"
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
        h = _num(bars[i].get("high")); l = _num(bars[i].get("low")); pc = _num(bars[i - 1].get("close"))
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return mean(trs) if trs else 0.0


def _candle(bar: dict[str, Any], previous: dict[str, Any], atr: float) -> dict[str, Any]:
    o = _num(bar.get("open")); h = _num(bar.get("high")); l = _num(bar.get("low")); c = _num(bar.get("close"))
    po = _num(previous.get("open")); pc = _num(previous.get("close"))
    rng = max(h - l, 1e-9); body = abs(c - o); body_atr = body / max(atr, 1e-9)
    close_position = max(0.0, min(1.0, (c - l) / rng))
    return {
        "open": o, "high": h, "low": l, "close": c, "range": rng, "body": body,
        "body_atr": body_atr, "close_position": close_position,
        "bullish": c > o, "bearish": c < o,
        "bullish_engulf": o <= pc and c >= po and c > o,
        "bearish_engulf": o >= pc and c <= po and c < o,
    }


def _e4(e4: dict[str, Any]) -> dict[str, Any]:
    event = _text(e4.get("event", e4.get("finding"))); state = _text(e4.get("auction_state", e4.get("state")))
    direction = _direction(e4.get("direction"))
    if direction == "NEUTRAL":
        if any(x in event for x in ("HIGH_FAILED_BREAK_RECLAIM", "HIGH_SWEEP_REJECTION", "HIGH_REJECTION")): direction = "SELL"
        elif any(x in event for x in ("LOW_FAILED_BREAK_RECLAIM", "LOW_SWEEP_REJECTION", "LOW_REJECTION")): direction = "BUY"
        elif any(x in event for x in ("HIGH_ACCEPTANCE", "HIGH_BREAK")): direction = "BUY"
        elif any(x in event for x in ("LOW_ACCEPTANCE", "LOW_BREAK")): direction = "SELL"
    age = max(0, int(_num(e4.get("event_age_bars"))))
    terminal = state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "REJECTED"} or "TERMINAL" in state
    return {
        "event": event, "state": state, "direction": direction, "level": _num(e4.get("event_level")), "age": age,
        "terminal": terminal, "pending": state == "PENDING" or "PENDING" in event,
        "event_id": str(e4.get("event_id") or e4.get("event_candle_id") or ""),
        "quality": _num(e4.get("auction_quality")), "response_actor": _text(e4.get("response_actor")),
    }


def _base(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION,
        "role": "CONFIRMATION_ANALYST", "reasoning_role": "CONFIRMATION_ANALYST",
        "decision_authority": "E9", "trade_decision_authority": False,
        "closed_candle_only": True, "lookahead": False, "bar_count": len(snapshot.get("bars") or []),
    }


def _reasoning(*, conclusion: str, thesis: str, observed: list[str], missing: list[str], support: list[str],
               counter: list[str], invalidation: list[str], lifecycle: dict[str, Any], next_event: str,
               ledger: dict[str, Any], proof: dict[str, Any]) -> dict[str, Any]:
    states = [v.get("state") for v in ledger.values() if isinstance(v, dict)]
    return {
        "question": QUESTION, "conclusion": conclusion, "hypothesis": thesis,
        "evidence": observed, "observed_evidence": observed, "missing_evidence": missing,
        "supporting_evidence": support, "counter_evidence": counter, "invalidation": invalidation,
        "confirmation_lifecycle": lifecycle, "next_required_event": next_event, "proof_gates": proof,
        "evidence_ledger_summary": {"total": len(states), "pass": sum(s == "PASS" for s in states),
                                    "fail": sum(s == "FAIL" for s in states), "pending": sum(s == "PENDING" for s in states),
                                    "unavailable": sum(s == "UNAVAILABLE" for s in states)},
        "decision_path": [
            "E6 supplies the hypothesis; E7 never creates a new setup thesis.",
            "Only completed candles are admissible; the current open candle is excluded.",
            "A trigger is candidate evidence and never equals confirmation by itself.",
            "Confirmation requires setup-specific proof plus causal closed-candle follow-through, or a setup-relevant terminal auction proof.",
            "Follow-through validates the immediately preceding trigger; future candles are never borrowed.",
            "Explicit invalidation has absolute priority over positive confirmation evidence.",
            "Counter-evidence is disclosed and weighted; it becomes invalidation only when the thesis-specific invalidation rule is met.",
            "Structural space is downstream economic context and never creates confirmation.",
            "E7 reports confirmation evidence; E9 retains trade-decision authority.",
        ],
        "reasoning_trace_version": "E7_V11_CAUSAL_CONFIRMATION_AUDIT",
    }


def _empty(snapshot: dict[str, Any], reason: str) -> EngineResult:
    observed = [f"context=INSUFFICIENT reason={reason}"]
    missing = ["valid directional setup thesis", "valid closed-candle confirmation"]
    next_event = "E6_RESOLVED_THESIS_AND_CLOSED_CANDLE_PROOF"
    lifecycle = {"state": "WAIT", "trigger": "NOT_OBSERVED", "confirmation": "NOT_PROVEN", "follow_through": "UNAVAILABLE", "invalidation": "NONE", "next_required_event": next_event}
    out = {**_base(snapshot), "state": "WAIT", "confirmation": "UNRESOLVED", "trigger_status": "NOT_EVALUATED", "direction": "NEUTRAL", "setup": "NONE", "setup_family": "NONE", "candidate_setup_thesis": "", "trigger_observed": False, "confirmation_strength": "NONE", "confirmation_score": 0.0, "supporting_evidence": [], "counter_evidence": [reason], "observed_evidence": observed, "missing_evidence": missing, "next_required_evidence": missing, "next_required_event": next_event, "invalidation": ["new closed candle may replace the thesis"], "proof_gates": {}, "evidence_ledger": {}, "confirmation_lifecycle": lifecycle, "observations": observed, "reasoning_trace": {"conclusion": "Confirmation cannot be evaluated from current context.", "why_not_confirmed": missing, "next_required_event": next_event}}
    out["professional_reasoning"] = _reasoning(conclusion=out["reasoning_trace"]["conclusion"], thesis="", observed=observed, missing=missing, support=[], counter=[reason], invalidation=out["invalidation"], lifecycle=lifecycle, next_event=next_event, ledger={}, proof={})
    return EngineResult("E7", NAME, False, 0.0, out, ("INSUFFICIENT_CONTEXT",))


def _setup_family(setup: Any) -> str:
    s = _text(setup)
    return {
        "TREND_PULLBACK": "TREND_PULLBACK_CONTINUATION",
        "PULLBACK": "TREND_PULLBACK_CONTINUATION",
        "IMPULSE_CONTINUATION": "IMPULSE_CONTINUATION",
        "AUCTION_ACCEPTANCE": "AUCTION_ACCEPTANCE_CONTINUATION",
    }.get(s, s)


def _no_setup(snapshot: dict[str, Any], e6o: dict[str, Any], reason: str) -> EngineResult:
    thesis = str(e6o.get("candidate_setup_thesis") or e6o.get("thesis") or "")
    observed = [
        f"e6_setup={_text(e6o.get('setup', e6o.get('setup_family'))) or 'NONE'}",
        f"e6_direction={_direction(e6o.get('direction', e6o.get('direction_thesis')))}",
        f"e6_finding={_text(e6o.get('finding', '')) or 'UNRESOLVED'}",
        f"setup_status={reason}",
    ]
    missing = ["new E6 setup thesis that survives causal screening"]
    next_event = "E6_NEW_SURVIVING_SETUP_THESIS"
    lifecycle = {"state": "NO_SETUP", "trigger": "NOT_ALLOWED", "confirmation": "NOT_APPLICABLE", "follow_through": "NOT_APPLICABLE", "invalidation": "CURRENT_THESIS_NOT_ESTABLISHED", "next_required_event": next_event}
    reasons = ("NO_SURVIVING_SETUP", "CONFIRMATION_NOT_APPLICABLE", "E7_DID_NOT_CREATE_THESIS")
    ledger = {"surviving_setup": {"state": "FAIL", "observed": reason, "required": "E6 surviving setup", "interpretation": "E7 cannot confirm an absent thesis."}}
    out = {**_base(snapshot), "state": "NO_SETUP", "confirmation": "NO_SURVIVING_SETUP", "trigger_status": "NOT_ALLOWED", "direction": _direction(e6o.get("direction", e6o.get("direction_thesis"))), "setup": "NONE", "setup_family": "NONE", "candidate_setup_thesis": thesis, "trigger_observed": False, "confirmation_strength": "NONE", "confirmation_score": 0.0, "supporting_evidence": [], "counter_evidence": [reason], "observed_evidence": observed, "missing_evidence": missing, "next_required_evidence": missing, "next_required_event": next_event, "invalidation": ["E6 must produce a new setup that survives causal screening"], "proof_gates": {"surviving_setup": "FAIL"}, "evidence_ledger": ledger, "confirmation_lifecycle": lifecycle, "observations": observed, "reasoning_trace": {"conclusion": "E6 produced no setup that survives causal screening; E7 will not invent confirmation.", "why_not_confirmed": missing, "next_required_event": next_event}, "reason_codes": list(reasons)}
    out["professional_reasoning"] = _reasoning(conclusion=out["reasoning_trace"]["conclusion"], thesis=thesis, observed=observed, missing=missing, support=[], counter=[reason], invalidation=out["invalidation"], lifecycle=lifecycle, next_event=next_event, ledger=ledger, proof=out["proof_gates"])
    return EngineResult("E7", NAME, False, 0.0, out, reasons)


def analyze_e7(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    bars = list(snapshot.get("bars") or []); e6 = upstream.get("E6")
    if len(bars) < MIN_BARS or not e6:
        return _empty(snapshot, "MISSING_SETUP_CONTEXT")

    e6o = dict(e6.output or {})
    e3o = dict((upstream.get("E3").output if upstream.get("E3") else {}) or {})
    e4o = dict((upstream.get("E4").output if upstream.get("E4") else {}) or {})
    e5o = dict((upstream.get("E5").output if upstream.get("E5") else {}) or {})

    raw_setup = _setup_family(e6o.get("setup", e6o.get("setup_family")))
    e6_finding = _text(e6o.get("finding", "")); e6_state = _text(e6o.get("state", ""))
    e6_maturity = _text(e6o.get("maturity", e6o.get("setup_stage", ""))) or "UNRESOLVED"
    no_setup_markers = {"NONE", "UNKNOWN", "UNRESOLVED", "NO_SETUP", "NO_PLAUSIBLE_SETUP", "NO_SURVIVING_SETUP", "SETUP_NOT_TRADE_READY"}
    if raw_setup in no_setup_markers or any(x in e6_finding for x in ("NO PLAUSIBLE SETUP", "NO SURVIVING SETUP")):
        return _no_setup(snapshot, e6o, "E6_NO_SURVIVING_SETUP")
    if e6_state in {"NO_SETUP", "UNRESOLVED"} and not raw_setup:
        return _no_setup(snapshot, e6o, "E6_SETUP_UNRESOLVED")

    direction = _direction(e6o.get("direction", e6o.get("direction_thesis")))
    thesis = str(e6o.get("candidate_setup_thesis") or e6o.get("thesis") or "")
    setup = raw_setup or "UNKNOWN"
    if direction not in {"BUY", "SELL"}:
        return _no_setup(snapshot, e6o, "E6_DIRECTION_UNRESOLVED")

    buy = direction == "BUY"
    atr = max(_atr(bars), 1e-9)
    current = _candle(bars[-1], bars[-2], atr)
    previous = _candle(bars[-2], bars[-3], atr)
    auction = _e4(e4o)
    observed: list[str] = []; missing: list[str] = []; support: list[str] = []; counter: list[str] = []; invalid: list[str] = []; ledger: dict[str, dict[str, Any]] = {}

    def rec(name: str, state: str, observed_value: Any, required: Any, interpretation: str) -> str:
        normalized = _text(state)
        state = normalized if normalized in VALID_STATES else "UNAVAILABLE"
        ledger[name] = {"state": state, "observed": observed_value, "required": required, "interpretation": interpretation}
        observed.append(f"{name}={observed_value}")
        if state == "PASS": support.append(name.upper())
        elif state == "FAIL": counter.append(name.upper())
        else: missing.append(name)
        return state

    directional = current["bullish"] if buy else current["bearish"]
    close_ok = current["close_position"] >= MIN_CLOSE_POSITION if buy else current["close_position"] <= 1.0 - MIN_CLOSE_POSITION
    displacement = directional and current["body_atr"] >= MIN_DISPLACEMENT_ATR and close_ok
    engulf = current["bullish_engulf"] if buy else current["bearish_engulf"]
    trigger = bool(directional and close_ok and (displacement or engulf))

    previous_directional = previous["bullish"] if buy else previous["bearish"]
    previous_close_ok = previous["close_position"] >= MIN_CLOSE_POSITION if buy else previous["close_position"] <= 1.0 - MIN_CLOSE_POSITION
    previous_displacement = previous_directional and previous["body_atr"] >= MIN_DISPLACEMENT_ATR and previous_close_ok
    previous_engulf = previous["bullish_engulf"] if buy else previous["bearish_engulf"]
    previous_trigger = bool(previous_directional and previous_close_ok and (previous_displacement or previous_engulf))

    rec("directional_closed_candle", "PASS" if directional else "FAIL", directional, True, "Latest closed candle agrees with E6 direction.")
    rec("close_location", "PASS" if close_ok else "FAIL", round(current["close_position"], 4), ">=0.65 BUY / <=0.35 SELL", "The close must finish decisively on the thesis side.")
    rec("directional_displacement", "PASS" if displacement else "PENDING", round(current["body_atr"], 4), f">={MIN_DISPLACEMENT_ATR} ATR", "Displacement is trigger evidence, not confirmation alone.")
    rec("engulfing_response", "PASS" if engulf else "UNAVAILABLE", engulf, True, "Optional corroborating response; absence does not veto displacement.")
    rec("closed_candle_trigger", "PASS" if trigger else "FAIL", trigger, True, "A trigger is candidate evidence and is never confirmation by itself.")
    rec("prior_candle_trigger", "PASS" if previous_trigger else "PENDING", previous_trigger, "required for next-candle causal follow-through", "A later candle may confirm only an already-observed prior trigger.")

    protected_high = _num(e3o.get("protected_high")); protected_low = _num(e3o.get("protected_low"))
    structure_finding = _text(e3o.get("finding", e3o.get("structure_state")))
    external = _direction(e3o.get("external_state", e3o.get("external_count_state")))
    internal = _direction(e3o.get("internal_state", e3o.get("internal_count_state")))
    structure_conflict = "MIXED" in structure_finding or "TRANSITION" in structure_finding or (external in {"BUY", "SELL"} and internal in {"BUY", "SELL"} and external != internal)
    structure_aligned = not structure_conflict and (external in {"NEUTRAL", direction} or internal in {"NEUTRAL", direction})
    rec("structure_alignment", "PASS" if structure_aligned else "FAIL", structure_finding or "UNAVAILABLE", f"aligned_with={direction}", "Structure cannot directly contradict the setup thesis.")

    if buy and protected_low and current["close"] < protected_low:
        invalid.append(f"CLOSE_BELOW_PROTECTED_LOW={protected_low:.5f}")
    if not buy and protected_high and current["close"] > protected_high:
        invalid.append(f"CLOSE_ABOVE_PROTECTED_HIGH={protected_high:.5f}")
    rec("thesis_invalidation", "FAIL" if invalid else "PASS", invalid[-1] if invalid else "NONE", "no protected-level invalidation", "A closed-candle protected-level break invalidates the thesis and outranks positive evidence.")

    space = _num(e5o.get("available_space_atr_long" if buy else "available_space_atr_short"), 0.0)
    space_available = bool(e5o) and space > 0.0
    space_ok = space_available and space >= MIN_STRUCTURAL_SPACE_ATR
    rec("structural_space", "PASS" if space_ok else "PENDING" if space_available else "UNAVAILABLE", round(space, 4), f">={MIN_STRUCTURAL_SPACE_ATR} ATR for downstream economics", "Space informs E8/E9 economics; it never creates confirmation.")

    event_direction_ok = auction["direction"] in {"NEUTRAL", direction}
    event_fresh = auction["age"] <= FOLLOW_THROUGH_MAX_AGE
    event_present = bool(auction["event"] and "NO_CONFIRMED" not in auction["event"] and "NO_LIQUIDITY" not in auction["event"])
    response_present = auction["response_actor"] not in {"", "UNKNOWN", "NONE", "UNCLEAR"}
    rec("auction_direction", "PASS" if event_direction_ok else "FAIL", auction["direction"], direction, "Auction evidence must not oppose the thesis.")
    rec("auction_freshness", "PASS" if event_fresh else "FAIL", auction["age"], f"<= {FOLLOW_THROUGH_MAX_AGE} bars", "Stale auction evidence cannot confirm a current setup.")
    rec("auction_event", "PASS" if event_present else "PENDING", auction["event"] or "NONE", "setup-relevant event", "The setup needs an identifiable causal event when its family requires one.")

    # For a positive confirmation on the second candle, setup proof must be allowed
    # to refer to the immediately preceding trigger. This closes the old asymmetry
    # where confirmation could only succeed when the current candle itself was a trigger.
    causal_trigger = trigger or previous_trigger
    setup_gates: dict[str, str] = {}
    if "AUCTION_ACCEPTANCE" in setup:
        acceptance_event = "ACCEPTANCE" in auction["event"]
        acceptance_proof = acceptance_event and event_direction_ok and (auction["terminal"] or response_present)
        setup_gates["auction_acceptance"] = rec("setup.auction_acceptance", "PASS" if acceptance_proof else "PENDING", {"event": auction["event"], "terminal": auction["terminal"], "response": response_present}, "acceptance event + directional response/terminal state", "Acceptance must be evidenced, not inferred from a touch.")
    elif "LIQUIDITY_REVERSAL" in setup:
        sweep = any(x in auction["event"] for x in ("SWEEP", "FAILED_BREAK_RECLAIM", "REJECTION"))
        reclaim = bool(causal_trigger and event_direction_ok)
        setup_gates["liquidity_sweep"] = rec("setup.liquidity_sweep", "PASS" if sweep else "PENDING", sweep, "sweep/rejection/failed-break event", "A reversal requires evidence that liquidity was actually taken.")
        setup_gates["reclaim_response"] = rec("setup.reclaim_response", "PASS" if reclaim else "PENDING", reclaim, "closed-candle reclaim in thesis direction", "Reclaim must be tied to a valid trigger/follow-through sequence.")
    elif "BREAKOUT_RETEST" in setup:
        bos = _text(e3o.get("bos", e3o.get("break_of_structure"))) in {"BREAK", "BOS", "YES", "CONFIRMED"} or "BREAK" in auction["event"]
        retest = "RETEST" in auction["event"]
        setup_gates["break_event"] = rec("setup.break_event", "PASS" if bos else "PENDING", bos, "confirmed break", "Retest reasoning is invalid without a causal break.")
        setup_gates["retest_response"] = rec("setup.retest_response", "PASS" if (retest and causal_trigger) else "PENDING", {"retest": retest, "causal_trigger": causal_trigger}, "retest + directional closed-candle response", "The retest must hold/reject and continue.")
    elif "BREAKOUT" in setup:
        bos = _text(e3o.get("bos", e3o.get("break_of_structure"))) in {"BREAK", "BOS", "YES", "CONFIRMED"} or "BREAK" in auction["event"]
        setup_gates["break_event"] = rec("setup.break_event", "PASS" if bos else "PENDING", bos, "confirmed break", "A breakout requires a causal closed-candle break.")
        setup_gates["expansion"] = rec("setup.expansion", "PASS" if (causal_trigger and (displacement or previous_displacement)) else "PENDING", {"causal_trigger": causal_trigger, "displacement": displacement, "previous_displacement": previous_displacement}, "directional displacement", "Expansion demonstrates participation after the break.")
    elif "TREND_PULLBACK" in setup:
        pullback = "PULLBACK" in _text(thesis) or "PULLBACK" in setup
        setup_gates["pullback_context"] = rec("setup.pullback_context", "PASS" if pullback else "PENDING", pullback, "pullback context", "Continuation requires a genuine pullback context.")
        setup_gates["continuation_close"] = rec("setup.continuation_close", "PASS" if (causal_trigger and structure_aligned) else "PENDING", {"causal_trigger": causal_trigger, "structure_aligned": structure_aligned}, "closed-candle continuation", "Continuation must agree with direction and structure.")
    elif "IMPULSE_CONTINUATION" in setup:
        setup_gates["impulse"] = rec("setup.impulse", "PASS" if ((displacement or previous_displacement) and (directional or previous_directional)) else "PENDING", {"displacement": displacement, "previous_displacement": previous_displacement, "directional": directional, "previous_directional": previous_directional}, "directional impulse", "An impulse must be demonstrated on a closed candle.")
        setup_gates["continuation_close"] = rec("setup.continuation_close", "PASS" if causal_trigger else "PENDING", causal_trigger, "closed-candle continuation trigger", "Continuation must be tied to a valid causal trigger.")
    else:
        setup_gates["generic_setup_proof"] = rec("setup.generic_setup_proof", "PASS" if causal_trigger else "PENDING", causal_trigger, "explicit closed-candle setup proof", "Unknown setup families require explicit proof and remain conservative.")

    current_follow = bool(previous_trigger and directional and close_ok and not invalid)
    if trigger:
        follow_state = "PENDING_NEXT_CLOSED_CANDLE"
        rec("follow_through", "PENDING", "TRIGGER_ON_LATEST_CLOSED_CANDLE", "subsequent closed candle", "The next candle does not exist yet; future evidence cannot be borrowed.")
        next_event = "NEXT_CLOSED_CANDLE_THESIS_FOLLOW_THROUGH"
    elif current_follow:
        follow_state = "PROVEN_ON_CURRENT_CLOSED_CANDLE"
        rec("follow_through", "PASS", {"previous_trigger": True, "bars_after_trigger": 1}, "current candle follows previous trigger", "The current closed candle causally validates the immediately preceding trigger.")
        next_event = "MONITOR_CONFIRMED_THESIS_INVALIDATION"
    else:
        follow_state = "NOT_PROVEN"
        rec("follow_through", "PENDING", "NOT_OBSERVED", "closed-candle follow-through", "Follow-through must be observed after a setup-specific trigger.")
        next_event = "VALID_CLOSED_CANDLE_TRIGGER"

    if structure_conflict:
        counter.append("STRUCTURE_COUNTER_EVIDENCE")
    if auction["pending"] and not auction["terminal"]:
        counter.append("AUCTION_PENDING")
    if space_available and space < MIN_STRUCTURAL_SPACE_ATR:
        counter.append("STRUCTURAL_SPACE_CONSTRAINED")
    if buy and current["bearish"]:
        counter.append("BEARISH_CLOSED_CANDLE_COUNTER_EVIDENCE")
    if not buy and current["bullish"]:
        counter.append("BULLISH_CLOSED_CANDLE_COUNTER_EVIDENCE")
    counter = _dedupe(counter)

    invalidated = bool(invalid)
    all_setup_pass = bool(setup_gates) and all(v == "PASS" for v in setup_gates.values())
    hard_structure_conflict = structure_conflict
    follow_proven = current_follow
    auction_setup = "AUCTION_ACCEPTANCE" in setup or "LIQUIDITY_REVERSAL" in setup
    terminal_auction_proof = bool(auction_setup and auction["terminal"] and event_direction_ok and event_fresh and event_present and response_present)

    # Confirmation paths are deliberately explicit:
    # A) current candle is a valid trigger and setup-specific proof is complete,
    #    then terminal auction proof may confirm immediately when the setup family supports it.
    # B) previous candle was the valid trigger and the current closed candle follows through,
    #    with setup-specific proof still complete. This is the normal causal confirmation path.
    causal_confirmation = bool(
        not invalidated
        and all_setup_pass
        and not hard_structure_conflict
        and follow_proven
    )
    terminal_confirmation = bool(
        not invalidated
        and all_setup_pass
        and not hard_structure_conflict
        and terminal_auction_proof
        and trigger
    )
    confirmation_allowed = causal_confirmation or terminal_confirmation

    if invalidated:
        state = "INVALIDATED"; confirmation = "INVALIDATED"; trigger_status = "INVALIDATED"; score = 0.0
        next_event = "E6_NEW_SETUP_AFTER_INVALIDATION"
        missing.append("new valid setup thesis")
    elif confirmation_allowed:
        state = "CONFIRMED"; confirmation = "CONFIRMED"; trigger_status = "CONFIRMED"; score = 92.0
        next_event = "MONITOR_CONFIRMED_THESIS_INVALIDATION"
    else:
        state = "WAIT"; confirmation = "DEVELOPING"; trigger_status = "TRIGGER_OBSERVED" if trigger else "NOT_CONFIRMED"
        pass_count = sum(v == "PASS" for v in ledger.values() if isinstance(v, dict))
        score = min(79.0, 40.0 + 4.0 * pass_count)
        if trigger:
            next_event = "NEXT_CLOSED_CANDLE_THESIS_FOLLOW_THROUGH"
        elif current_follow:
            next_event = "SETUP_PROOF_AND_CONFIRMATION_RECHECK"

    proof = dict(setup_gates)
    proof.update({
        "trigger": "PASS" if trigger else "FAIL",
        "prior_trigger": "PASS" if previous_trigger else "PENDING",
        "structure_alignment": "PASS" if structure_aligned else "FAIL",
        "structural_space": "PASS" if space_ok else "PENDING" if space_available else "UNAVAILABLE",
        "auction_terminal": "PASS" if terminal_auction_proof else "PENDING",
        "follow_through": "PASS" if follow_proven else "PENDING",
        "invalidation": "FAIL" if invalidated else "PASS",
    })
    proof_pass = sum(v == "PASS" for v in proof.values()); proof_total = max(1, len(proof))

    observed = _dedupe(observed + [
        f"setup={setup}", f"direction={direction}", f"maturity={e6_maturity}",
        f"trigger={trigger}", f"previous_trigger={previous_trigger}",
        f"follow_through={follow_state}", f"auction_event={auction['event'] or 'NONE'}",
        f"auction_state={auction['state'] or 'NONE'}", f"auction_age_bars={auction['age']}",
        f"current_body_atr={current['body_atr']:.4f}", f"current_close_position={current['close_position']:.4f}",
        f"proof_pass_ratio={proof_pass}/{proof_total}", f"terminal_auction_proof={terminal_auction_proof}",
        f"causal_confirmation={causal_confirmation}", f"terminal_confirmation={terminal_confirmation}",
    ])
    missing = _dedupe(missing); support = _dedupe(support); invalid = _dedupe(invalid); next_required = _dedupe(missing)
    lifecycle = {
        "state": state, "trigger": "OBSERVED" if trigger else "NOT_OBSERVED", "confirmation": confirmation,
        "follow_through": follow_state, "invalidation": invalid or "NONE", "next_required_event": next_event,
        "setup": setup, "direction": direction, "event_age_bars": auction["age"],
        "maturity": e6_maturity, "terminal_auction_proof": terminal_auction_proof,
        "causal_confirmation": causal_confirmation, "terminal_confirmation": terminal_confirmation,
    }
    conclusion = "Closed-candle evidence confirms the setup." if confirmation == "CONFIRMED" else "Closed-candle evidence invalidates the current setup thesis." if confirmation == "INVALIDATED" else "The thesis remains a hypothesis; required proof is incomplete."
    reasons: list[str] = []
    if confirmation == "CONFIRMED": reasons.append("CONFIRMATION_PROVEN")
    elif confirmation == "INVALIDATED": reasons.append("CONFIRMATION_INVALIDATED")
    else: reasons.append("PROOF_GATES_INCOMPLETE")
    reasons.append("CAUSAL_FOLLOW_THROUGH_PROVEN" if causal_confirmation else "TRIGGER_OBSERVED_NOT_AUTOMATIC_CONFIRMATION" if trigger else "VALID_CLOSED_CANDLE_TRIGGER_MISSING")
    if missing: reasons.append("MISSING_EVIDENCE_EXPOSED")
    if counter: reasons.append("COUNTER_EVIDENCE_PRESENT")
    if terminal_auction_proof: reasons.append("TERMINAL_AUCTION_PROOF_PRESENT")
    reasons += ["CLOSED_CANDLE_ONLY", "SETUP_SPECIFIC_PROOF_EVALUATED", "FOLLOW_THROUGH_EVALUATED", "INVALIDATION_EVALUATED", "CONFIRMATION_LIFECYCLE_EXPOSED", "EVIDENCE_LEDGER_EVALUATED", "OBSERVED_EVIDENCE_EXPOSED", "NEXT_REQUIRED_EVENT_EXPOSED", "TRIGGER_SEPARATED_FROM_CONFIRMATION", "PROFESSIONAL_REASONING_EXPOSED", "E7_DID_NOT_CREATE_THESIS"]

    out = {
        **_base(snapshot), "state": state, "confirmation": confirmation, "trigger_status": trigger_status,
        "direction": direction, "setup": setup, "setup_family": setup, "candidate_setup_thesis": thesis,
        "maturity": e6_maturity, "trigger_observed": trigger,
        "confirmation_strength": "HIGH" if confirmation == "CONFIRMED" else "NONE" if confirmation == "INVALIDATED" else "DEVELOPING",
        "confirmation_score": round(score, 2), "supporting_evidence": support, "counter_evidence": counter,
        "observed_evidence": observed, "missing_evidence": missing, "next_required_evidence": next_required,
        "next_required_event": next_event, "invalidation": invalid or ["closed-candle structural break or setup-specific contradiction"],
        "proof_gates": proof, "evidence_ledger": ledger, "confirmation_lifecycle": lifecycle,
        "trigger": {"observed": trigger, "direction": direction, "closed_candle": True, "body_atr": round(current["body_atr"], 4), "close_position": round(current["close_position"], 4), "is_confirmation": False},
        "follow_through": {"state": follow_state, "required": "subsequent closed-candle evidence", "previous_trigger": previous_trigger},
        "reasoning_trace": {"conclusion": conclusion, "why_not_confirmed": missing, "observed": observed, "counter_evidence": counter, "next_required_event": next_event, "setup_specific_proof": setup_gates},
        "observations": observed, "reason_codes": _dedupe(reasons),
    }
    out["professional_reasoning"] = _reasoning(conclusion=conclusion, thesis=thesis, observed=observed, missing=missing, support=support, counter=counter, invalidation=out["invalidation"], lifecycle=lifecycle, next_event=next_event, ledger=ledger, proof=proof)
    return EngineResult("E7", NAME, confirmation == "CONFIRMED", score, out, tuple(_dedupe(reasons)))
