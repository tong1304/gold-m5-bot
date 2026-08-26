from __future__ import annotations

"""Production-V2 Evidence-Based Professional Decision Engine.

E1-E8 are independent sequential reasoning brains. They do NOT gate, block,
or authorize a trade. Each engine receives prior evidence, analyzes it using
its own question, and returns an evidence record. E9 is the only master
Decision Brain and decides BUY / SELL / NO_TRADE from the complete ledger.

This module intentionally has no dependency on v11 or legacy signal engines.
"""
import math
import os
from typing import Any
import pandas as pd

ENGINE_VERSION = "PROFESSIONAL-EVIDENCE-9E-v2.2"
MIN_RR = max(float(os.getenv("PROFESSIONAL_MIN_RR", "2.0")), 1.5)


def _f(x, default=0.0):
    try:
        v = float(x)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def _atr(df, n=14):
    h = pd.to_numeric(df["high"], errors="coerce")
    l = pd.to_numeric(df["low"], errors="coerce")
    c = pd.to_numeric(df["close"], errors="coerce")
    pc = c.shift(1)
    tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=3).mean()


def _ema(df, n):
    return pd.to_numeric(df.close, errors="coerce").ewm(span=n, adjust=False).mean()


def _evidence(engine, question, conclusion, confidence, observations=None, **values):
    return {
        "engine": engine,
        "question": question,
        "analysis_status": "COMPLETE",
        "conclusion": conclusion,
        "confidence": round(float(confidence), 1),
        "observations": observations or [],
        **values,
    }


def e1_market_state(m5):
    if len(m5) < 80:
        return _evidence("E1", "What market state is present?", "INSUFFICIENT_DATA", 0, ["Need at least 80 M5 candles"], analysis_status="INCOMPLETE", market_state="UNKNOWN")
    atr = _atr(m5); a = _f(atr.iloc[-1]); base = _f(atr.tail(40).median(), a)
    e20, e50 = _ema(m5, 20), _ema(m5, 50); c = _f(m5.close.iloc[-1])
    trend = "UP" if c > e20.iloc[-1] > e50.iloc[-1] else "DOWN" if c < e20.iloc[-1] < e50.iloc[-1] else "NEUTRAL"
    compression = a < base * .75 if base else False
    expansion = a > base * 1.25 if base else False
    state = "COMPRESSION" if compression else "EXPANSION" if expansion else "TREND_UP" if trend == "UP" else "TREND_DOWN" if trend == "DOWN" else "RANGE"
    return _evidence("E1", "What market state is present?", state, 90 if trend != "NEUTRAL" else 70, [f"Trend={trend}", f"ATR={a:.5g}", f"ATR baseline={base:.5g}"], market_state=state, trend_state=trend, atr=a, atr_baseline=base, compression=compression, expansion=expansion)


def e2_regime(e1, m5):
    s = e1.get("market_state", "UNKNOWN")
    play = {"TREND_UP":"TREND_CONTINUATION", "TREND_DOWN":"TREND_CONTINUATION", "COMPRESSION":"BREAKOUT_WATCH", "EXPANSION":"EXPANSION_CONTINUATION", "RANGE":"RANGE_REJECTION"}.get(s, "WAIT")
    confidence = e1.get("confidence", 0) if play != "WAIT" else 35
    conclusion = play if play != "WAIT" else "REGIME_UNCLEAR"
    return _evidence("E2", "Given E1, what regime/opportunity is the market offering?", conclusion, confidence, [f"E1 state={s}"], regime=s, playbook=play, opportunity=conclusion)


def e3_structure(m5, e1, e2):
    if len(m5) < 60:
        return _evidence("E3", "Does price structure support the current thesis?", "INSUFFICIENT_DATA", 0, ["Need at least 60 M5 candles"], structure="UNKNOWN", bos="NONE")
    x = m5.iloc[:-1].tail(30); hi = _f(x.high.max()); lo = _f(x.low.min()); c = _f(m5.close.iloc[-1])
    prev = m5.iloc[:-5].tail(25); phi = _f(prev.high.max()); plo = _f(prev.low.min())
    bos = "BULLISH" if c > phi else "BEARISH" if c < plo else "NONE"
    ema20 = _f(_ema(m5, 20).iloc[-1])
    structure = "BULLISH" if c > hi*.999 and c > ema20 else "BEARISH" if c < lo*1.001 and c < ema20 else "NEUTRAL"
    return _evidence("E3", "Does price structure support the current thesis?", structure, 88 if bos != "NONE" else 65, [f"BOS={bos}", f"E2 playbook={e2.get('playbook')}"], structure=structure, bos=bos, external_high=hi, external_low=lo)


