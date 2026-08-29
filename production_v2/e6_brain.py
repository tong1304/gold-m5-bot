from __future__ import annotations

from statistics import mean
from typing import Any
from .contracts import EngineResult

NAME = "Setup Brain"
QUESTION = "What setup is forming, in what direction, and at what stage?"
ARCHITECTURE = "E6_PROFESSIONAL_SETUP_FORMATION_BRAIN_V19"
VERSION = "19.0"
MIN_BARS = 60
ATR_PERIOD = 14
MIN_SPACE_ATR = 0.75
SETUP_FAMILIES = ("LIQUIDITY_REVERSAL", "AUCTION_ACCEPTANCE_CONTINUATION", "BREAKOUT_RETEST", "TREND_PULLBACK", "BREAKOUT", "IMPULSE_CONTINUATION")


def _payload(u: dict[str, EngineResult], n: str) -> dict[str, Any]:
    r = u.get(n)
    return r.output if r else {}


def _text(v: Any) -> str:
    return str(v or "").upper().strip()


def _norm(v: Any) -> str:
    t = _text(v)
    if t in {"UP", "BULLISH", "BUY", "BUYERS", "LONG", "TREND_UP"}:
        return "BUY"
    if t in {"DOWN", "BEARISH", "SELL", "SELLERS", "SHORT", "TREND_DOWN"}:
        return "SELL"
    return "NEUTRAL"


def _num(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _atr(b: list[dict[str, Any]]) -> float:
    if len(b) < 2:
        return 0.0
    s = b[-(ATR_PERIOD + 1):]
    trs = []
    for i, x in enumerate(s):
        h = _num(x.get("high"))
        l = _num(x.get("low"))
        p = _num(s[i - 1].get("close")) if i else 0.0
        trs.append(max(0.0, h - l) if i == 0 else max(h - l, abs(h - p), abs(l - p)))
    return mean(trs[-ATR_PERIOD:]) if trs else 0.0


def _auction_direction(e: str) -> str:
    if "HIGH_SWEEP_REJECTION" in e or "HIGH_FAILED_BREAK_RECLAIM" in e:
        return "SELL"
    if "LOW_SWEEP_REJECTION" in e or "LOW_FAILED_BREAK_RECLAIM" in e:
        return "BUY"
    if "HIGH_ACCEPTANCE" in e or "HIGH_BREAK" in e:
        return "BUY"
    if "LOW_ACCEPTANCE" in e or "LOW_BREAK" in e:
        return "SELL"
    return "NEUTRAL"


def _auction(e: dict[str, Any]):
    st = _text(e.get("auction_state", e.get("state")))
    ev = _text(e.get("event", e.get("finding")))
    term = st in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "REJECTED"} or "TERMINAL" in st
    pending = st == "PENDING" or "PENDING" in ev
    return ev, term, pending, max(0, int(_num(e.get("event_age_bars"), 0)))


def _dirs(e1: dict[str, Any], e2: dict[str, Any], e3: dict[str, Any], e4: dict[str, Any]):
    vals = {
        "E1_PRESSURE": _norm(e1.get("directional_pressure", e1.get("pressure"))),
        "E3_EXTERNAL": _norm(e3.get("external_state", e3.get("external_count_state"))),
        "E4_AUCTION": _auction_direction(_text(e4.get("event", e4.get("finding")))),
    }
    votes = [v for v in vals.values() if v != "NEUTRAL"]
    uniq = set(votes)
    sup = [f"{k}={v}" for k, v in vals.items() if v != "NEUTRAL"]
    ctr: list[str] = []
    if len(uniq) > 1:
        d, src = "NEUTRAL", "INDEPENDENT_EVIDENCE_CONFLICT"
        ctr.append("DIRECTIONAL_EVIDENCE_CONFLICT")
    elif len(uniq) == 1:
        d, src = next(iter(uniq)), "E1_E3_E4_CONVERGENCE" if len(votes) >= 2 else "INDEPENDENT_EVIDENCE"
    else:
        d, src = "NEUTRAL", "INSUFFICIENT_CONVERGENCE"

    e2d = [x for x in (_norm(e2.get("direction")), _norm(e2.get("opportunity_direction"))) if x != "NEUTRAL"]
    ef = _text(e2.get("finding", e2.get("state")))
    if e2d and len(set(e2d)) == 1 and not any(x in ef for x in ("UNRESOLVED", "UNPROVEN")):
        if d == "NEUTRAL":
            d, src = e2d[0], "E2_CORROBORATION_ONLY"
        sup.append(f"E2_DIRECTION={e2d[0]}")
        if d != e2d[0]:
            ctr.append("E2_DIRECTION_DISAGREEMENT")
    if len(e2d) > 1:
        ctr.append("E2_INTERNAL_DIRECTION_CONFLICT")

    ef3 = _text(e3.get("finding", e3.get("structure_state")))
    ei = _text(e3.get("internal_state", e3.get("internal_count_state")))
    if "MIXED" in ef3 or "MIXED" in ei:
        ctr.append("STRUCTURE_MIXED")
    return d, list(dict.fromkeys(sup + [f"DIRECTION_SOURCE={src}"])), list(dict.fromkeys(ctr)), src


