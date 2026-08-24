from __future__ import annotations

def _num(v, default=0.0):
    try: return float(v)
    except (TypeError, ValueError): return default

def rank(candidates, direction, m15_direction):
    eligible = [c for c in candidates if c.get("status") == "PASS" and c.get("direction") == direction and (m15_direction == "NEUTRAL" or direction == m15_direction)]
    def key(c):
        ev=c.get("evidence") or {}
        quality=_num(c.get("quality",ev.get("quality",0.0)))
        freshness=_num(c.get("freshness_bars",ev.get("freshness_bars",999.0)),999.0)
        rr=_num(c.get("risk_reward",ev.get("risk_reward",0.0)))
        return (-quality,freshness,-rr,str(c.get("strategy","")))
    return sorted(eligible,key=key)

def select(candidates,m15_direction):
    if m15_direction not in ("BUY","SELL","NEUTRAL"): return None
    # In TREND regimes, only the M15 direction is eligible. In RANGE/NEUTRAL,
    # independent mean-reversion setups (e.g. VWAP) may be selected.
    for direction in ((m15_direction,) if m15_direction in ("BUY","SELL") else ("BUY","SELL")):
        ranked=rank(candidates,direction,m15_direction)
        if ranked:return ranked[0]
    return None