def e4_liquidity(m5, e1, e2, e3):
    x = m5.iloc[:-1].tail(20); hi = _f(x.high.max()); lo = _f(x.low.min()); r = m5.iloc[-1]
    h, l, c = _f(r.high), _f(r.low), _f(r.close)
    sweep = "BUY_SIDE_SWEEP" if h > hi and c < hi else "SELL_SIDE_SWEEP" if l < lo and c > lo else "NONE"
    state = "SWEEP" if sweep != "NONE" else "NO_EVENT"
    return _evidence("E4", "What is liquidity doing around the thesis?", state, 88 if sweep != "NONE" else 62, [f"Sweep={sweep}", f"Structure={e3.get('structure')}"], liquidity_state=state, sweep=sweep, zone_high=hi, zone_low=lo, acceptance="ABOVE" if c > hi else "BELOW" if c < lo else "INSIDE")


def e5_location(m5, e1, e2, e3, e4):
    hi, lo, c = _f(e3.get("external_high")), _f(e3.get("external_low")), _f(m5.close.iloc[-1]); w=max(hi-lo,1e-9); p=(c-lo)/w
    loc="DISCOUNT" if p<.35 else "PREMIUM" if p>.65 else "EQUILIBRIUM"
    direction="BUY" if e3.get("structure")=="BULLISH" else "SELL" if e3.get("structure")=="BEARISH" else "NONE"
    advantage=(direction=="BUY" and loc=="DISCOUNT") or (direction=="SELL" and loc=="PREMIUM")
    return _evidence("E5", "Is current price located where risk is asymmetric?", "ADVANTAGE" if advantage else "NEUTRAL_OR_POOR", 88 if advantage else 50, [f"Location={loc}", f"Direction={direction}"], location=loc, position_in_range=round(p,3), direction=direction, advantage=advantage)


def e6_setup(m5, e1, e2, e3, e4, e5):
    direction="BUY" if e3.get("structure")=="BULLISH" else "SELL" if e3.get("structure")=="BEARISH" else None
    if not direction:
        return _evidence("E6", "Has the opportunity matured into an executable setup?", "NO_VALID_SETUP", 30, ["No directional structure"], setup="NONE", direction=None, setup_state="EARLY")
    candle=m5.iloc[-1]; body=abs(_f(candle.close)-_f(candle.open)); atr=max(_f(_atr(m5).iloc[-1]),1e-9); impulse=body>=atr*.35
    liquidity_support=(direction=="BUY" and e4.get("sweep")=="SELL_SIDE_SWEEP") or (direction=="SELL" and e4.get("sweep")=="BUY_SIDE_SWEEP")
    setup="LIQUIDITY_REVERSAL" if liquidity_support else "TREND_CONTINUATION" if e2.get("playbook")=="TREND_CONTINUATION" and impulse else "NONE"
    state="MATURE" if setup!="NONE" else "EARLY"
    return _evidence("E6", "Has the opportunity matured into an executable setup?", setup if setup!="NONE" else "NO_VALID_SETUP", 90 if setup!="NONE" and e5.get("advantage") else 65 if setup!="NONE" else 35, [f"Impulse={impulse}", f"Liquidity support={liquidity_support}", f"Location advantage={e5.get('advantage')}"], setup=setup, direction=direction, setup_state=state, impulse=impulse, liquidity_support=liquidity_support)


def e7_confirmation(m5, e1, e2, e3, e4, e5, e6):
    d=e6.get("direction")
    if not d:
        return _evidence("E7", "Has the market actually confirmed the setup thesis?", "NO_CONFIRMATION", 20, ["No directional setup"], confirmation="NONE", confirmed=False)
    r=m5.iloc[-1]; o,c,h,l=map(_f,(r.open,r.close,r.high,r.low)); body=abs(c-o); atr=max(_f(_atr(m5).iloc[-1]),1e-9)
    directional=(d=="BUY" and c>o) or (d=="SELL" and c<o); displacement=body>=atr*.30
    bos=(d=="BUY" and e3.get("bos")=="BULLISH") or (d=="SELL" and e3.get("bos")=="BEARISH")
    sweep=(d=="BUY" and e4.get("sweep")=="SELL_SIDE_SWEEP") or (d=="SELL" and e4.get("sweep")=="BUY_SIDE_SWEEP")
    confirmed=directional and displacement and (bos or sweep)
    return _evidence("E7", "Has the market actually confirmed the setup thesis?", "CONFIRMED" if confirmed else "UNCONFIRMED", 92 if confirmed else 45, [f"Directional candle={directional}", f"Displacement={displacement}", f"BOS={bos}", f"Liquidity confirmation={sweep}"], confirmation="CONFIRMED" if confirmed else "NONE", confirmed=confirmed, directional_candle=directional, displacement=displacement, bos_confirmation=bos, liquidity_confirmation=sweep)


