"""E1 V14 professional market-state arbitration core."""
from __future__ import annotations
from math import isfinite
from statistics import mean
from typing import Any

QUESTION = "What is the market doing right now?"
MIN_BARS = 60
WING = 2
DIRECTIONS = {"UP", "DOWN"}
ARBITRATION_ORDER = ["DATA_QUALITY", "STRUCTURE", "LONG_HORIZON", "PERSISTENCE", "PRESSURE", "EMA_CONTEXT", "VOLATILITY", "COUNTER_EVIDENCE", "TRANSITION"]


def _num(x: Any):
    try: x = float(x)
    except (TypeError, ValueError): return None
    return x if isfinite(x) else None


def _clean(bars):
    good, bad = [], 0
    for raw in bars or []:
        if not isinstance(raw, dict): bad += 1; continue
        v = {k: _num(raw.get(k)) for k in ("open", "high", "low", "close")}
        if any(x is None for x in v.values()): bad += 1; continue
        o, h, l, c = v["open"], v["high"], v["low"], v["close"]
        if h < l or h < max(o, c) or l > min(o, c): bad += 1; continue
        good.append({**raw, **v})
    return good, bad


def _ema(xs, n):
    if not xs: return []
    a, cur, out = 2 / (n + 1), xs[0], [xs[0]]
    for x in xs[1:]: cur = a * x + (1 - a) * cur; out.append(cur)
    return out


def _atr(bars, n=14):
    trs, prev = [], None
    for b in bars[-n:]:
        h, l, c = b["high"], b["low"], b["close"]
        trs.append(h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev))); prev = c
    return mean(trs) if trs else 0.0


def _slope(xs, atr, n): return 0.0 if atr <= 0 or len(xs) <= n else (xs[-1] - xs[-1-n]) / atr


def _eff(xs, n):
    s = xs[-n:]
    if len(s) < 2: return 0.0
    path = sum(abs(s[i] - s[i-1]) for i in range(1, len(s)))
    return abs(s[-1] - s[0]) / max(path, 1e-12)


def _structure(bars, atr):
    hs, ls = [], []
    for i in range(WING, len(bars) - WING):
        w = bars[i-WING:i+WING+1]; h, l = bars[i]["high"], bars[i]["low"]
        if h >= max(x["high"] for x in w): hs.append(h)
        if l <= min(x["low"] for x in w): ls.append(l)
    hs, ls = hs[-8:], ls[-8:]
    hh = sum(hs[i] > hs[i-1] for i in range(1, len(hs))); lh = sum(hs[i] < hs[i-1] for i in range(1, len(hs)))
    hl = sum(ls[i] > ls[i-1] for i in range(1, len(ls))); ll = sum(ls[i] < ls[i-1] for i in range(1, len(ls)))
    bull, bear = min(hh, hl), min(lh, ll)
    if bull >= 2 and bull > bear: state, q = "BULLISH", min(1.0, .62 + .07 * bull)
    elif bear >= 2 and bear > bull: state, q = "BEARISH", min(1.0, .62 + .07 * bear)
    elif hh + hl >= 2 and hh + hl > lh + ll: state, q = "BULLISH", .52
    elif lh + ll >= 2 and lh + ll > hh + hl: state, q = "BEARISH", .52
    else: state, q = "MIXED", .30
    last = bars[-1]["close"]; hi = max(hs, default=last); lo = min(ls, default=last); buf = max(.10 * atr, 1e-12)
    bos = "UP" if last > hi + buf else "DOWN" if last < lo - buf else "NONE"
    return {"state": state, "quality": q, "bos": bos, "counts": {"HH":hh,"HL":hl,"LH":lh,"LL":ll}}


def _dir(state): return "UP" if state == "BULLISH" else "DOWN" if state == "BEARISH" else "NEUTRAL"