def _out(state, setup, direction, stage, maturity, thesis, q, conf, exists, ready, sup, ctr, missing, nextreq, inv, cands, rejected, trace):
    ctr = list(dict.fromkeys(ctr))
    missing = list(dict.fromkeys(missing))
    nextreq = list(dict.fromkeys(nextreq))
    q = max(0.0, min(100.0, q))
    conf = max(0.0, min(100.0, conf))
    reasons = list(dict.fromkeys(ctr + ([] if stage == "MATURE" else ["SETUP_NOT_MATURE"])))
    obs = [
        f"candidate_setups={','.join(x['name'] for x in cands) if cands else 'NONE'}",
        f"selected_setup={setup}",
        f"selected_direction={direction}",
        f"selected_stage={stage}",
        f"setup_exists={exists}",
        f"trade_ready={ready}",
        f"supporting_evidence={','.join(sup) if sup else 'NONE'}",
        f"counter_evidence={','.join(ctr) if ctr else 'NONE'}",
        f"missing_evidence={','.join(missing) if missing else 'NONE'}",
        f"next_required_evidence={','.join(nextreq) if nextreq else 'NONE'}",
        f"lifecycle={stage}",
        f"maturity={maturity}",
    ]
    o = {
        "architecture": ARCHITECTURE,
        "version": VERSION,
        "question": QUESTION,
        "role": "SETUP_ANALYST",
        "reasoning_role": "SETUP_FORMATION_REASONER",
        "decision_authority": "E9",
        "trade_decision_authority": False,
        "state": state,
        "setup_state": state,
        "finding": state,
        "setup": setup,
        "setup_family": setup,
        "direction": direction,
        "stage": stage,
        "formation_stage": stage,
        "lifecycle": stage,
        "maturity": maturity,
        "thesis": thesis,
        "setup_exists": exists,
        "trade_ready": ready,
        "trade_readiness": "READY" if ready else "NOT_READY",
        "setup_quality": round(q, 2),
        "confidence": round(conf, 2),
        "candidate_setups": [x["name"] for x in cands],
        "candidate_states": cands,
        "rejected_setups": rejected,
        "supporting_evidence": sup,
        "counter_evidence": ctr,
        "missing_evidence": missing,
        "next_required_evidence": nextreq,
        "invalidation": list(dict.fromkeys(inv)),
        "observations": obs,
        "reasoning_trace": trace,
    }
    return EngineResult("E6", NAME, False, q, o, tuple(reasons))


