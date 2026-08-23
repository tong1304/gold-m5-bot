"""V9.1 historical paper backtest using the same LSE candles as live scanning.
No live orders are placed. The last closed M5 candle is the decision candle;
all higher-timeframe context is truncated at or before that timestamp.
"""
from __future__ import annotations
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
import pandas as pd

import engine_v9_1 as engine
from live_scanner_v9 import _lse_frame

FORWARD_BARS = max(1, int(os.getenv("FORWARD_BARS", "24")))


def _closed_context(df, ts):
    if df is None or df.empty:
        return df
    return df.loc[pd.to_datetime(df["datetime"], utc=True) <= ts].reset_index(drop=True)


def _stats(trades):
    wins=sum(1 for t in trades if t["result"]=="WIN")
    losses=sum(1 for t in trades if t["result"]=="LOSS")
    ambiguous=sum(1 for t in trades if t["result"]=="AMBIGUOUS")
    open_=sum(1 for t in trades if t["result"]=="OPEN")
    resolved=wins+losses+ambiguous
    win_rate=(wins/resolved*100) if resolved else 0.0
    gross_profit=sum(max(float(t.get("r",0)),0) for t in trades)
    gross_loss=abs(sum(min(float(t.get("r",0)),0) for t in trades))
    total_r=sum(float(t.get("r",0) or 0) for t in trades)
    curve=[]; equity=0.0; peak=0.0; max_dd=0.0
    for t in trades:
        r=t.get("r")
        if r is None: continue
        equity+=float(r); peak=max(peak,equity); max_dd=max(max_dd,peak-equity); curve.append(equity)
    return {"trades":len(trades),"wins":wins,"losses":losses,"ambiguous":ambiguous,"open":open_,"resolved":resolved,"win_rate_pct":round(win_rate,2),"profit_factor":round(gross_profit/gross_loss,3) if gross_loss else None,"total_r":round(total_r,3),"average_r":round(total_r/len(trades),3) if trades else 0.0,"max_drawdown_r":round(max_dd,3)}


def _run_symbol(symbol,bars=1000):
    m5=_lse_frame(symbol,"5m",bars)
    m15=_lse_frame(symbol,"15m",max(100,min(1000,bars//3+80)))
    h1=_lse_frame(symbol,"1h",max(100,min(1000,bars//12+80)))
    if len(m5)<150 or len(m15)<60 or len(h1)<60:
        raise RuntimeError(f"Insufficient data M5={len(m5)} M15={len(m15)} H1={len(h1)}")
    start=100
    end=len(m5)-FORWARD_BARS-1
    trades=[]; diagnostics=Counter(); reasons=Counter(); patterns=Counter()
    for i in range(start,end):
        diagnostics["candidate_candles"]+=1
        ts=pd.Timestamp(m5.iloc[i]["datetime"])
        m15_ctx=_closed_context(m15,ts)
        h1_ctx=_closed_context(h1,ts)
        if len(m15_ctx)<60 or len(h1_ctx)<60:
            reasons["INSUFFICIENT_CONTEXT"]+=1; continue
        try:
            setup=engine.analyze_structure_setup(m5,m15_ctx,h1_ctx,i)
            signal=setup.get("signal")
            if signal not in ("BUY","SELL") or not setup.get("valid"):
                for reason in setup.get("rejection_reasons") or ["NO_TRADE"]: reasons[str(reason)]+=1
                continue
            levels=setup.get("trade_levels") or {}
            if not levels.get("valid") or float(levels.get("risk_reward",0))<1.0:
                reasons["RR_BELOW_1R"]+=1; continue
            future=m5.iloc[i+1:i+1+FORWARD_BARS]
            result,r,when=engine.resolve_trade(signal,float(levels["entry"]),float(levels["sl"]),float(levels["tp"]),future)
            trade={"index":i,"closed_candle":str(ts),"direction":signal,"pattern":(setup.get("pattern") or {}).get("name"),"rr":float(levels.get("risk_reward",0)),"result":result,"r":r,"resolved_at":when}
            trades.append(trade); diagnostics["accepted_trades"]+=1; patterns[trade["pattern"] or "UNKNOWN"]+=1
        except Exception as exc:
            diagnostics["exceptions"]+=1; reasons[f"EXCEPTION_{type(exc).__name__}"]+=1
    by_side={s:_stats([t for t in trades if t["direction"]==s]) for s in ("BUY","SELL")}
    by_pattern={p:_stats([t for t in trades if t["pattern"]==p]) for p in sorted(patterns)}
    return {"symbol":symbol,"candles":{"M5":len(m5),"M15":len(m15),"H1":len(h1)},"data_start":str(m5.iloc[0]["datetime"]),"data_end":str(m5.iloc[-1]["datetime"]),"statistics":_stats(trades),"by_side":by_side,"by_pattern":by_pattern,"diagnostics":{**dict(diagnostics),"rejection_reasons":dict(reasons.most_common()),"pattern_counts":dict(patterns.most_common())},"trades":trades}


def run(symbol="BTC/USDT",bars=1000):
    started=time.monotonic(); symbol=symbol.strip().upper()
    mapped={"BTC/USDT":"BTC","BTC":"BTC","XAU/USDT":"GOLD","GOLD":"GOLD"}.get(symbol)
    if not mapped: return {"status":"error","message":"symbol must be BTC/USDT, BTC, XAU/USDT or GOLD"}
    try:
        report=_run_symbol(mapped,max(150,min(int(bars),1000)))
        report.update({"status":"PAPER_BACKTEST_V9_1","engine_version":engine.ENGINE_VERSION,"timeframe":"M5 trigger + M15 location + H1 structure","minimum_rr":1.0,"forward_bars":FORWARD_BARS,"generated_at":datetime.now(timezone.utc).isoformat(),"elapsed_seconds":round(time.monotonic()-started,3),"orders_placed":False,"live_orders_allowed":False,"method":"multi-candle pattern detection with last closed M5 candle as confirmation"})
        return report
    except Exception as exc:
        return {"status":"BACKTEST_FAILED","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"bars":bars,"error_type":type(exc).__name__,"message":str(exc),"elapsed_seconds":round(time.monotonic()-started,3),"live_orders_allowed":False}


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(); p.add_argument("--symbol",default="BTC/USDT"); p.add_argument("--bars",type=int,default=1000); a=p.parse_args()
    print(json.dumps(run(a.symbol,a.bars),ensure_ascii=False,default=str))
