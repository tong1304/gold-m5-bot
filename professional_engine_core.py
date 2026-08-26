from __future__ import annotations

"""Native Production-V2 Professional Decision Engine.

E1-E8 are evidence specialists. E9 alone authorizes BUY/SELL.
Gate semantics are explicit: PASS, CONDITIONAL, BLOCK, FAIL.
Analysis may continue after a blocked specialist so E9 receives the full evidence ledger.
This module is independent from v11 and legacy signal engines.
"""
import math, os
from typing import Any
import pandas as pd

ENGINE_VERSION = "PROFESSIONAL-DECISION-9E-v2.1"
MIN_RR = max(float(os.getenv("PROFESSIONAL_MIN_RR", "2.0")), 1.5)


def _f(x, default=0.0):
    try:
        v = float(x)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def _atr(df, n=14):
    h, l, c = [pd.to_numeric(df[k], errors="coerce") for k in ("high", "low", "close")]
    pc = c.shift(1)
    tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=3).mean()


def _ema(df, n):
    return pd.to_numeric(df.close, errors="coerce").ewm(span=n, adjust=False).mean()


def _result(engine, gate, quality=0, reason_codes=None, **values):
    return {
        "engine": engine,
        "gate": gate,
        "analysis_status": "COMPLETE",
        "quality": quality,
        "reason_codes": reason_codes or [],
        **values,
    }


def e1_market_state(m5):
    if len(m5) < 80:
        return _result("E1", "FAIL", reason_codes=["INSUFFICIENT_DATA"], analysis_status="INCOMPLETE", state="UNKNOWN")
    atr = _atr(m5); a = _f(atr.iloc[-1]); base = _f(atr.tail(40).median(), a)
    e20, e50 = _ema(m5, 20), _ema(m5, 50); c = _f(m5.close.iloc[-1])
    trend = "UP" if c > e20.iloc[-1] > e50.iloc[-1] else "DOWN" if c < e20.iloc[-1] < e50.iloc[-1] else "NEUTRAL"
    compression = a < base * .75 if base else False
    expansion = a > base * 1.25 if base else False
    state = "COMPRESSION" if compression else "EXPANSION" if expansion else "TREND_UP" if trend == "UP" else "TREND_DOWN" if trend == "DOWN" else "RANGE"
    q = 90 if trend != "NEUTRAL" else 70
    return _result("E1", "PASS", q, state=state, trend_state=trend, atr=a, atr_baseline=base, compression=compression, expansion=expansion)


def e2_regime(e1, m5):
    if e1.get("gate") not in ("PASS", "CONDITIONAL"):
        return _result("E2", "FAIL", reason_codes=["E1_NOT_VALID"], regime="UNKNOWN", playbook="NONE")
    s = e1.get("state")
    play = {"TREND_UP":"TREND_CONTINUATION", "TREND_DOWN":"TREND_CONTINUATION", "COMPRESSION":"BREAKOUT_WATCH", "EXPANSION":"EXPANSION_CONTINUATION", "RANGE":"RANGE_REJECTION"}.get(s, "WAIT")
    if play == "WAIT":
        return _result("E2", "BLOCK", 40, ["REGIME_UNCLEAR"], regime=s or "UNKNOWN", playbook="NONE")
    return _result("E2", "PASS", e1.get("quality", 0), regime=s, playbook=play)


def e3_structure(m5):
    if len(m5) < 60:
        return _result("E3", "FAIL", reason_codes=["INSUFFICIENT_DATA"], structure="UNKNOWN")
    x = m5.iloc[:-1].tail(30); hi = _f(x.high.max()); lo = _f(x.low.min()); c = _f(m5.close.iloc[-1])
    prev = m5.iloc[:-5].tail(25); phi = _f(prev.high.max()); plo = _f(prev.low.min())
    bos = "BULLISH" if c > phi else "BEARISH" if c < plo else "NONE"
    ema20 = _f(_ema(m5, 20).iloc[-1])
    structure = "BULLISH" if c > hi*.999 and c > ema20 else "BEARISH" if c < lo*1.001 and c < ema20 else "NEUTRAL"
    return _result("E3", "PASS", 80 if bos != "NONE" else 65, structure=structure, bos=bos, external_high=hi, external_low=lo)


