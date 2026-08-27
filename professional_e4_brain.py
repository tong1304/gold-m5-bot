from __future__ import annotations

"""E4 — Professional Liquidity & Auction Brain.

Single-brain implementation at the same repository level as professional E1-E3.
E4 independently answers one professional question from CLOSED M5 price data:
where liquidity is, whether it was swept/accepted/rejected, and whether a
break failed and reclaimed. Upstream E1-E3 may be supplied only as contextual
evidence; their decisions, gates and scores are never consumed.

E4 is evidence-only. It never authorizes a trade. E9 remains the sole decision
authority.
"""

import math
from typing import Any

QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_BRAIN_V11"
_FORBIDDEN = {"decision", "trade_decision", "decision_score", "score", "gate", "gate_passed", "specialist_gate"}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _bars(snapshot: Any) -> list[dict[str, float]]:
    source = snapshot if isinstance(snapshot, list) else (snapshot or {}).get("bars") or []
    out = []
    for bar in source:
        if not isinstance(bar, dict):
            continue
        row = {k: _f(bar.get(k), float("nan")) for k in ("open", "high", "low", "close")}
        if all(math.isfinite(v) for v in row.values()) and row["high"] >= row["low"]:
            out.append(row)
    return out


def _atr(bars: list[dict[str, float]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    tr = []
    for i in range(1, len(bars)):
        b, p = bars[i], bars[i - 1]
        tr.append(max(b["high"] - b["low"], abs(b["high"] - p["close"]), abs(b["low"] - p["close"])))
    return sum(tr[-period:]) / min(period, len(tr))


def _pivots(bars: list[dict[str, float]], wing: int):
    highs, lows = [], []
    for i in range(wing, len(bars) - wing):
        window = bars[i - wing:i + wing + 1]
        if bars[i]["high"] >= max(x["high"] for x in window):
            highs.append((i, bars[i]["high"]))
        if bars[i]["low"] <= min(x["low"] for x in window):
            lows.append((i, bars[i]["low"]))
    return highs, lows


def _clusters(levels, tolerance: float, current: int):
    groups = []
    for idx, price in sorted(levels, key=lambda x: x[1]):
        if not groups or abs(price - sum(p for _, p in groups[-1]) / len(groups[-1])) > tolerance:
            groups.append([(idx, price)])
        else:
            groups[-1].append((idx, price))
    zones = []
    for group in groups:
        prices = [p for _, p in group]
        last_touch = max(i for i, _ in group)
        touches = len(group)
        age = max(0, current - last_touch)
        zones.append({"price": sum(prices) / len(prices), "lower": min(prices), "upper": max(prices), "touches": touches, "last_touch_index": last_touch, "age_bars": age, "fresh": touches <= 2 and age <= 40, "type": "CLUSTERED" if touches > 1 else "SWING"})
    return zones


def _context_hint(bus):
    votes = []
    for eid in ("E1", "E2", "E3"):
        package = (bus or {}).get(eid, {})
        evidence = package.get("evidence") if isinstance(package, dict) else None
        if isinstance(evidence, dict):
            evidence = evidence.get("output", evidence)
        if not isinstance(evidence, dict):
            continue
        text = str({k: v for k, v in evidence.items() if str(k).lower() not in _FORBIDDEN}).upper()
        if any(t in text for t in ("DIRECTION=UP", "TREND_STATE=UP", "PRESSURE=BULLISH")):
            votes.append("UP")
        if any(t in text for t in ("DIRECTION=DOWN", "TREND_STATE=DOWN", "PRESSURE=BEARISH")):
            votes.append("DOWN")
    return "UP" if votes.count("UP") > votes.count("DOWN") else "DOWN" if votes.count("DOWN") > votes.count("UP") else "NEUTRAL"


def _event(bars, highs, lows, atr):
    last, prev = bars[-1], bars[-2]
    tol = max(atr * 0.10, 1e-9)
    rng = max(last["high"] - last["low"], 1e-9)
    upper_wick = last["high"] - max(last["open"], last["close"])
    lower_wick = min(last["open"], last["close"]) - last["low"]
    hc = [z for z in highs if last["high"] >= z["lower"] - tol]
    lc = [z for z in lows if last["low"] <= z["upper"] + tol]
    hz = min(hc, key=lambda z: abs(last["high"] - z["price"]), default=None)
    lz = min(lc, key=lambda z: abs(last["low"] - z["price"]), default=None)
    hf = bool(hz and prev["close"] > hz["upper"] + atr * 0.10 and last["close"] <= hz["upper"])
    lf = bool(lz and prev["close"] < lz["lower"] - atr * 0.10 and last["close"] >= lz["lower"])
    hs = bool(hz and last["high"] > hz["upper"] + tol * 0.05 and last["close"] <= hz["upper"] + tol * 0.10)
    ls = bool(lz and last["low"] < lz["lower"] - tol * 0.05 and last["close"] >= lz["lower"] - tol * 0.10)
    ha = bool(hz and last["close"] > hz["upper"] + atr * 0.15)
    la = bool(lz and last["close"] < lz["lower"] - atr * 0.15)
    if hf: return {"type":"HIGH_FAILED_BREAK_RECLAIM","state":"TAKEN","direction":"DOWN","zone":hz,"strength":0.86}
    if lf: return {"type":"LOW_FAILED_BREAK_RECLAIM","state":"TAKEN","direction":"UP","zone":lz,"strength":0.86}
    if hs and upper_wick / rng >= 0.30: return {"type":"HIGH_SWEEP_REJECTION","state":"TAKEN","direction":"DOWN","zone":hz,"strength":0.90}
    if ls and lower_wick / rng >= 0.30: return {"type":"LOW_SWEEP_REJECTION","state":"TAKEN","direction":"UP","zone":lz,"strength":0.90}
    if ha: return {"type":"HIGH_LIQUIDITY_ACCEPTANCE","state":"ACCEPTED","direction":"UP","zone":hz,"strength":0.82}
    if la: return {"type":"LOW_LIQUIDITY_ACCEPTANCE","state":"ACCEPTED","direction":"DOWN","zone":lz,"strength":0.82}
    if hs: return {"type":"HIGH_LIQUIDITY_INTERACTION","state":"TAKEN","direction":"NEUTRAL","zone":hz,"strength":0.58}
    if ls: return {"type":"LOW_LIQUIDITY_INTERACTION","state":"TAKEN","direction":"NEUTRAL","zone":lz,"strength":0.58}
    return {"type":"NO_CONFIRMED_LIQUIDITY_EVENT","state":"UNRESOLVED","direction":"NEUTRAL","zone":None,"strength":0.42}


def analyze_e4(snapshot: dict[str, Any] | list[dict[str, Any]] | None = None, evidence_bus: dict[str, Any] | None = None) -> dict[str, Any]:
    bars = _bars(snapshot or {})
    ctx = _context_hint(evidence_bus)
    if len(bars) < 30:
        return {"engine":"E4","architecture":ARCHITECTURE,"question":QUESTION,"analysis_status":"INCOMPLETE","finding":"LIQUIDITY_DATA_INSUFFICIENT","direction":"NEUTRAL","directional_implication":"NEUTRAL","contextual_direction_hint":ctx,"confidence":0.0,"evidence_strength":0.0,"observations":["Need >=30 closed M5 candles"],"liquidity_map":{"high_zones":[],"low_zones":[]},"event":{"type":"LIQUIDITY_DATA_INSUFFICIENT","liquidity_state":"UNRESOLVED"},"auction_state":"UNRESOLVED","missing_evidence":["CLOSED_CANDLE_HISTORY"],"reasons":["INSUFFICIENT_CLOSED_CANDLE_DATA"],"conflicts":[],"decision":None,"gate":None,"score":None,"trade_decision_authority":False,"decision_authority":"E9_ONLY"}

    atr = _atr(bars)
    hi, lo = _pivots(bars, 2)
    tolerance = max(atr * 0.15, 1e-9)
    high_zones = _clusters(hi[-40:], tolerance, len(bars)-1)
    low_zones = _clusters(lo[-40:], tolerance, len(bars)-1)
    event = _event(bars, high_zones, low_zones, atr)
    et = event["type"]
    auction = "REJECTION" if et.endswith("REJECTION") or "FAILED_BREAK" in et else "ACCEPTANCE" if et.endswith("ACCEPTANCE") else "BALANCED" if high_zones and low_zones else "UNRESOLVED"
    reasons = []
    if event["state"] == "TAKEN": reasons.append("LIQUIDITY_TAKEN")
    if et.endswith("REJECTION"): reasons.append("REJECTION_AFTER_SWEEP")
    if "FAILED_BREAK" in et: reasons.append("FAILED_BREAK_RECLAIM")
    if et.endswith("ACCEPTANCE"): reasons.append("ACCEPTANCE_BEYOND_LIQUIDITY")
    if et == "NO_CONFIRMED_LIQUIDITY_EVENT": reasons.append("NO_CONFIRMED_EVENT")
    return {"engine":"E4","architecture":ARCHITECTURE,"question":QUESTION,"analysis_status":"COMPLETE","finding":et,"direction":event["direction"],"directional_implication":event["direction"],"contextual_direction_hint":ctx,"confidence":round(event["strength"],3),"evidence_strength":round(event["strength"],3),"observations":[f"closed_candles={len(bars)}",f"atr14={atr:.6f}",f"high_liquidity_zones={len(high_zones)}",f"low_liquidity_zones={len(low_zones)}",f"event={et}",f"auction_state={auction}",f"contextual_direction={ctx}"],"liquidity_map":{"high_zones":high_zones,"low_zones":low_zones},"event":{"type":et,"liquidity_state":event["state"],"direction":event["direction"],"zone":event["zone"]},"interaction":{"type":et,"accepted":event["state"]=="ACCEPTED","rejected":auction=="REJECTION"},"auction_state":auction,"missing_evidence":[] if et != "NO_CONFIRMED_LIQUIDITY_EVENT" else ["CONFIRMED_AUCTION_EVENT"],"reasons":reasons,"conflicts":[],"decision":None,"gate":None,"score":None,"trade_decision_authority":False,"decision_authority":"E9_ONLY"}


__all__ = ["ARCHITECTURE", "QUESTION", "analyze_e4"]
