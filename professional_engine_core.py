from __future__ import annotations

"""Production-V2 Evidence-Based Professional Decision Engine.

E1-E8 are sequential reasoning brains. They do not gate, block, or authorize
trades. Each engine answers its own professional question and passes evidence
to the next engine. E9 is the sole master decision brain.

No v11 or legacy signal engine is imported here.
"""

import math
import os
import pandas as pd

ENGINE_VERSION = "PROFESSIONAL-EVIDENCE-9E-v3.0"
MIN_RR = max(float(os.getenv("PROFESSIONAL_MIN_RR", "2.0")), 1.5)


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


def _ema(df, period):
    return pd.to_numeric(df["close"], errors="coerce").ewm(span=period, adjust=False).mean()


def _evidence(engine, question, conclusion, confidence, observations=None, **values):
    return {
        "engine": engine,
        "question": question,
        "analysis_status": "COMPLETE",
        "conclusion": conclusion,
        "confidence": round(_f(confidence), 1),
        "observations": observations or [],
        **values,
    }


def e1_market_state(m5, m15=None, h1=None):
    if len(m5) < 80:
        return _evidence("E1", "What is the current market state?", "INSUFFICIENT_DATA", 0, ["Need >=80 M5 candles"], analysis_status="INCOMPLETE", market_state="UNKNOWN")
    atr = _atr(m5)
    a = _f(atr.iloc[-1])
    base = max(_f(atr.tail(60).median(), a), 1e-9)
    e20 = _ema(m5, 20)
    e50 = _ema(m5, 50)
    c = _f(m5.close.iloc[-1])
    e20_now = _f(e20.iloc[-1])
    e50_now = _f(e50.iloc[-1])
    e20_slope = _f(e20.iloc[-1] - e20.iloc[-6])
    separation = abs(e20_now - e50_now) / max(a, 1e-9)
    aligned_up = c > e20_now > e50_now and e20_slope > 0
    aligned_down = c < e20_now < e50_now and e20_slope < 0
    vol_ratio = a / base
    if vol_ratio < 0.72:
        state = "COMPRESSION"
    elif vol_ratio > 1.28:
        state = "EXPANSION"
    elif aligned_up and separation > 0.25:
        state = "TREND_UP"
    elif aligned_down and separation > 0.25:
        state = "TREND_DOWN"
    elif separation < 0.25:
        state = "RANGE"
    else:
        state = "TRANSITION"
    confidence = min(96.0, max(40.0, 55.0 + min(separation * 20.0, 25.0) + min(abs(e20_slope) / max(a, 1e-9) * 12.0, 16.0)))
    return _evidence("E1", "What is the current market state?", state, confidence, [f"EMA20/EMA50 separation ATR={separation:.2f}", f"ATR ratio={vol_ratio:.2f}", f"EMA20 slope={e20_slope:.5g}"], market_state=state, trend_state="UP" if aligned_up else "DOWN" if aligned_down else "NEUTRAL", atr=a, atr_baseline=base, volatility_ratio=vol_ratio, ema_separation_atr=separation, ema20_slope=e20_slope)


def e2_regime(e1, m5, m15=None, h1=None):
    state = e1.get("market_state", "UNKNOWN")
    playbooks = {
        "TREND_UP": "TREND_CONTINUATION_OR_PULLBACK",
        "TREND_DOWN": "TREND_CONTINUATION_OR_PULLBACK",
        "RANGE": "RANGE_EDGE_REJECTION_OR_MEAN_REVERSION",
        "COMPRESSION": "BREAKOUT_BUILDUP",
        "EXPANSION": "MOMENTUM_OR_BREAKOUT_CONTINUATION",
        "TRANSITION": "WAIT_FOR_REGIME_RESOLUTION",
    }
    playbook = playbooks.get(state, "UNDEFINED")
    conclusion = playbook
    confidence = _f(e1.get("confidence")) * (0.82 if state == "TRANSITION" else 1.0)
    return _evidence("E2", "Given E1, what regime and opportunity is the market offering?", conclusion, confidence, [f"E1 state={state}", f"Selected opportunity={playbook}"], regime=state, playbook=playbook, opportunity=conclusion, directional_bias="BUY" if state == "TREND_UP" else "SELL" if state == "TREND_DOWN" else "CONDITIONAL")


