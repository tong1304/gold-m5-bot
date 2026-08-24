from __future__ import annotations
import pandas as pd
from datetime import timedelta
from . import engine

def resolve_outcome(signal: dict, future: pd.DataFrame):
    if signal.get("signal") not in ("BUY","SELL"): return {"result":"NO_TRADE","r_multiple":0.0}
    l=signal.get("trade_levels") or {}; entry=float(l["entry"]); sl=float(l["sl"]); tp=float(l["tp"]); direction=signal["signal"]
    for _,row in future.iterrows():
        high=float(row.high); low=float(row.low); ts=str(row.datetime); hit_sl=low<=sl if direction=="BUY" else high>=sl; hit_tp=high>=tp if direction=="BUY" else low<=tp
        if hit_sl and hit_tp:return {"result":"AMBIGUOUS","r_multiple":0.0,"resolved_at":ts}
        if hit_tp:return {"result":"WIN","r_multiple":round(abs(tp-entry)/abs(entry-sl),4),"resolved_at":ts}
        if hit_sl:return {"result":"LOSS","r_multiple":-1.0,"resolved_at":ts}
    return {"result":"OPEN","r_multiple":0.0}

def replay_frames(m5: pd.DataFrame, m15: pd.DataFrame, symbol: str, *, limit: int | None = None):
    m5=m5.sort_values("datetime").reset_index(drop=True); m15=m15.sort_values("datetime").reset_index(drop=True); rows=[]; start=max(60,len(m5)-limit) if limit else 60
    for i in range(start,len(m5)):
        ts=m5.iloc[i].datetime; context=m15[m15.datetime <= ts-timedelta(minutes=15)].reset_index(drop=True)
        setup=engine.analyze(m5.iloc[:i+1].reset_index(drop=True),context,symbol,i); outcome=resolve_outcome(setup,m5.iloc[i+1:i+1+engine.FORWARD_BARS])
        rows.append({"candle_time":str(ts),"signal":setup.get("signal","NO_TRADE"),"strategy":setup.get("strategy","NONE"),"valid":bool(setup.get("valid")),"trade_levels":setup.get("trade_levels"),"result":outcome["result"],"r_multiple":outcome["r_multiple"],"resolved_at":outcome.get("resolved_at"),"engine_version":engine.ENGINE_VERSION})
    decided=[r for r in rows if r["result"] in ("WIN","LOSS")]
    return {"status":"completed","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"candles_evaluated":len(rows),"signals":sum(r["valid"] for r in rows),"wins":sum(r["result"]=="WIN" for r in rows),"losses":sum(r["result"]=="LOSS" for r in rows),"ambiguous":sum(r["result"]=="AMBIGUOUS" for r in rows),"open":sum(r["result"]=="OPEN" for r in rows),"net_r":round(sum(r["r_multiple"] for r in decided),4),"rows":rows,"live_orders_allowed":False,"m15_policy":"CLOSED_AT_M5_CLOSE"}