def _incomplete(reason, valid, invalid):
    return {
        "question": QUESTION, "reasoning_role": "MARKET_STATE_ANALYST", "trade_decision_authority": False, "decision_authority": "E9_ONLY",
        "architecture": "E1_SINGLE_PROFESSIONAL_BRAIN_V14", "market_state": "UNCLEAR", "trend_state": "NONE", "volatility_state": "UNKNOWN",
        "structure_state": "UNCLEAR", "structure_quality": 0.0, "structure_alignment": "UNRESOLVED", "directional_pressure": "NEUTRAL", "current_pressure": "NEUTRAL",
        "counter_pressure": "NONE", "dominant_direction": "NEUTRAL", "directional_state": "UNRESOLVED", "market_phase": "UNRESOLVED",
        "transition": "UNRESOLVED", "transition_status": "UNRESOLVED", "transition_confirmed": False, "transition_committed": False,
        "structural_persistence": False, "confidence": 0.0, "observations": [f"valid_candles={valid}", f"invalid_candles={invalid}"],
        "evidence": [f"valid_candles={valid}", f"invalid_candles={invalid}"], "reasons": [reason], "reason_codes": [reason], "conflicts": ["DATA_QUALITY_ANOMALIES"] if invalid else [],
        "counter_evidence": {"direction":"NEUTRAL","strength":0.0,"items":[]}, "transition_commitment": {"required":True,"confirmed":False,"missing":["RELIABLE_MARKET_DATA"]},
        "professional_reasoning": {"task":"DESCRIBE_MARKET_STATE_ONLY","arbitration_order":ARBITRATION_ORDER,"trade_boundary":"MARKET_STATE_ONLY","primary_thesis":{"direction":"NEUTRAL","status":"UNRESOLVED","supporting_evidence":[],"counter_evidence":[]},"confidence_model":{"support":0.0,"counter_evidence":0.0,"structure":0.0,"persistence":0.0,"stability":0.0},"invalidation":{"conditions":[reason]}},
        "e1_contract_version":"PROFESSIONAL_MARKET_STATE_V14", "e1_engine_version":"PROFESSIONAL_MARKET_STATE_V14", "e1_trade_authority":False, "analysis_status":"INCOMPLETE"
    }