def e3_structure(m5, e1, e2):
    if len(m5) < 70:
        return _evidence("E3", "What does price structure say about the current opportunity?", "INSUFFICIENT_DATA", 0, ["Need >=70 M5 candles"], structure="UNKNOWN", bos="NONE")
    closed = m5.iloc[:-1]
    recent = closed.tail(30)
    prior = closed.iloc[-60:-30]
    rh, rl = _f(recent.high.max()), _f(recent.low.min())
    ph, pl = _f(prior.high.max()), _f(prior.low.min())
    c = _f(m5.close.iloc[-1])
    higher_high = rh > ph
    lower_low = rl < pl
    bos = "BULLISH" if c > ph else "BEARISH" if c < pl else "NONE"
    structure = "BULLISH" if higher_high and not lower_low else "BEARISH" if lower_low and not higher_high else "MIXED" if higher_high or lower_low else "NEUTRAL"
    quality = 90 if bos != "NONE" else 70 if structure in ("BULLISH", "BEARISH") else 52
    return _evidence("E3", "What does price structure say about the current opportunity?", structure, quality, [f"Recent HH={higher_high}", f"Recent LL={lower_low}", f"BOS={bos}", f"E2 playbook={e2.get('playbook')}"], structure=structure, bos=bos, recent_high=rh, recent_low=rl, prior_high=ph, prior_low=pl, structural_bias="BUY" if structure == "BULLISH" else "SELL" if structure == "BEARISH" else "NEUTRAL")


def e4_liquidity(m5, e1, e2, e3):
    closed = m5.iloc[:-1]
    zone = closed.tail(20)
    hi, lo = _f(zone.high.max()), _f(zone.low.min())
    candle = m5.iloc[-1]
    h, l, c = _f(candle.high), _f(candle.low), _f(candle.close)
    sweep = "BUY_SIDE_SWEEP" if h > hi and c < hi else "SELL_SIDE_SWEEP" if l < lo and c > lo else "NONE"
    reaction = "REJECTION" if sweep != "NONE" else "UNRESOLVED"
    return _evidence("E4", "Where is liquidity and what did price do with it?", "SWEEP_AND_REJECTION" if sweep != "NONE" else "NO_CLEAR_EVENT", 90 if sweep != "NONE" else 56, [f"Sweep={sweep}", f"Reaction={reaction}", f"Structure={e3.get('structure')}"], liquidity_event=sweep, reaction=reaction, liquidity_state="ACTIVE_EVENT" if sweep != "NONE" else "UNRESOLVED", zone_high=hi, zone_low=lo, acceptance="ABOVE" if c > hi else "BELOW" if c < lo else "INSIDE")


def e5_location(m5, e1, e2, e3, e4):
    hi, lo, c = _f(e3.get("recent_high")), _f(e3.get("recent_low")), _f(m5.close.iloc[-1])
    width = max(hi - lo, 1e-9)
    position = (c - lo) / width
    location = "DISCOUNT" if position < 0.35 else "PREMIUM" if position > 0.65 else "EQUILIBRIUM"
    direction = "BUY" if e3.get("structural_bias") == "BUY" else "SELL" if e3.get("structural_bias") == "SELL" else "NONE"
    advantage = (direction == "BUY" and location == "DISCOUNT") or (direction == "SELL" and location == "PREMIUM")
    return _evidence("E5", "Is current price located where the opportunity has asymmetric location?", "ADVANTAGE" if advantage else "NEUTRAL_OR_POOR", 88 if advantage else 50, [f"Location={location}", f"Range position={position:.2f}", f"Direction={direction}", f"Liquidity={e4.get('liquidity_event')}"], location=location, position_in_range=round(position, 3), direction=direction, advantage=advantage, location_quality="HIGH" if advantage else "LOW")


