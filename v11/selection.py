from __future__ import annotations

DIRECTION_FILTERED={"TREND_PULLBACK","BREAKOUT_RETEST","VWAP_MOMENTUM_PULLBACK","OPENING_RANGE_BREAKOUT"}

def _num(v,default=0.0):
    try:return float(v)
    except (TypeError,ValueError):return default

def rank(candidates,direction,m15_direction):
    eligible=[]
    for c in candidates:
        if c.get("status")!="PASS" or c.get("direction")!=direction:continue
        strategy=str(c.get("strategy",""))
        if strategy in DIRECTION_FILTERED and m15_direction in ("BUY","SELL") and direction!=m15_direction:continue
        eligible.append(c)
    def key(c):
        ev=c.get("evidence") or {}; quality=_num(c.get("quality",ev.get("quality",0))); freshness=_num(c.get("freshness_bars",ev.get("freshness_bars",999)),999); return (-quality,freshness,str(c.get("strategy","")))
    return sorted(eligible,key=key)

def select(candidates,m15_direction):
    if m15_direction not in ("BUY","SELL","NEUTRAL"):return None
    directions=(m15_direction,) if m15_direction in ("BUY","SELL") else ("BUY","SELL")
    ranked=[]
    for direction in directions:ranked.extend(rank(candidates,direction,m15_direction))
    return ranked[0] if ranked else None