def analyze_e1_professional_v14(bars):
    good, bad = _clean(bars)
    if len(good) < MIN_BARS: return _incomplete("INSUFFICIENT_RELIABLE_CLOSED_CANDLES", len(good), bad)
    if bad: return _incomplete("DATA_QUALITY_ANOMALIES_PRESENT_CLASSIFICATION_WITHHELD", len(good), bad)
    closes = [b["close"] for b in good]; atr = _atr(good); atr50 = _atr(good, 50)
    if atr <= 0 or atr50 <= 0: return _incomplete("ATR_INVALID", len(good), bad)

    e20, e50 = _ema(closes,20), _ema(closes,50); ema = "UP" if e20[-1] > e50[-1] else "DOWN" if e20[-1] < e50[-1] else "NEUTRAL"; ema_gap = (e20[-1]-e50[-1])/atr
    ns, ts = (5,10,20,40), (.15,.20,.30,.40); slopes = [_slope(closes,atr,n) for n in ns]
    states = ["UP" if s >= t else "DOWN" if s <= -t else "FLAT" for s,t in zip(slopes,ts)]; up, down = states.count("UP"), states.count("DOWN")
    pressure = "UP" if up > down else "DOWN" if down > up else "NEUTRAL"; consensus = max(up,down)/4
    long_states = states[1:]; lu, ld = long_states.count("UP"), long_states.count("DOWN"); long_dir = "UP" if lu > ld else "DOWN" if ld > lu else "NEUTRAL"; long_cons = max(lu,ld)/3
    if pressure == "UP": persistence = sum(s >= t for s,t in zip(slopes,(.20,.25,.35,.45)))/4; long_persist = sum(s >= t for s,t in zip(slopes[1:],(.25,.35,.45)))/3
    elif pressure == "DOWN": persistence = sum(s <= -t for s,t in zip(slopes,(.20,.25,.35,.45)))/4; long_persist = sum(s <= -t for s,t in zip(slopes[1:],(.25,.35,.45)))/3
    else: persistence = long_persist = 0.0

    st = _structure(good,atr); sd = _dir(st["state"]); s80 = _dir(_structure(good[-80:],_atr(good[-80:]))["state"]); s40 = _dir(_structure(good[-40:],_atr(good[-40:]))["state"])
    structural_persist = sd in DIRECTIONS and sd == s80 == s40; structural_candidate = sd in DIRECTIONS and st["quality"] >= .52
    persistent_long = long_dir in DIRECTIONS and long_cons >= 2/3 and long_persist >= 2/3
    if structural_candidate and persistent_long and sd == long_dir: dominant, basis = sd, "STRUCTURE_LONG_HORIZON_PERSISTENCE"
    elif persistent_long and ema == long_dir and abs(ema_gap) >= .50: dominant, basis = long_dir, "LONG_HORIZON_EMA_ALIGNMENT"
    elif structural_candidate and sd == ema and abs(ema_gap) >= .50 and long_dir in {"NEUTRAL",sd}: dominant, basis = sd, "STRUCTURE_EMA_ALIGNMENT"
    elif structural_candidate and persistent_long: dominant, basis = sd, "STRUCTURE_WITH_LONG_HORIZON_SUPPORT"
    else: dominant, basis = "NEUTRAL", "NO_DOMINANT_REGIME"

    align = "ALIGNED" if dominant in DIRECTIONS and sd == dominant else "COUNTER_TREND" if dominant in DIRECTIONS and sd in DIRECTIONS else "MIXED" if sd == "MIXED" else "UNRESOLVED"
    counter_dir = "DOWN" if dominant == "UP" else "UP" if dominant == "DOWN" else "NEUTRAL"; recent_delta = closes[-1]-closes[-6]; recent = "UP" if recent_delta >= .15*atr else "DOWN" if recent_delta <= -.15*atr else "NEUTRAL"
    context_flip = abs(_slope(closes,atr,30)) >= .45 and abs(_slope(closes,atr,8)) >= .65 and (_slope(closes,atr,30) > 0) != (_slope(closes,atr,8) > 0)
    items = []
    if counter_dir in DIRECTIONS:
        if sd == counter_dir: items.append("COUNTER_TREND_STRUCTURE_PRESENT")
        if pressure == counter_dir: items.append("SHORT_HORIZON_COUNTER_PRESSURE")
        if recent == counter_dir: items.append("RECENT_COUNTER_PRESSURE")
        if context_flip: items.append("CONTEXT_FLIP_REQUIRES_PERSISTENT_REPRICING")
    if not items: items = ["NO_MATERIAL_COUNTER_EVIDENCE"]
    counter_strength = min(1.0,.35*float(sd==counter_dir)+.25*float(pressure==counter_dir)+.20*float(recent==counter_dir)+.20*float(context_flip)) if counter_dir in DIRECTIONS else 0.0

    checks = {
        "STRUCTURAL_REPRICING": structural_candidate and sd == counter_dir and structural_persist,
        "LONG_HORIZON_REPRICING": long_dir == counter_dir and long_cons >= 2/3 and long_persist >= 2/3,
        "PRESSURE_REPRICING": pressure == counter_dir and recent == counter_dir,
        "EMA_REPRICING": ema == counter_dir and abs(ema_gap) >= .50,
        "BOS_REPRICING": st["bos"] == counter_dir,
        "CONTEXT_PERSISTENCE": context_flip,
    }
    transition_confirmed = dominant in DIRECTIONS and all(checks.values()); missing = [k for k,v in checks.items() if not v]
    if transition_confirmed: state, transition, phase = "TRANSITION", "CONFIRMED", "TRANSITION"
    elif dominant in DIRECTIONS: state, transition, phase = ("TREND_UP" if dominant=="UP" else "TREND_DOWN"), ("WATCH" if items != ["NO_MATERIAL_COUNTER_EVIDENCE"] else "ABSENT"), ("PULLBACK" if recent not in {dominant,"NEUTRAL"} else "IMPULSE" if recent==dominant else "CONSOLIDATION")
    elif abs(slopes[2]) < .65 and _eff(closes,20) < .35 and _eff(closes,40) < .40: state, transition, phase = "RANGE", "ABSENT", "RANGE"
    else: state, transition, phase = "UNCLEAR", "WATCH", "TRANSITION_WATCH"
    volatility = "EXPANDING" if atr/atr50 > 1.20 else "CONTRACTING" if atr/atr50 < .78 else "NORMAL"
    support = min(1.0,.45*long_cons+.30*long_persist+.25*st["quality"]) if dominant in DIRECTIONS else 0.0; stability = min(1.0,.50*persistence+.50*float(structural_persist)); confidence = min(1.0,.55*support+.25*stability+.20*(1-counter_strength)) if dominant in DIRECTIONS else 0.0
    counter_pressure = "PULLBACK_WITHIN_TREND" if dominant in DIRECTIONS and recent == counter_dir and sd == dominant else counter_dir if items != ["NO_MATERIAL_COUNTER_EVIDENCE"] else "NONE"
    reasons = (["COUNTER_TREND_STRUCTURE_CANNOT_AUTO_FLIP_STATE"] if align=="COUNTER_TREND" else []) + (["SINGLE_COUNTER_MOVE_CANNOT_COMMIT_TRANSITION"] if dominant in DIRECTIONS and recent == counter_dir and not transition_confirmed else []) + [f"DOMINANT_BASIS={basis}","DATA_INTEGRITY_VALIDATED","EMA_AS_CONTEXT_NOT_AUTHORITY"] + (["LONG_HORIZON_PERSISTENCE_CONFIRMED"] if persistent_long else []) + (["VOLATILITY_COMPRESSION_DETECTED"] if volatility=="CONTRACTING" else []) + (["PERSISTENT_STRUCTURAL_REPRICING_CONFIRMED"] if transition_confirmed else ["TRANSITION_REQUIRES_PERSISTENT_REPRICING"])
    obs = [f"valid_candles={len(good)}",f"invalid_candles={bad}",f"ema20_vs_ema50={ema}",f"ema_gap_atr={ema_gap:.3f}"] + [f"price_slope_{n}_atr={s:.3f}" for n,s in zip(ns,slopes)] + [f"multi_horizon={','.join(states)}",f"directional_consensus={consensus:.3f}",f"long_horizon_direction={long_dir}",f"long_horizon_consensus={long_cons:.3f}",f"long_horizon_persistence={long_persist:.3f}"]
    thesis_dir = dominant if dominant in DIRECTIONS else pressure if pressure in DIRECTIONS else "NEUTRAL"
    invalidation = ["PERSISTENT_DOWN_STRUCTURAL_REPRICING","LONG_HORIZON_DOWN_PERSISTENCE"] if dominant=="UP" else ["PERSISTENT_UP_STRUCTURAL_REPRICING","LONG_HORIZON_UP_PERSISTENCE"] if dominant=="DOWN" else ["ESTABLISH_RELIABLE_DOMINANT_DIRECTION"]
    return {
        "question":QUESTION,"reasoning_role":"MARKET_STATE_ANALYST","trade_decision_authority":False,"decision_authority":"E9_ONLY","architecture":"E1_SINGLE_PROFESSIONAL_BRAIN_V14",
        "market_state":state,"trend_state":dominant if dominant in DIRECTIONS else "NONE","volatility_state":volatility,"structure_state":st["state"],"structure_quality":st["quality"],"structure_alignment":align,
        "directional_pressure":pressure,"current_pressure":recent,"counter_pressure":counter_pressure,"dominant_direction":dominant,"directional_state":state,"market_phase":phase,
        "transition":transition,"transition_status":transition,"transition_confirmed":transition_confirmed,"transition_committed":transition_confirmed,"structural_persistence":structural_persist,"confidence":confidence,"evidence_strength":confidence,
        "observations":obs,"evidence":obs,"reasons":reasons,"reason_codes":reasons,"conflicts":items if items != ["NO_MATERIAL_COUNTER_EVIDENCE"] else [],
        "counter_evidence":{"direction":counter_dir,"strength":counter_strength,"items":items},"transition_commitment":{"required":dominant in DIRECTIONS,"confirmed":transition_confirmed,"missing":missing},
        "professional_reasoning":{"task":"DESCRIBE_MARKET_STATE_ONLY","arbitration_order":ARBITRATION_ORDER,"trade_boundary":"MARKET_STATE_ONLY","primary_thesis":{"direction":thesis_dir,"status":"ESTABLISHED" if dominant in DIRECTIONS else "UNRESOLVED","supporting_evidence":[basis,f"STRUCTURE={st['state']}"],"counter_evidence":items},"confidence_model":{"support":support,"counter_evidence":counter_strength,"structure":st["quality"],"persistence":long_persist,"stability":stability},"invalidation":{"conditions":invalidation},"transition_commitment":checks},
        "e1_contract_version":"PROFESSIONAL_MARKET_STATE_V14","e1_engine_version":"PROFESSIONAL_MARKET_STATE_V14","e1_trade_authority":False,"analysis_status":"COMPLETE"
    }

__all__ = ["analyze_e1_professional_v14"]
