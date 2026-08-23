"""V10.3 historical replay: M15 context + M5 setup/trigger, no H1.
Uses the same strategy_engine and engine_v9_2 as live. Replay is dry with respect
to Telegram/orders, but persists historical outcomes to SignalHistory.
"""
from __future__ import annotations
import argparse, json, os
from datetime import datetime, timezone, timedelta
import pandas as pd
from zoneinfo import ZoneInfo
from lse import LSE
import engine_v9_2 as engine
import strategy_engine
from signal_history import history

BANGKOK=ZoneInfo("Asia/Bangkok")
SYMBOLS={"BTC":"BTC/USD","GOLD":"XAU/USD"}

def _bounds(a,b):
    s=datetime.fromisoformat(a).replace(tzinfo=BANGKOK)
    e=datetime.fromisoformat(b).replace(tzinfo=BANGKOK)+timedelta(days=1)
    return s.astimezone(timezone.utc),e.astimezone(timezone.utc)

def _normalize(raw):
    rows=raw.get("data") if isinstance(raw,dict) else raw
    if isinstance(rows,dict): rows=rows.get("data") or rows.get("rows") or rows.get("candles")
    df=pd.DataFrame(rows or [])
    if df.empty:return df
    if "datetime" not in df.columns:
        for c in ("timestamp","time","date","ts"):
            if c in df.columns: df=df.rename(columns={c:"datetime"}); break
    df=df.rename(columns={k:v for k,v in {"o":"open","h":"high","l":"low","c":"close","v":"volume"}.items() if k in df.columns})
    required=["datetime","open","high","low","close"]
    missing=[c for c in required if c not in df.columns]
    if missing:raise RuntimeError(f"LSE response missing columns: {missing}")
    if "volume" not in df.columns:df["volume"]=0.0
    df["datetime"]=pd.to_datetime(df["datetime"],utc=True,errors="coerce")
    for c in ("open","high","low","close","volume"):df[c]=pd.to_numeric(df[c],errors="coerce")
    return df.dropna(subset=required).sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)

def _fetch(symbol,start,end,timeframe="5m",chunk_days=6):
    key=os.getenv("LSE_API_KEY","").strip() or os.getenv("LSE_KEY","").strip()
    if not key:raise RuntimeError("LSE_API_KEY/LSE_KEY is not configured")
    client=LSE(api_key=key); parts=[]; cursor=start
    while cursor<end:
        ce=min(cursor+timedelta(days=chunk_days),end)
        raw=client.candles(SYMBOLS[symbol],timeframe,start=cursor.date().isoformat(),end=ce.date().isoformat(),limit=200,order="desc")
        frame=_normalize(raw)
        if not frame.empty:parts.append(frame)
        cursor=ce
    if not parts:raise RuntimeError(f"LSE returned no {timeframe} candles for {symbol}")
    return pd.concat(parts,ignore_index=True).sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)

def _resample(m5,minutes):
    return (m5.set_index("datetime")[["open","high","low","close","volume"]].resample(f"{minutes}min",label="left",closed="left").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna(subset=["open","high","low","close"]).reset_index())

def _context(frame,ts):return frame[frame.datetime<=pd.Timestamp(ts)].reset_index(drop=True)

def _resolve(direction,entry,sl,tp,future):
    risk=abs(entry-sl); rr=abs(tp-entry)/risk if risk else 0.0
    for _,c in future.iterrows():
        hi,lo=float(c.high),float(c.low); hs=lo<=sl if direction=="BUY" else hi>=sl; ht=hi>=tp if direction=="BUY" else lo<=tp
        if hs and ht:return "AMBIGUOUS",0.0,str(c.datetime)
        if ht:return "WIN",rr,str(c.datetime)
        if hs:return "LOSS",-1.0,str(c.datetime)
    return "OPEN",None,None

