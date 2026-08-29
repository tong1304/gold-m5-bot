from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Confirmation / Trigger Brain"
QUESTION = "Does the setup have a valid closed-candle confirmation, or what is still missing?"
ARCHITECTURE = "E7_PROFESSIONAL_SETUP_AWARE_CONFIRMATION_BRAIN_V3"
VERSION = "3.0"
ATR_PERIOD = 14
MIN_BARS = 5
FOLLOW_THROUGH_MAX_AGE = 3


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _dedupe(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(v) for v in values if v))


def _direction(value: Any) -> str:
    t = _text(value)
    if t in {"BUY", "BULLISH", "UP", "LONG", "BUYERS"}: return "BUY"
    if t in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS"}: return "SELL"
    return "NEUTRAL"


def _atr(bars: list[dict[str, Any]], period: int = ATR_PERIOD) -> float:
    if len(bars) < 2: return 0.0
    trs = []
    for i in range(max(1, len(bars) - period), len(bars)):
        h, l = _num(bars[i].get("high")), _num(bars[i].get("low"))
        pc = _num(bars[i - 1].get("close"))
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return mean(trs) if trs else 0.0


def _candle(bar: dict[str, Any], previous: dict[str, Any], atr: float) -> dict[str, Any]:
    o, h, l, c = (_num(bar.get(k)) for k in ("open", "high", "low", "close"))
    po, ph, pl, pc = (_num(previous.get(k)) for k in ("open", "high", "low", "close"))
    rng = max(h - l, 1e-9); body = abs(c - o); a = max(atr, 1e-9)
    pos = max(0.0, min(1.0, (c - l) / rng))
    return {"open":o,"high":h,"low":l,"close":c,"prev_open":po,"prev_high":ph,"prev_low":pl,"prev_close":pc,
            "range":rng,"body":body,"body_atr":body/a,"close_position":pos,
            "bullish":c>o,"bearish":c<o,"bullish_engulf":o<=pc and c>=po and c>o,
            "bearish_engulf":o>=pc and c<=po and c<o,
            "bullish_displacement":c>o and body/a>=0.55 and pos>=0.65,
            "bearish_displacement":c<o and body/a>=0.55 and pos<=0.35}


def _e4(e4: dict[str, Any]) -> dict[str, Any]:
    event = _text(e4.get("event", e4.get("finding"))); state = _text(e4.get("auction_state", e4.get("state")))
    direction = _direction(e4.get("direction")); level = _num(e4.get("event_level"))
    age = max(0, int(_num(e4.get("event_age_bars"))))
    if direction == "NEUTRAL":
        if any(x in event for x in ("HIGH_FAILED_BREAK_RECLAIM","HIGH_SWEEP_REJECTION")): direction="SELL"
        elif any(x in event for x in ("LOW_FAILED_BREAK_RECLAIM","LOW_SWEEP_REJECTION")): direction="BUY"
        elif any(x in event for x in ("HIGH_ACCEPTANCE","HIGH_BREAK")): direction="BUY"
        elif any(x in event for x in ("LOW_ACCEPTANCE","LOW_BREAK")): direction="SELL"
    terminal = state in {"CONFIRMED","TERMINALLY_CONFIRMED","ACCEPTED","REJECTED"} or "TERMINAL" in state
    return {"event":event,"state":state,"direction":direction,"level":level,"age":age,"terminal":terminal,
            "pending":state=="PENDING" or "PENDING" in event,"event_id":str(e4.get("event_id") or e4.get("event_candle_id") or ""),
            "quality":_num(e4.get("auction_quality"))}


