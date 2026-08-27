from __future__ import annotations

"""E3 — Professional Market Structure Brain.

Single-brain implementation. Former 3A-3F concepts are parked and are not
separate runtime engines. E3 analyzes structure only and never authorizes or
blocks a trade.
"""

import math
import pandas as pd


def _f(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _atr(df, period=14):
    h = pd.to_numeric(df["high"], errors="coerce")
    l = pd.to_numeric(df["low"], errors="coerce")
    c = pd.to_numeric(df["close"], errors="coerce")
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=3).mean()


def e3_structure(m5, e1, e2):
    """Professional structure synthesis from closed M5 candles.

    Pivot significance is ATR-normalized. Internal and external structure are
    evaluated in one brain. BOS requires a close beyond a confirmed swing;
    wick-only breaks are not accepted as BOS. Conflicts remain visible.
    """
    question = "What does price structure say about the current opportunity?"
    if len(m5) < 80:
        return {"engine":"E3","question":question,"analysis_status":"INCOMPLETE","conclusion":"INSUFFICIENT_DATA","confidence":0.0,"observations":["Need >=80 M5 candles for confirmed structure"],"structure":"UNKNOWN","structure_state":"UNKNOWN","bos":"NONE","structural_bias":"NEUTRAL"}

    # The live scanner already removes the forming candle. Therefore E3 must
    # analyze the complete supplied frame rather than dropping one extra bar.
    closed = m5.copy()
    for col in ("open","high","low","close"):
        closed[col] = pd.to_numeric(closed[col], errors="coerce")
    closed = closed.dropna(subset=["high","low","close"]).reset_index(drop=True)
    if len(closed) < 70:
        return {"engine":"E3","question":question,"analysis_status":"INCOMPLETE","conclusion":"INSUFFICIENT_DATA","confidence":0.0,"observations":["Not enough valid closed candles for structure confirmation"],"structure":"UNKNOWN","structure_state":"UNKNOWN","bos":"NONE","structural_bias":"NEUTRAL"}

    atr_series = _atr(closed)
    atr_now = max(_f(atr_series.iloc[-1]), 1e-9)

    def pivots(window):
        highs, lows = [], []
        if len(closed) < window * 2 + 5:
            return highs, lows
        h, l = closed["high"].to_numpy(), closed["low"].to_numpy()
        for i in range(window, len(closed) - window):
            rng = max(_f(atr_series.iloc[i]), 1e-9)
            left_h, right_h = max(h[i-window:i]), max(h[i+1:i+window+1])
            left_l, right_l = min(l[i-window:i]), min(l[i+1:i+window+1])
            if h[i] == max(h[i-window:i+window+1]) and h[i] - left_h >= 0.12*rng and h[i] - right_h >= 0.08*rng:
                highs.append((i, _f(h[i]), rng))
            if l[i] == min(l[i-window:i+window+1]) and left_l - l[i] >= 0.12*rng and right_l - l[i] >= 0.08*rng:
                lows.append((i, _f(l[i]), rng))
        return highs, lows

    internal_h, internal_l = pivots(2)
    external_h, external_l = pivots(4)

    def classify(highs, lows):
        counts={"HH":0,"HL":0,"LH":0,"LL":0}; labels=[]
        for a,b in zip(highs[-6:-1], highs[-5:]):
            x="HH" if b[1]>a[1] else "LH"; labels.append(x); counts[x]+=1
        for a,b in zip(lows[-6:-1], lows[-5:]):
            x="HL" if b[1]>a[1] else "LL"; labels.append(x); counts[x]+=1
        bull=counts["HH"]+counts["HL"]; bear=counts["LH"]+counts["LL"]
        state="BULLISH" if bull>=2 and bull>bear+1 else "BEARISH" if bear>=2 and bear>bull+1 else "MIXED" if bull or bear else "NEUTRAL"
        return state, labels, counts

    ext_state, ext_labels, ext_counts = classify(external_h, external_l)
    int_state, int_labels, int_counts = classify(internal_h, internal_l)
    last_close = _f(closed["close"].iloc[-1]); prior_close = _f(closed["close"].iloc[-2])
    ext_h = external_h[-1] if external_h else None
    ext_l = external_l[-1] if external_l else None
    bull_bos = bool(ext_h and last_close > ext_h[1] and prior_close <= ext_h[1])
    bear_bos = bool(ext_l and last_close < ext_l[1] and prior_close >= ext_l[1])
    bos = "BULLISH" if bull_bos else "BEARISH" if bear_bos else "NONE"
    bos_level = ext_h[1] if bull_bos else ext_l[1] if bear_bos else None
    bos_index = ext_h[0] if bull_bos else ext_l[0] if bear_bos else None

    failure="NONE"; failure_type="NONE"; failure_level=None
    recent=closed.tail(4)
    if ext_h and bool((recent["high"] > ext_h[1]).any()) and _f(recent["close"].iloc[-1]) < ext_h[1]:
        failure="BULLISH_BREAK_FAILURE"; failure_type="FAILED_UPSIDE_ACCEPTANCE"; failure_level=ext_h[1]
    elif ext_l and bool((recent["low"] < ext_l[1]).any()) and _f(recent["close"].iloc[-1]) > ext_l[1]:
        failure="BEARISH_BREAK_FAILURE"; failure_type="FAILED_DOWNSIDE_ACCEPTANCE"; failure_level=ext_l[1]

    events=min(4,len(external_h)+len(external_l)); internal_events=min(4,len(internal_h)+len(internal_l)); continuity=max(ext_counts.values()) if ext_counts else 0
    strength=35.0+events*7.0+internal_events*3.0+min(continuity*4.0,16.0)
    if bos!="NONE": strength+=12.0
    if failure!="NONE": strength-=10.0
    if ext_state==int_state and ext_state in ("BULLISH","BEARISH"): strength+=8.0
    strength=max(0.0,min(100.0,strength))

    if failure=="BULLISH_BREAK_FAILURE": state="BEARISH_FAILURE_RISK"
    elif failure=="BEARISH_BREAK_FAILURE": state="BULLISH_FAILURE_RISK"
    elif bos=="BULLISH": state="BULLISH_BOS"
    elif bos=="BEARISH": state="BEARISH_BOS"
    elif ext_state=="BULLISH" and int_state=="BEARISH": state="BULLISH_EXTERNAL_BEARISH_INTERNAL"
    elif ext_state=="BEARISH" and int_state=="BULLISH": state="BEARISH_EXTERNAL_BULLISH_INTERNAL"
    elif ext_state in ("BULLISH","BEARISH"): state=ext_state
    else: state="MIXED" if int_state=="MIXED" else "NEUTRAL"

    if state.startswith("BULLISH") or ext_state=="BULLISH": bias="BUY"
    elif state.startswith("BEARISH") or ext_state=="BEARISH": bias="SELL"
    else: bias="NEUTRAL"
    conflicts=[]
    if ext_state!=int_state and ext_state in ("BULLISH","BEARISH") and int_state in ("BULLISH","BEARISH"): conflicts.append("INTERNAL_EXTERNAL_DIVERGENCE")
    if e2.get("directional_bias") in ("BUY","SELL") and bias in ("BUY","SELL") and e2.get("directional_bias")!=bias: conflicts.append("E2_STRUCTURE_DIRECTION_CONFLICT")
    if failure!="NONE": conflicts.append("STRUCTURAL_FAILURE_PRESENT")
    confidence=max(20.0,min(96.0,strength-8.0*len(conflicts)))
    structure="BULLISH" if bias=="BUY" else "BEARISH" if bias=="SELL" else "MIXED" if "MIXED" in state else "NEUTRAL"
    observations=[f"External={ext_state}; Internal={int_state}",f"External HH={ext_counts['HH']} HL={ext_counts['HL']} LH={ext_counts['LH']} LL={ext_counts['LL']}",f"Internal HH={int_counts['HH']} HL={int_counts['HL']} LH={int_counts['LH']} LL={int_counts['LL']}",f"BOS={bos}; failure={failure}; strength={strength:.1f}",f"E1 state={e1.get('market_state','UNKNOWN')}; E2 playbook={e2.get('playbook','UNKNOWN')}"]
    return {"engine":"E3","question":question,"analysis_status":"COMPLETE","conclusion":state,"confidence":round(confidence,1),"observations":observations,"structure":structure,"structure_state":state,"internal_structure":int_state,"external_structure":ext_state,"internal_labels":int_labels[-10:],"external_labels":ext_labels[-10:],"swing_map":{"external_highs":[{"index":i,"price":round(p,6)} for i,p,_ in external_h[-6:]],"external_lows":[{"index":i,"price":round(p,6)} for i,p,_ in external_l[-6:]],"internal_highs":[{"index":i,"price":round(p,6)} for i,p,_ in internal_h[-8:]],"internal_lows":[{"index":i,"price":round(p,6)} for i,p,_ in internal_l[-8:]]},"HH":ext_counts["HH"],"HL":ext_counts["HL"],"LH":ext_counts["LH"],"LL":ext_counts["LL"],"BOS":bos,"bos":bos,"BOS_type":"EXTERNAL_CLOSE_BREAK" if bos!="NONE" else "NONE","bos_type":"EXTERNAL_CLOSE_BREAK" if bos!="NONE" else "NONE","BOS_level":round(bos_level,6) if bos_level is not None else None,"bos_level":round(bos_level,6) if bos_level is not None else None,"BOS_candle_index":bos_index,"structural_failure":failure,"failure_type":failure_type,"failure_level":round(failure_level,6) if failure_level is not None else None,"strength":round(strength,1),"structure_strength":round(strength,1),"directional_bias":bias,"structural_bias":bias,"recent_high":round(_f(closed["high"].tail(30).max()),6),"recent_low":round(_f(closed["low"].tail(30).min()),6),"prior_high":round(_f(closed["high"].iloc[-60:-30].max()),6),"prior_low":round(_f(closed["low"].iloc[-60:-30].min()),6),"atr":round(atr_now,6),"conflicts":conflicts,"evidence":observations,"reasoning_trace":{"closed_candles":len(closed),"internal_pivot_window":2,"external_pivot_window":4,"atr_prominence_threshold":0.12,"bos_requires_close":True,"external_structure_state":ext_state,"internal_structure_state":int_state}}