def e6_setup(m5, e1, e2, e3, e4, e5):
    direction = e5.get("direction")
    candle = m5.iloc[-1]
    body = abs(_f(candle.close) - _f(candle.open))
    atr = max(_f(_atr(m5).iloc[-1]), 1e-9)
    impulse = body >= 0.35 * atr
    sweep = e4.get("liquidity_event")
    liquidity_support = (direction == "BUY" and sweep == "SELL_SIDE_SWEEP") or (direction == "SELL" and sweep == "BUY_SIDE_SWEEP")
    trend_setup = e2.get("playbook") == "TREND_CONTINUATION_OR_PULLBACK" and impulse
    setup = "LIQUIDITY_REVERSAL" if liquidity_support else "TREND_CONTINUATION" if trend_setup else "NONE"
    maturity = "MATURE" if setup != "NONE" else "EARLY"
    confidence = 92 if setup != "NONE" and e5.get("advantage") else 70 if setup != "NONE" else 38
    return _evidence("E6", "Has the opportunity matured into a recognizable setup?", setup if setup != "NONE" else "NO_VALID_SETUP", confidence, [f"Direction={direction}", f"Impulse={impulse}", f"Liquidity support={liquidity_support}", f"Location advantage={e5.get('advantage')}"], setup=setup, setup_state=maturity, direction=direction, impulse=impulse, liquidity_support=liquidity_support)


def e7_confirmation(m5, e1, e2, e3, e4, e5, e6):
    direction = e6.get("direction")
    if direction not in ("BUY", "SELL") or e6.get("setup") == "NONE":
        return _evidence("E7", "Has price confirmed the setup thesis?", "NO_CONFIRMATION", 20, ["Setup is not currently executable"], confirmation="NONE", confirmed=False)
    candle = m5.iloc[-1]
    o, c = _f(candle.open), _f(candle.close)
    body = abs(c - o)
    atr = max(_f(_atr(m5).iloc[-1]), 1e-9)
    directional = (direction == "BUY" and c > o) or (direction == "SELL" and c < o)
    displacement = body >= 0.30 * atr
    bos = (direction == "BUY" and e3.get("bos") == "BULLISH") or (direction == "SELL" and e3.get("bos") == "BEARISH")
    sweep = (direction == "BUY" and e4.get("liquidity_event") == "SELL_SIDE_SWEEP") or (direction == "SELL" and e4.get("liquidity_event") == "BUY_SIDE_SWEEP")
    confirmed = directional and displacement and (bos or sweep)
    return _evidence("E7", "Has price confirmed the setup thesis?", "CONFIRMED" if confirmed else "UNCONFIRMED", 94 if confirmed else 44, [f"Directional candle={directional}", f"Displacement={displacement}", f"BOS confirmation={bos}", f"Liquidity confirmation={sweep}"], confirmation="CONFIRMED" if confirmed else "NONE", confirmed=confirmed, directional_candle=directional, displacement=displacement, bos_confirmation=bos, liquidity_confirmation=sweep)


def e8_risk(m5, e1, e2, e3, e4, e5, e6, e7):
    direction = e6.get("direction")
    if direction not in ("BUY", "SELL"):
        return _evidence("E8", "What are the trade economics and downside?", "NOT_READY", 0, ["No directional setup"], risk_assessment="NOT_READY", risk_valid=False)
    entry = _f(m5.close.iloc[-1])
    atr = max(_f(_atr(m5).iloc[-1]), 1e-9)
    if direction == "BUY":
        sl = min(_f(m5.low.tail(5).min()), _f(e3.get("recent_low"))) - 0.10 * atr
        target = _f(e3.get("recent_high"))
    else:
        sl = max(_f(m5.high.tail(5).max()), _f(e3.get("recent_high"))) + 0.10 * atr
        target = _f(e3.get("recent_low"))
    risk = abs(entry - sl)
    reward = abs(target - entry)
    rr = reward / risk if risk else 0.0
    valid = risk > 0 and reward > 0 and rr >= MIN_RR
    assessment = "ATTRACTIVE" if valid else "MARGINAL_OR_POOR"
    return _evidence("E8", "What are the trade economics and downside?", assessment, 92 if valid else 30, [f"Entry={entry}", f"SL={sl}", f"Target={target}", f"RR={rr:.2f}", f"Minimum RR={MIN_RR:.2f}", f"Confirmation={e7.get('confirmed')}"], risk_assessment=assessment, risk_valid=valid, entry=entry, sl=sl, target=target, risk=risk, reward=reward, rr=rr, minimum_rr=MIN_RR)