def _base(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {"architecture":ARCHITECTURE,"version":VERSION,"question":QUESTION,"role":"CONFIRMATION_ANALYST",
            "reasoning_role":"CONFIRMATION_ANALYST","decision_authority":"E9","trade_decision_authority":False,
            "closed_candle_only":True,"lookahead":False,"bar_count":len(snapshot.get("bars") or [])}


def _empty(snapshot: dict[str, Any], reason: str) -> EngineResult:
    out={**_base(snapshot),"state":"WAIT","confirmation":"UNRESOLVED","trigger_status":"NOT_EVALUATED","direction":"NEUTRAL","setup":"NONE",
         "trigger_observed":False,"confirmation_strength":"NONE","confirmation_score":0.0,"supporting_evidence":[],"counter_evidence":[reason],
         "missing_evidence":["valid setup thesis","valid closed-candle confirmation"],"next_required_evidence":["a valid closed candle proving the setup thesis"],
         "invalidation":["new closed candle invalidates or replaces the current thesis"],"proof_gates":{},"evidence_ledger":{},
         "reasoning_trace":{"conclusion":"Confirmation cannot be evaluated from current context."}}
    return EngineResult("E7",NAME,False,0.0,out,("INSUFFICIENT_CONTEXT",))


def analyze_e7(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    bars=list(snapshot.get("bars") or []); e6=upstream.get("E6")
    if len(bars)<MIN_BARS or not e6: return _empty(snapshot,"MISSING_SETUP_CONTEXT")
    e6o=dict(e6.output or {}); e4o=dict((upstream.get("E4").output if upstream.get("E4") else {}) or {})
    e3o=dict((upstream.get("E3").output if upstream.get("E3") else {}) or {}); e5o=dict((upstream.get("E5").output if upstream.get("E5") else {}) or {})
    direction=_direction(e6o.get("direction",e6o.get("direction_thesis"))); setup=_text(e6o.get("setup",e6o.get("setup_family"))) or "NONE"
    thesis=str(e6o.get("candidate_setup_thesis") or e6o.get("thesis") or ""); atr=max(_atr(bars),1e-9)
    c=_candle(bars[-1],bars[-2],atr); p=_candle(bars[-2],bars[-3],atr); auction=_e4(e4o)
    if direction not in {"BUY","SELL"}:
        out={**_base(snapshot),"state":"UNRESOLVED","confirmation":"UNRESOLVED","trigger_status":"NOT_EVALUATED","direction":"NEUTRAL","setup":setup,
             "candidate_setup_thesis":thesis,"trigger_observed":False,"confirmation_strength":"NONE","confirmation_score":20.0,
             "supporting_evidence":[],"counter_evidence":["SETUP_DIRECTION_UNRESOLVED"],"missing_evidence":["directional setup thesis"],
             "next_required_evidence":["E6 must expose a resolved BUY/SELL thesis"],"invalidation":["new closed candle changes the setup thesis"],
             "proof_gates":{"direction_resolved":"FAIL"},"evidence_ledger":{"direction_resolved":{"state":"FAIL","observed":direction,"required":"BUY or SELL"}},
             "reasoning_trace":{"conclusion":"No directional thesis can be confirmed."}}
        return EngineResult("E7",NAME,False,20.0,out,("SETUP_DIRECTION_UNRESOLVED",))

    buy=direction=="BUY"; support=[]; counter=[]; missing=[]; invalid=[]; ledger={}; proof={}
    def rec(name: str,state: str,observed: Any=None,required: Any=None,why: str=""):
        state=_text(state) if _text(state) in {"PASS","FAIL","PENDING","UNAVAILABLE"} else "UNAVAILABLE"
        ledger[name]={"state":state,"observed":observed,"required":required,"interpretation":why}
        if state=="PASS": support.append(name.upper())
        elif state=="FAIL": counter.append(name.upper())
        else: missing.append(name)
    def gate(name: str,state: str,missing_name: str):
        state=_text(state) if _text(state) in {"PASS","FAIL","PENDING","UNAVAILABLE"} else "UNAVAILABLE"; proof[name]=state; rec("setup."+name,state,state,"PASS")
        if state in {"PENDING","UNAVAILABLE"}: missing.append(missing_name)

    directional=bool(c["bullish"] if buy else c["bearish"]); close_ok=bool(c["close_position"]>=0.65 if buy else c["close_position"]<=0.35)
    displacement=bool(c["bullish_displacement"] if buy else c["bearish_displacement"]); engulf=bool(c["bullish_engulf"] if buy else c["bearish_engulf"])
    trigger=directional and close_ok and (displacement or engulf)
    rec("directional_closed_candle","PASS" if directional else "FAIL",directional,True)
    rec("close_location","PASS" if close_ok else "FAIL",round(float(c["close_position"]),4),">=0.65 BUY / <=0.35 SELL")
    rec("meaningful_directional_displacement","PASS" if displacement else "PENDING",round(float(c["body_atr"]),4),">=0.55 ATR")
    if engulf: rec("engulfing_response","PASS",True,True)
    else: rec("engulfing_response","UNAVAILABLE",False,True)

    internal=_direction(e3o.get("internal_state",e3o.get("internal_count_state"))); external=_direction(e3o.get("external_state",e3o.get("external_count_state")))
    finding=_text(e3o.get("finding",e3o.get("structure_state")))
    rec("internal_structure","PASS" if internal==direction else "FAIL" if internal!="NEUTRAL" else "UNAVAILABLE",internal,direction)
    rec("external_structure","PASS" if external==direction else "FAIL" if external!="NEUTRAL" else "UNAVAILABLE",external,direction)
    if "MIXED" in finding or "TRANSITION" in finding: counter.append("STRUCTURE_NOT_RESOLVED")
    space=_num(e5o.get("available_space_atr_long" if buy else "available_space_atr_short"))
    rec("structural_space","PASS" if space>=0.75 else "FAIL" if space>0 else "UNAVAILABLE",round(space,4),">=0.75 ATR")

    family=setup.replace(" ","_")
    if "LIQUIDITY_REVERSAL" in family:
        event_ok=bool(auction["event"] and any(x in auction["event"] for x in ("SWEEP_REJECTION","FAILED_BREAK_RECLAIM")))
        gate("liquidity_event","PASS" if event_ok else "FAIL","liquidity_sweep_or_failed_break_reclaim")
        gate("liquidity_response","PASS" if auction["direction"]==direction else "FAIL" if auction["direction"] in {"BUY","SELL"} else "PENDING","liquidity_response_aligned_with_thesis")
        gate("auction_terminality","PASS" if auction["terminal"] else "PENDING" if auction["pending"] else "FAIL","terminal_auction_confirmation")
        if auction["level"]:
            reclaimed=c["close"]>auction["level"] if buy else c["close"]<auction["level"]
            gate("level_reclaim","PASS" if reclaimed else "FAIL","closed_candle_reclaim_of_liquidity_level")
        else: gate("level_reclaim","UNAVAILABLE","liquidity_level")
    elif "BREAKOUT_RETEST" in family or "BREAKOUT" in family:
        bos=_text(e3o.get("bos",e3o.get("break_of_structure"))) in {"BREAK","BOS","YES"}
        gate("structure_break","PASS" if bos else "FAIL","confirmed_structure_break"); gate("break_acceptance_close","PASS" if close_ok else "FAIL","closed_candle_acceptance_beyond_level")
        gate("breakout_displacement","PASS" if displacement else "PENDING","breakout_displacement")
        if "BREAKOUT_RETEST" in family: gate("retest_continuation","PASS" if displacement and directional else "PENDING","continuation_after_retest")
    elif "TREND_PULLBACK" in family:
        trend=_direction(e3o.get("trend_state",e3o.get("direction")))
        gate("trend_alignment","PASS" if trend==direction else "FAIL" if trend!="NEUTRAL" else "PENDING","trend_direction_alignment")
        gate("pullback_response","PASS" if directional else "FAIL","pullback_rejection_and_continuation"); gate("continuation_displacement","PASS" if displacement else "PENDING","continuation_displacement")
    elif "AUCTION_ACCEPTANCE_CONTINUATION" in family:
        gate("terminal_auction_acceptance","PASS" if auction["terminal"] else "PENDING" if auction["pending"] else "FAIL","terminal_auction_acceptance")
        gate("directional_acceptance_close","PASS" if close_ok else "FAIL","directional_acceptance_close"); gate("continuation_displacement","PASS" if displacement else "PENDING","continuation_displacement")
    else:
        gate("setup_definition","FAIL","setup_specific_confirmation_definition"); counter.append("UNKNOWN_SETUP_CONFIRMATION_RULE")

    prev_trigger=bool(p["bullish"] if buy else p["bearish"]) and bool(p["close_position"]>=0.65 if buy else p["close_position"]<=0.35) and bool(p["bullish_displacement"] if buy else p["bearish_displacement"] or p["bullish_engulf"] if buy else p["bearish_engulf"])
    if prev_trigger: follow="PASS" if directional and close_ok else "FAIL"
    elif trigger: follow="PENDING"
    else: follow="NOT_ESTABLISHED"
    rec("follow_through",follow,{"previous_trigger":prev_trigger,"current_directional_close":directional},"next closed candle continues thesis")
    if auction["event"]:
        fresh=auction["age"]<=FOLLOW_THROUGH_MAX_AGE; rec("liquidity_event_freshness","PASS" if fresh else "FAIL",auction["age"],f"<= {FOLLOW_THROUGH_MAX_AGE} bars")
        if not fresh: invalid.append("LIQUIDITY_EVENT_STALE")

    if (buy and c["bearish"] and c["close_position"]<=0.35) or ((not buy) and c["bullish"] and c["close_position"]>=0.65): invalid.append("DIRECT_CLOSED_CANDLE_THESIS_REJECTION")
    if auction["direction"] in {"BUY","SELL"} and auction["direction"]!=direction: invalid.append("AUCTION_RESPONSE_REVERSES_SETUP_DIRECTION")
    invalidated=bool(invalid)
    setup_specific=bool(proof) and all(v=="PASS" for v in proof.values())
    confirmed=bool(trigger and setup_specific and follow=="PASS" and not invalidated)

    sc=25.0+min(35.0,len(_dedupe(support))*4.0)-min(25.0,len(_dedupe(counter))*5.0)-min(20.0,len(_dedupe(missing))*2.0)
    if trigger: sc+=12
    if setup_specific: sc+=8
    if follow=="PASS": sc+=15
    if invalidated: sc-=25
    score=max(0.0,min(100.0,sc))
    if invalidated: state,status,strength="INVALIDATED","CONFLICTED","NONE"
    elif confirmed: state,status,strength="CONFIRMED","CONFIRMED","STRONG" if score>=80 else "MODERATE"
    elif trigger or prev_trigger or any(v=="PENDING" for v in proof.values()): state,status,strength="DEVELOPING","TRIGGER_OBSERVED_NOT_PROVEN","MODERATE" if score>=60 else "WEAK"
    else: state,status,strength="UNRESOLVED","NOT_CONFIRMED","NONE"

    required=_dedupe(missing)
    if confirmed: next_required=[]
    elif follow=="PENDING": next_required=["next closed candle must continue the thesis with directional acceptance"]
    elif follow=="FAIL": next_required=["a new valid setup trigger after the failed confirmation"]
    else: next_required=required[:] or ["closed-candle evidence completing the setup-specific proof gates"]
    reasons=["SETUP_SPECIFIC_CONFIRMATION_PROVEN"] if confirmed else _dedupe((["TRIGGER_OBSERVED_NOT_CONFIRMATION"] if trigger else [])+["PROOF_GATES_INCOMPLETE"] if required else (["CONFIRMATION_INVALIDATED"] if invalidated else ["CONFIRMATION_NOT_PROVEN"]))
    gates={"direction_resolved":"PASS","directional_closed_candle":ledger["directional_closed_candle"]["state"],"close_location":ledger["close_location"]["state"],
           "displacement_or_engulfing":"PASS" if displacement or engulf else "FAIL","setup_specific_proof":"PASS" if setup_specific else "PENDING" if any(v=="PENDING" for v in proof.values()) else "FAIL",
           "follow_through":follow,"counter_evidence_clear":"PASS" if not invalidated else "FAIL"}
    trace={"thesis":thesis,"setup_family":family,"direction":direction,"lifecycle":"TRIGGER" if trigger and follow=="PENDING" else "FOLLOW_THROUGH" if follow=="PASS" else "FAILED" if follow=="FAIL" else state,
           "trigger_observed":trigger,"trigger_definition":"directional closed candle + close location + displacement/engulfing","follow_through_state":follow,
           "setup_proof":proof,"evidence_ledger":ledger,"counter_evidence_applied":_dedupe(counter),"missing_proof":required,"next_required_evidence":next_required,
           "invalidation":_dedupe(invalid),"confirmation_boundary":"E7 proves evidence for the E6 thesis; E9 alone decides whether a trade is permitted."}
    out={**_base(snapshot),"state":state,"confirmation":state,"trigger_status":status,"direction":direction,"setup":setup,"setup_family":family,"candidate_setup_thesis":thesis,
         "trigger_observed":trigger,"trigger_type":"BULLISH_DISPLACEMENT" if buy and displacement else "BEARISH_DISPLACEMENT" if not buy and displacement else "BULLISH_ENGULFING" if buy and engulf else "BEARISH_ENGULFING" if not buy and engulf else "NONE",
         "confirmation_strength":strength,"confirmation_score":round(score,2),"candle_body":round(float(c["body"]),8),"candle_range":round(float(c["range"]),8),"body_atr":round(float(c["body_atr"]),4),"close_position":round(float(c["close_position"]),4),
         "follow_through":follow=="PASS","follow_through_state":follow,"displacement":displacement,"auction_context":auction,
         "supporting_evidence":_dedupe(support),"counter_evidence":_dedupe(counter),"missing_evidence":required,"next_required_evidence":next_required,
         "invalidation":_dedupe(invalid+["new closed candle materially invalidates the confirmation"]),"proof_gates":gates,"setup_proof":proof,"evidence_ledger":ledger,"reasoning_trace":trace,
         "professional_reasoning":{"conclusion":state,"why_trigger_is_or_is_not_present":trigger,"why_confirmation_is_or_is_not_proven":confirmed,"what_is_missing":required,"what_can_invalidate":_dedupe(invalid),
         "next_required_event":next_required,"evidence_hierarchy":"direct setup proof > closed-candle trigger > structure corroboration > soft context","decision_boundary":"E7 is evidence/confirmation only; E9 retains trade decision authority."}}
    return EngineResult("E7",NAME,confirmed,round(score,2),out,tuple(_dedupe(reasons+counter+required)))
