from __future__ import annotations

from statistics import mean
from typing import Any
from .contracts import EngineResult

NAME = "Setup Brain"


def _ema(values, period):
    if not values: return 0.0
    a = 2.0 / (period + 1.0); x = values[0]
    for v in values[1:]: x = a * v + (1-a) * x
    return x


def analyze_e6(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    bars = list(snapshot.get("bars") or [])
    if len(bars) < 30:
        return EngineResult("E6", NAME, False, 0.0, {"state":"UNRESOLVED","setup":"NONE","question":"What setup is forming?"}, ("INSUFFICIENT_DATA",))
    closes=[float(b["close"]) for b in bars]; highs=[float(b["high"]) for b in bars]; lows=[float(b["low"]) for b in bars]
    atr=mean([float(b["high"])-float(b["low"]) for b in bars[-14:]])
    ema20=_ema(closes,20); ema50=_ema(closes,50); price=closes[-1]
    e1=upstream.get("E1"); state=str((e1.output if e1 else {}).get("market_state","UNCLEAR"))
    direction="BUY" if state=="TREND_UP" or (price>ema20>ema50) else "SELL" if state=="TREND_DOWN" or (price<ema20<ema50) else "NEUTRAL"
    prior_hi=max(highs[-11:-1]); prior_lo=min(lows[-11:-1]); body=abs(closes[-1]-float(bars[-1]["open"]))
    impulse=body >= max(0.65*atr, 1e-9)
    pullback=(direction=="BUY" and price<=ema20+0.35*atr) or (direction=="SELL" and price>=ema20-0.35*atr)
    breakout=(direction=="BUY" and price>prior_hi) or (direction=="SELL" and price<prior_lo)
    mature=direction in {"BUY","SELL"} and (impulse or breakout or pullback)
    quality=60.0 + (15 if impulse else 0) + (15 if pullback else 0) + (10 if breakout else 0)
    state_out="MATURE" if mature else "FORMING"
    reasons=[]
    if not impulse: reasons.append("NO_CLEAR_IMPULSE")
    if not pullback and not breakout: reasons.append("NO_CONTINUATION_LOCATION")
    return EngineResult("E6",NAME,mature,min(100.0,quality),{
        "question":"What setup is forming?","state":state_out,"setup":"TREND_CONTINUATION" if mature else "NONE",
        "direction":direction,"impulse":impulse,"pullback":pullback,"breakout":breakout,"maturity":"MATURE" if mature else "FORMING",
        "ema20":ema20,"ema50":ema50,"atr":atr,"reasoning_role":"SETUP_ANALYST","decision_authority":"E9"
    },tuple(reasons))
