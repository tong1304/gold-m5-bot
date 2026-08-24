from __future__ import annotations
import math
from .common import num, atr14, structure

MIN_RISK_REWARD = 2.0

def calculate(m5, direction: str, strategy: str, evidence: dict | None = None, *, rr: float = MIN_RISK_REWARD):
    evidence = evidence or {}
    if direction not in ("BUY", "SELL"):
        return {"valid": False, "reason": "INVALID_DIRECTION"}
    x = m5.tail(30).reset_index(drop=True)
    if len(x) < 14:
        return {"valid": False, "reason": "INSUFFICIENT_RISK_CONTEXT"}
    entry = num(x.close.iloc[-1]); a = num(atr14(x).iloc[-1])
    if not math.isfinite(entry) or entry <= 0 or not math.isfinite(a) or a <= 0:
        return {"valid": False, "reason": "ATR_UNAVAILABLE"}
    s = structure(x, 25)
    raw = evidence.get("support") if direction == "BUY" else evidence.get("resistance")
    if raw is None: raw = s["support"] if direction == "BUY" else s["resistance"]
    raw = num(raw)
    if direction == "BUY":
        sl = min(raw - a * .10, entry - a * .80); risk = entry - sl; tp = entry + rr * risk
    else:
        sl = max(raw + a * .10, entry + a * .80); risk = sl - entry; tp = entry - rr * risk
    if not all(math.isfinite(v) for v in (sl, tp, risk)) or risk <= 0 or min(entry, sl, tp) <= 0:
        return {"valid": False, "reason": "INVALID_RISK"}
    effective_rr = abs(tp-entry) / risk
    valid = effective_rr >= MIN_RISK_REWARD and ((direction == "BUY" and sl < entry < tp) or (direction == "SELL" and sl > entry > tp))
    return {"valid": bool(valid), "entry": entry, "sl": sl, "tp": tp, "risk": risk, "risk_reward": round(effective_rr, 4), "effective_rr": round(effective_rr, 4), "target_rr": MIN_RISK_REWARD, "strategy": strategy}