def e4_liquidity(m5, e3):
    if e3.get("gate") not in ("PASS", "CONDITIONAL"):
        return _result("E4", "FAIL", reason_codes=["E3_NOT_VALID"], liquidity_state="UNKNOWN")
    x = m5.iloc[:-1].tail(20); hi = _f(x.high.max()); lo = _f(x.low.min()); r = m5.iloc[-1]
    h, l, c = _f(r.high), _f(r.low), _f(r.close)
    sweep = "BUY_SIDE_SWEEP" if h > hi and c < hi else "SELL_SIDE_SWEEP" if l < lo and c > lo else "NONE"
    acceptance = "ABOVE" if c > hi else "BELOW" if c < lo else "INSIDE"
    return _result("E4", "PASS", 88 if sweep != "NONE" else 62, liquidity_state="SWEEP" if sweep != "NONE" else "NO_EVENT", sweep=sweep, zone_high=hi, zone_low=lo, acceptance=acceptance)


def e5_location(m5, e3, e4):
    if e3.get("gate") not in ("PASS", "CONDITIONAL"):
        return _result("E5", "FAIL", reason_codes=["E3_NOT_VALID"], location="UNKNOWN")
    hi, lo, c = _f(e3.get("external_high")), _f(e3.get("external_low")), _f(m5.close.iloc[-1])
    w = max(hi-lo, 1e-9); p = (c-lo)/w
    loc = "DISCOUNT" if p < .35 else "PREMIUM" if p > .65 else "EQUILIBRIUM"
    direction = "BUY" if e3.get("structure") == "BULLISH" else "SELL" if e3.get("structure") == "BEARISH" else "NONE"
    advantage = (direction == "BUY" and loc == "DISCOUNT") or (direction == "SELL" and loc == "PREMIUM")
    return _result("E5", "PASS", 88 if advantage else 50, location=loc, position_in_range=round(p,3), direction=direction, advantage=advantage)


def e6_setup(m5, e1, e2, e3, e4, e5):
    if e2.get("gate") not in ("PASS", "CONDITIONAL"):
        return _result("E6", "BLOCK", 0, ["REGIME_NOT_READY"], setup="NONE", direction=None)
    direction = "BUY" if e3.get("structure") == "BULLISH" else "SELL" if e3.get("structure") == "BEARISH" else None
    if not direction:
        return _result("E6", "BLOCK", 30, ["NO_DIRECTION"], setup="NONE", direction=None)
    candle = m5.iloc[-1]; body = abs(_f(candle.close)-_f(candle.open)); atr = max(_f(_atr(m5).iloc[-1]), 1e-9)
    impulse = body >= atr*.35
    liquidity_support = (direction == "BUY" and e4.get("sweep") == "SELL_SIDE_SWEEP") or (direction == "SELL" and e4.get("sweep") == "BUY_SIDE_SWEEP")
    setup = "LIQUIDITY_REVERSAL" if liquidity_support else "TREND_CONTINUATION" if e2.get("playbook") == "TREND_CONTINUATION" and impulse else "NONE"
    if setup == "NONE":
        return _result("E6", "BLOCK", 35, ["NO_VALID_SETUP"], setup=setup, direction=direction, impulse=impulse, liquidity_support=liquidity_support)
    q = 90 if e5.get("advantage") else 65
    return _result("E6", "PASS", q, setup=setup, direction=direction, impulse=impulse, liquidity_support=liquidity_support)


def e7_confirmation(m5, e6, e3, e4):
    d = e6.get("direction")
    if not d:
        return _result("E7", "BLOCK", 20, ["NO_SETUP_TO_CONFIRM"], confirmation="NONE", confirmed=False)
    r = m5.iloc[-1]; o,c,h,l = map(_f, (r.open,r.close,r.high,r.low)); body = abs(c-o); atr = max(_f(_atr(m5).iloc[-1]),1e-9)
    directional = (d == "BUY" and c > o) or (d == "SELL" and c < o); displacement = body >= atr*.30
    bos = (d == "BUY" and e3.get("bos") == "BULLISH") or (d == "SELL" and e3.get("bos") == "BEARISH")
    sweep = (d == "BUY" and e4.get("sweep") == "SELL_SIDE_SWEEP") or (d == "SELL" and e4.get("sweep") == "BUY_SIDE_SWEEP")
    confirmed = directional and displacement and (bos or sweep)
    return _result("E7", "PASS" if confirmed else "BLOCK", 92 if confirmed else 45, [] if confirmed else ["CONFIRMATION_INSUFFICIENT"], confirmation="CONFIRMED" if confirmed else "UNCONFIRMED", confirmed=confirmed, directional_candle=directional, displacement=displacement, bos_confirmation=bos, liquidity_confirmation=sweep)