def replay_symbol(symbol,start,end,dry_run=False):
    m5=_fetch(symbol,start-timedelta(days=14),end,"5m",6); m15=_resample(m5,15)
    if len(m5)<150 or len(m15)<100:raise RuntimeError(f"Not enough history for {symbol}: M5={len(m5)} M15={len(m15)}")
    outcomes={"WIN":0,"LOSS":0,"AMBIGUOUS":0,"OPEN":0,"NO_TRADE":0}; rejected={}; strategy_stats={}; generated=inserted=0
    forward=int(getattr(engine,"FORWARD_BARS",12)); start_ts,end_ts=pd.Timestamp(start),pd.Timestamp(end)
    engine.MIN_RISK_REWARD=1.0; engine.RISK_REWARD=max(float(os.getenv("RISK_REWARD","1.0")),1.0)
    for i in range(100,len(m5)-1):
        ts=pd.Timestamp(m5.iloc[i].datetime)
        if ts<start_ts or ts>=end_ts:continue
        m5c=m5.iloc[:i+1].reset_index(drop=True); m15c=_context(m15,ts)
        if len(m15c)<100:continue
        evaluation=strategy_engine.analyze(m5c,m15c,symbol=symbol)
        candidates=evaluation.get("strategy_candidates") or []
        for c in candidates:
            name=c.get("strategy","UNKNOWN"); st=strategy_stats.setdefault(name,{"evaluated":0,"pass":0,"fail":0,"not_applicable":0,"wins":0,"losses":0,"open":0,"ambiguous":0,"no_trade":0,"reasons":{}})
            st["evaluated"]+=1; status=c.get("status","FAIL").lower(); st[status if status in ("pass","fail","not_applicable") else "fail"]+=1
            for r in c.get("reason") or []:st["reasons"][r]=st["reasons"].get(r,0)+1
        setup=engine.analyze_structure_setup(m5c,m15c,len(m5c)-1)
        setup.update({"candle_time":ts.isoformat(),"closed_candle":ts.isoformat(),"symbol":symbol,"engine_version":engine.ENGINE_VERSION,"strategy_candidates":candidates,"replay":True,"replay_source":"LSE_HISTORICAL_OHLCV_V10.3"})
        signal=setup.get("signal"); levels=setup.get("trade_levels") or {}; rr=float(levels.get("effective_rr",levels.get("risk_reward",0)) or 0); valid=signal in ("BUY","SELL") and bool(levels.get("valid")) and rr>=1.0
        setup["valid"]=valid
        if not valid:
            reasons=setup.get("rejection_reasons") or ["NO_TRADE_REASON_UNSPECIFIED"]
            for r in reasons:rejected[r]=rejected.get(r,0)+1
            outcomes["NO_TRADE"]+=1; generated+=1
            sid=f"REPLAY-V103-{symbol}-{ts.strftime('%Y%m%dT%H%MZ')}-NO_TRADE"
            payload={**setup,"signal_id":sid,"signal":"NO_TRADE","result":"NO_TRADE","created_at":ts.isoformat(),"no_trade_reasons":reasons}
            if not dry_run and history.record_no_trade(payload):inserted+=1
            continue
        generated+=1
        sid=f"REPLAY-V103-{symbol}-{ts.strftime('%Y%m%dT%H%MZ')}-{signal}"
        payload={**setup,"signal_id":sid,"signal":signal,"created_at":ts.isoformat(),"pattern_signal":signal,"m5_direction":signal}
        result,r,when=_resolve(signal,float(levels["entry"]),float(levels["sl"]),float(levels["tp"]),m5.iloc[i+1:i+1+forward+1]); outcomes[result]+=1
        st=strategy_stats.setdefault(setup.get("strategy","NONE"),{"evaluated":0,"pass":0,"fail":0,"not_applicable":0,"wins":0,"losses":0,"open":0,"ambiguous":0,"no_trade":0,"reasons":{}})
        st[{"WIN":"wins","LOSS":"losses","OPEN":"open","AMBIGUOUS":"ambiguous"}.get(result,"no_trade")]+=1
        if not dry_run:
            if history.record_signal(payload):inserted+=1
            if result!="OPEN":history.set_result(sid,result,r,when)
    return {"symbol":symbol,"engine_version":engine.ENGINE_VERSION,"provider":"LSE","generated":generated,"inserted":inserted,"outcomes":outcomes,"rejected":dict(sorted(rejected.items(),key=lambda x:x[1],reverse=True)[:30]),"strategy_stats":strategy_stats}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--start",required=True); p.add_argument("--end",required=True); p.add_argument("--symbol",choices=["BTC","GOLD","ALL"],default="ALL"); p.add_argument("--dry-run",action="store_true"); a=p.parse_args(); start,end=_bounds(a.start,a.end); results=[]
    for s in (["BTC","GOLD"] if a.symbol=="ALL" else [a.symbol]):
        try:results.append(replay_symbol(s,start,end,a.dry_run))
        except Exception as exc:results.append({"symbol":s,"engine_version":engine.ENGINE_VERSION,"status":"failed","error":f"{type(exc).__name__}: {exc}"})
    status="completed" if all(r.get("status")!="failed" for r in results) else "failed"
    print(json.dumps({"status":"dry-run" if a.dry_run and status=="completed" else status,"engine_version":engine.ENGINE_VERSION,"provider":"LSE","start":a.start,"end":a.end,"results":results},ensure_ascii=False,separators=(",",":")))

if __name__=="__main__":main()