def analyze_e6(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    bars = list(snapshot.get("bars") or [])
    if len(bars) < MIN_BARS:
        return _out(
            "NO_SETUP", "NONE", "NEUTRAL", "SEARCHING", "UNRESOLVED",
            "Insufficient closed-candle history", 0, 100, False, False, [],
            [f"CLOSED_CANDLES_BELOW_MINIMUM={MIN_BARS}"],
            ["sufficient_closed_candle_data"],
            [f"wait for at least {MIN_BARS} valid closed candles"],
            ["history remains insufficient"], [], [],
            {"decision": "NO_SETUP", "cause": "INSUFFICIENT_HISTORY"},
        )

    try:
        atr = _atr(bars)
        if atr <= 0:
            raise ValueError
        for b in bars[-MIN_BARS:]:
            for k in ("open", "high", "low", "close"):
                v = float(b[k])
                if v != v:
                    raise ValueError
    except (KeyError, TypeError, ValueError):
        return _out(
            "NO_SETUP", "NONE", "NEUTRAL", "SEARCHING", "UNRESOLVED",
            "Invalid closed-candle market data", 0, 100, False, False, [],
            ["INVALID_MARKET_DATA"], ["valid_closed_candle_ohlc"],
            ["provide valid closed-candle OHLC values"], ["invalid market data"],
            [], [], {"decision": "NO_SETUP", "cause": "INVALID_DATA"},
        )

    e1, e2, e3, e4, e5 = (_payload(upstream, n) for n in ("E1", "E2", "E3", "E4", "E5"))
    direction, sup, ctr, src = _dirs(e1, e2, e3, e4)
    event, terminal, pending, age = _auction(e4)
    ad = _auction_direction(event)
    opp = _text(e2.get("finding", e2.get("state", "")))
    ef3 = _text(e3.get("finding", e3.get("structure_state")))
    ei = _text(e3.get("internal_state", e3.get("internal_count_state")))
    mixed = "MIXED" in ef3 or "MIXED" in ei
    space = _num(e5.get("available_space_atr_long")) if direction == "BUY" else _num(e5.get("available_space_atr_short"))
    value_response = _text(e5.get("value_response", e5.get("repricing_state")))
    cands: list[dict[str, Any]] = []
    rejected: list[str] = []

    hard = direction == "NEUTRAL" or "DIRECTIONAL_EVIDENCE_CONFLICT" in ctr

    if not hard:
        # A pending acceptance event is a real formation hypothesis, not a trade
        # confirmation. E6 must preserve it while explicitly carrying the missing
        # follow-through evidence to E7/E9.
        if ad == direction and "ACCEPTANCE" in event:
            acceptance_ok = (
                (direction == "BUY" and any(x in value_response for x in ("ACCEPTED_ABOVE_VALUE", "ACCEPTANCE_ABOVE_VALUE", "EQUILIBRIUM")))
                or (direction == "SELL" and any(x in value_response for x in ("ACCEPTED_BELOW_VALUE", "ACCEPTANCE_BELOW_VALUE", "EQUILIBRIUM")))
            )
            if acceptance_ok or direction == _norm(e1.get("pressure")):
                cands.append({
                    "name": "AUCTION_ACCEPTANCE_CONTINUATION",
                    "direction": direction,
                    "formation_stage": "VALIDATING" if not terminal else "MATURE",
                    "strength": min(100, 56 + (12 if terminal else 0) + (8 if acceptance_ok else 0) - (8 if mixed else 0)),
                    "evidence": [
                        f"E4_EVENT={event}",
                        f"E4_AUCTION_STATE={'TERMINAL' if terminal else 'PENDING'}",
                        f"E5_VALUE_RESPONSE={value_response or 'UNKNOWN'}",
                        f"E1_PRESSURE={_norm(e1.get('pressure'))}",
                    ],
                    "missing": [] if terminal else ["closed_candle_follow_through", "terminal_auction_confirmation"],
                    "invalidation": ["acceptance_failure", "reclaim_through_accepted_level"],
                })

        if ad == direction and any(x in event for x in ("SWEEP_REJECTION", "FAILED_BREAK_RECLAIM")):
            cands.append({
                "name": "LIQUIDITY_REVERSAL",
                "direction": direction,
                "formation_stage": "MATURE" if terminal else "VALIDATING",
                "strength": min(100, 58 + (12 if _norm(e4.get("response_actor")) == direction else 0) + (10 if terminal else 0) - (8 if mixed else 0)),
                "evidence": [f"E4_EVENT={event}", f"E4_RESPONSE={_norm(e4.get('response_actor'))}", f"EVENT_AGE_BARS={age}"],
                "missing": [] if terminal else ["terminal_auction_confirmation"],
                "invalidation": ["auction_response_failure", "loss_of_structural_invalidation_level"],
            })

        trend = _norm(e1.get("trend_state", e1.get("finding")))
        bos = _text(e3.get("bos", e3.get("break_of_structure", "")))
        seq = _text(e3.get("sequence", ""))
        if direction == trend and not mixed:
            if "BREAK" in bos:
                cands.append({
                    "name": "BREAKOUT_RETEST" if "RETEST" in _text(e3) else "BREAKOUT",
                    "direction": direction,
                    "formation_stage": "MATURE" if terminal else "VALIDATING",
                    "strength": 62 if terminal else 48,
                    "evidence": ["DIRECTIONAL_TREND_ALIGNMENT", f"STRUCTURE_EVENT={bos}"],
                    "missing": [] if terminal else ["closed_candle_follow_through", "acceptance_after_break"],
                    "invalidation": ["breakout_failure", "reclaim_inside_prior_structure"],
                })
            elif "HL" in seq or "LH" in seq:
                cands.append({
                    "name": "TREND_PULLBACK",
                    "direction": direction,
                    "formation_stage": "FORMING",
                    "strength": 42,
                    "evidence": ["TREND_DIRECTION_ALIGNED", f"STRUCTURE_SEQUENCE={seq}"],
                    "missing": ["impulse_then_pullback_sequence", "continuation_trigger"],
                    "invalidation": ["loss_of_protected_structure"],
                })

    sup += [
        f"E4_EVENT={event or 'NONE'}",
        f"E4_EVENT_AGE_BARS={age}",
        f"E4_AUCTION_TERMINAL={terminal}",
        f"E4_AUCTION_PENDING={pending}",
        f"E3_FINDING={ef3 or 'UNKNOWN'}",
        f"E5_SELECTED_SPACE_ATR={space:.3f}",
        f"E5_VALUE_RESPONSE={value_response or 'UNKNOWN'}",
    ]
    sup = list(dict.fromkeys(sup))

    if pending and not terminal:
        ctr.append("LIQUIDITY_EVENT_PENDING")
    if any(x in opp for x in ("UNRESOLVED", "UNPROVEN")):
        ctr.append("OPPORTUNITY_MATURITY_UNPROVEN")
    if mixed:
        ctr.append("STRUCTURE_MIXED")
    if direction != "NEUTRAL" and space < MIN_SPACE_ATR:
        ctr.append("STRUCTURAL_SPACE_CONSTRAINED")
    ctr = list(dict.fromkeys(ctr))

    if not cands:
        setup = "NONE"
        stage = "FORMING"
        exists = False
        thesis = "No defensible setup hypothesis: evidence is insufficient or direction is conflicted."
        missing = ["directional_convergence", "causal_setup_sequence"]
        nextreq = ["closed-candle evidence resolving direction and establishing a causal setup sequence"]
        q = 20
        conf = 82
    else:
        cands.sort(key=lambda x: x["strength"], reverse=True)
        best = cands[0]
        setup = best["name"]
        stage = best["formation_stage"]
        exists = True
        missing = list(best["missing"])
        if space < MIN_SPACE_ATR:
            missing.append("adequate_structural_space")
        if pending and not terminal and "terminal_auction_confirmation" not in missing:
            missing.append("terminal_auction_confirmation")
        if any(x in opp for x in ("UNRESOLVED", "UNPROVEN")):
            missing.append("opportunity_acceptance_follow_through")
        missing = list(dict.fromkeys(missing))
        nextreq = [f"evidence required to advance {setup}: {x}" for x in missing]
        q = best["strength"]
        conf = min(95, 58 + 7 * len(best["evidence"]) - 5 * len(missing))
        thesis = f"{direction} {setup} is {stage.lower()}: formation is diagnosable, while maturity remains conditional on the missing evidence."
        if len(cands) > 1 and cands[0]["strength"] - cands[1]["strength"] < 8:
            setup = "AMBIGUOUS"
            stage = "FORMING"
            rejected = [x["name"] for x in cands]
            ctr.append("HYPOTHESES_TOO_CLOSE_TO_FORCE_SELECTION")
            thesis = "Multiple setup hypotheses are too close to justify false precision; wait for discriminating evidence."

    maturity = "MATURE" if stage == "MATURE" else ("VALIDATING" if stage == "VALIDATING" else "FORMING")
    ready = (
        exists
        and setup != "AMBIGUOUS"
        and stage == "MATURE"
        and direction != "NEUTRAL"
        and space >= MIN_SPACE_ATR
        and not pending
        and not any(x in opp for x in ("UNRESOLVED", "UNPROVEN"))
    )
    inv = [x for c in cands for x in c.get("invalidation", [])][:6]
    trace = {
        "direction_source": src,
        "auction": {"event": event, "direction": ad, "terminal": terminal, "pending": pending, "age_bars": age},
        "location": {"selected_space_atr": space, "minimum_space_atr": MIN_SPACE_ATR, "value_response": value_response},
        "hypothesis_count": len(cands),
        "hard_direction_veto": hard,
        "selection": "causal evidence -> counter evidence -> maturity -> discriminating evidence",
        "professional_rule": "diagnose formation before declaring absence; preserve conditional hypotheses; do not convert pending evidence into trade confirmation; E9 retains trade authority",
    }
    return _out(stage, setup, direction, stage, maturity, thesis, q, conf, exists, ready, sup, ctr, missing, nextreq, inv, cands, rejected, trace)