def e8_risk(m5, e6, e7, e3):
    d = e6.get("direction")
    if not d:
        return _result("E8", "BLOCK", 0, ["NO_DIRECTION"], risk_valid=False)
    entry = _f(m5.close.iloc[-1]); atr = max(_f(_atr(m5).iloc[-1]), 1e-9)
    if d == "BUY": sl = min(_f(m5.low.tail(5).min()), _f(e3.get("external_low"))) - atr*.10; target = _f(e3.get("external_high"))
    else: sl = max(_f(m5.high.tail(5).max()), _f(e3.get("external_high"))) + atr*.10; target = _f(e3.get("external_low"))
    risk, reward = abs(entry-sl), abs(target-entry); rr = reward/risk if risk else 0
    valid = risk > 0 and reward > 0 and rr >= MIN_RR
    return _result("E8", "PASS" if valid else "BLOCK", 90 if valid else 30, [] if valid else ["INSUFFICIENT_RISK_DATA" if reward <= 0 or risk <= 0 else "RR_BELOW_MINIMUM"], risk_valid=valid, entry=entry, sl=sl, target=target, risk=risk, reward=reward, rr=rr, minimum_rr=MIN_RR)


def e9_decision(evidence, symbol):
    failures=[]
    for name, ok in (("E1", evidence["E1"].get("gate") == "PASS"), ("E2", evidence["E2"].get("gate") == "PASS"), ("E3", evidence["E3"].get("gate") == "PASS"), ("E4", evidence["E4"].get("gate") == "PASS"), ("E5", evidence["E5"].get("gate") == "PASS"), ("E6", evidence["E6"].get("gate") == "PASS"), ("E7", bool(evidence["E7"].get("confirmed"))), ("E8", bool(evidence["E8"].get("risk_valid")))):
        if not ok: failures.append(f"{name}:HARD_GATE")
    direction=evidence["E6"].get("direction")
    decision=direction if not failures and direction in ("BUY","SELL") else "NO_TRADE"
    qualities=[_f(evidence[n].get("quality")) for n in evidence]
    return {"engine":"E9","gate":"PASS" if decision in ("BUY","SELL") else "BLOCK","decision":decision,"execution_eligible":decision in ("BUY","SELL"),"hard_failures":failures,"evidence_alignment":round(sum(qualities)/len(qualities),1),"decision_reason":"E1-E8 evidence aligned" if not failures else ";".join(failures),"symbol":symbol}


def analyze(m5, m15=None, h1=None, symbol=None, index=None):
    if index is not None: m5=m5.iloc[:index+1].reset_index(drop=True)
    e1=e1_market_state(m5); e2=e2_regime(e1,m5); e3=e3_structure(m5); e4=e4_liquidity(m5,e3); e5=e5_location(m5,e3,e4); e6=e6_setup(m5,e1,e2,e3,e4,e5); e7=e7_confirmation(m5,e6,e3,e4); e8=e8_risk(m5,e6,e7,e3)
    evidence={"E1":e1,"E2":e2,"E3":e3,"E4":e4,"E5":e5,"E6":e6,"E7":e7,"E8":e8}; e9=e9_decision(evidence,symbol or "UNKNOWN")
    return {"engine_version":ENGINE_VERSION,"architecture":"E1→E2→E3→E4→E5→E6→E7→E8→E9","symbol":symbol,"signal":e9["decision"],"decision_authority":"E9","professional_decision":{"e1":e1,"e2":e2,"e3":e3,"e4":e4,"e5":e5,"e6":e6,"e7":e7,"e8":e8,"e9":e9},"evidence":evidence,"rejection_reasons":e9["hard_failures"],"trade_levels":{"valid":e8.get("risk_valid",False),"entry":e8.get("entry"),"sl":e8.get("sl"),"tp":e8.get("target"),"risk_reward":e8.get("rr"),"minimum_rr":MIN_RR},"live_orders_allowed":False}