def e8_risk(m5, e1, e2, e3, e4, e5, e6, e7):
    d=e6.get("direction")
    if not d:
        return _evidence("E8", "Does the setup offer sufficient asymmetric trade economics?", "NOT_READY", 0, ["No directional setup"], risk_assessment="NOT_READY", risk_valid=False)
    entry=_f(m5.close.iloc[-1]); atr=max(_f(_atr(m5).iloc[-1]),1e-9)
    if d=="BUY": sl=min(_f(m5.low.tail(5).min()),_f(e3.get("external_low")))-atr*.10; target=_f(e3.get("external_high"))
    else: sl=max(_f(m5.high.tail(5).max()),_f(e3.get("external_high")))+atr*.10; target=_f(e3.get("external_low"))
    risk,reward=abs(entry-sl),abs(target-entry); rr=reward/risk if risk else 0; valid=risk>0 and reward>0 and rr>=MIN_RR
    assessment="ATTRACTIVE" if valid else "POOR_OR_INSUFFICIENT"
    reason="RR_MEETS_REQUIREMENT" if valid else "RR_BELOW_MINIMUM" if reward>0 and risk>0 else "RISK_DATA_INCOMPLETE"
    return _evidence("E8", "Does the setup offer sufficient asymmetric trade economics?", assessment, 90 if valid else 30, [f"RR={rr:.2f}", f"Minimum RR={MIN_RR:.2f}", f"Confirmation={e7.get('confirmed')}"], risk_assessment=assessment, risk_valid=valid, reason=reason, entry=entry, sl=sl, target=target, risk=risk, reward=reward, rr=rr, minimum_rr=MIN_RR)


def e9_decision(evidence, symbol):
    """Master brain: synthesize evidence; no E1-E8 gate is consulted."""
    e1,e2,e3,e4,e5,e6,e7,e8=[evidence[k] for k in ("E1","E2","E3","E4","E5","E6","E7","E8")]
    scores=[_f(e.get("confidence")) for e in (e1,e2,e3,e4,e5,e6,e7,e8)]
    alignment=sum(scores)/len(scores)
    direction=e6.get("direction")
    supporting=sum(1 for e in (e3,e4,e5,e6,e7) if (e.get("direction") or direction)==direction and direction in ("BUY","SELL"))
    conflicts=[]
    if e3.get("structure") not in ("BULLISH" if direction=="BUY" else "BEARISH" if direction=="SELL" else "NONE"): conflicts.append("STRUCTURE_CONFLICT")
    if not e7.get("confirmed"): conflicts.append("ENTRY_NOT_CONFIRMED")
    if not e8.get("risk_valid"): conflicts.append("TRADE_ECONOMICS_UNATTRACTIVE")
    decision=direction if direction in ("BUY","SELL") and e7.get("confirmed") and e8.get("risk_valid") and alignment>=70 and not conflicts else "NO_TRADE"
    return {"engine":"E9","question":"Do the complete E1-E8 evidence support risking real capital now?","decision":decision,"execution_eligible":decision in ("BUY","SELL"),"confidence":round(alignment,1),"supporting_evidence_count":supporting,"conflicts":conflicts,"decision_reason":"HIGH_CONFLUENCE_AND_ASYMMETRY" if decision!="NO_TRADE" else (";".join(conflicts) or "INSUFFICIENT_CONFLUENCE"),"symbol":symbol}


def analyze(m5, m15=None, h1=None, symbol=None, index=None):
    if index is not None: m5=m5.iloc[:index+1].reset_index(drop=True)
    e1=e1_market_state(m5)
    e2=e2_regime(e1,m5)
    e3=e3_structure(m5,e1,e2)
    e4=e4_liquidity(m5,e1,e2,e3)
    e5=e5_location(m5,e1,e2,e3,e4)
    e6=e6_setup(m5,e1,e2,e3,e4,e5)
    e7=e7_confirmation(m5,e1,e2,e3,e4,e5,e6)
    e8=e8_risk(m5,e1,e2,e3,e4,e5,e6,e7)
    evidence={"E1":e1,"E2":e2,"E3":e3,"E4":e4,"E5":e5,"E6":e6,"E7":e7,"E8":e8}
    e9=e9_decision(evidence,symbol or "UNKNOWN")
    return {"engine_version":ENGINE_VERSION,"architecture":"E1→E2→E3→E4→E5→E6→E7→E8→E9","symbol":symbol,"signal":e9["decision"],"decision_authority":"E9","professional_decision":{"e1":e1,"e2":e2,"e3":e3,"e4":e4,"e5":e5,"e6":e6,"e7":e7,"e8":e8,"e9":e9},"evidence":evidence,"rejection_reasons":e9["conflicts"],"trade_levels":{"valid":e8.get("risk_valid",False),"entry":e8.get("entry"),"sl":e8.get("sl"),"tp":e8.get("target"),"risk_reward":e8.get("rr"),"minimum_rr":MIN_RR},"live_orders_allowed":False}