def e9_decision(evidence, symbol):
    """Master brain. It synthesizes E1-E8 evidence; it does not read gates."""
    e1, e2, e3, e4, e5, e6, e7, e8 = [evidence[k] for k in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8")]
    confidence_values = [_f(x.get("confidence")) for x in (e1, e2, e3, e4, e5, e6, e7, e8)]
    alignment = sum(confidence_values) / len(confidence_values)
    direction = e6.get("direction")
    votes = {"BUY": 0, "SELL": 0}
    if e1.get("market_state") == "TREND_UP": votes["BUY"] += 2
    if e1.get("market_state") == "TREND_DOWN": votes["SELL"] += 2
    if e3.get("structure") == "BULLISH": votes["BUY"] += 2
    if e3.get("structure") == "BEARISH": votes["SELL"] += 2
    if direction in votes: votes[direction] += 2
    if e7.get("confirmed") and direction in votes: votes[direction] += 2
    if e8.get("risk_valid") and direction in votes: votes[direction] += 1
    chosen = max(votes, key=votes.get)
    conflicts = []
    if e1.get("market_state") in ("TRANSITION", "UNKNOWN"): conflicts.append("REGIME_UNRESOLVED")
    if e3.get("structure") == "MIXED": conflicts.append("STRUCTURE_MIXED")
    if e6.get("setup") == "NONE": conflicts.append("NO_MATURE_SETUP")
    if not e7.get("confirmed"): conflicts.append("ENTRY_NOT_CONFIRMED")
    if not e8.get("risk_valid"): conflicts.append("TRADE_ECONOMICS_NOT_ATTRACTIVE")
    opposing = votes["SELL"] if chosen == "BUY" else votes["BUY"]
    master_score = max(0.0, min(100.0, alignment + (votes[chosen] - opposing) * 2.0))
    decision = chosen if chosen == direction and e7.get("confirmed") and e8.get("risk_valid") and master_score >= 70 and not conflicts else "NO_TRADE"
    return {"engine": "E9", "question": "Do the complete E1-E8 evidence justify risking capital now?", "decision": decision, "execution_eligible": decision in ("BUY", "SELL"), "confidence": round(master_score, 1), "evidence_alignment": round(alignment, 1), "directional_votes": votes, "conflicts": conflicts, "decision_reason": "HIGH_CONFLUENCE_AND_ASYMMETRY" if decision != "NO_TRADE" else (";".join(conflicts) or "INSUFFICIENT_CONFLUENCE"), "symbol": symbol}


def analyze(m5, m15=None, h1=None, symbol=None, index=None):
    if index is not None:
        m5 = m5.iloc[:index + 1].reset_index(drop=True)
    e1 = e1_market_state(m5, m15, h1)
    e2 = e2_regime(e1, m5, m15, h1)
    e3 = e3_structure(m5, e1, e2)
    e4 = e4_liquidity(m5, e1, e2, e3)
    e5 = e5_location(m5, e1, e2, e3, e4)
    e6 = e6_setup(m5, e1, e2, e3, e4, e5)
    e7 = e7_confirmation(m5, e1, e2, e3, e4, e5, e6)
    e8 = e8_risk(m5, e1, e2, e3, e4, e5, e6, e7)
    evidence = {f"E{i}": value for i, value in enumerate((e1, e2, e3, e4, e5, e6, e7, e8), 1)}
    e9 = e9_decision(evidence, symbol or "UNKNOWN")
    return {"engine_version": ENGINE_VERSION, "architecture": "E1→E2→E3→E4→E5→E6→E7→E8→E9", "symbol": symbol, "signal": e9["decision"], "decision_authority": "E9", "professional_decision": {**{k.lower(): v for k, v in evidence.items()}, "e9": e9}, "evidence": evidence, "rejection_reasons": e9["conflicts"], "trade_levels": {"valid": e8.get("risk_valid", False), "entry": e8.get("entry"), "sl": e8.get("sl"), "tp": e8.get("target"), "risk_reward": e8.get("rr"), "minimum_rr": MIN_RR}, "live_orders_allowed": False}
