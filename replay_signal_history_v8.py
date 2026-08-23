"""Historical Replay for the same standalone V8 engine used live."""
from __future__ import annotations
import argparse,json,os
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import engine_v8 as engine
from signal_history import history

BANGKOK=ZoneInfo("Asia/Bangkok")
SYMBOLS={"BTC":"BTC/USD","GOLD":"XAU/USD"}


def _bounds(start_text,end_text):
    start=datetime.fromisoformat(start_text).replace(tzinfo=BANGKOK)
    end=datetime.fromisoformat(end_text).replace(tzinfo=BANGKOK)+timedelta(days=1)
    return start.astimezone(timezone.utc),end.astimezone(timezone.utc)


def _normalize(raw):
    if isinstance(raw,pd.DataFrame): df=raw.copy()
    elif isinstance(raw,dict): df=pd.DataFrame(raw.get("data") or raw.get("rows") or raw.get("candles") or [])
    else: df=pd.DataFrame(raw or [])
    if df.empty: return df
    time_col=next((c for c in ("datetime","timestamp","time","ts") if c in df.columns),None)
    if not time_col: raise RuntimeError("LSE response has no timestamp field")
    df["datetime"]=pd.to_datetime(df[time_col],utc=True,errors="coerce")
    df=df.rename(columns={k:v for k,v in {"o":"open","h":"high","l":"low","c":"close","v":"volume"}.items() if k in df.columns})
    for col in ("open","high","low","close","volume"):
        if col not in df.columns: df[col]=0.0
        df[col]=pd.to_numeric(df[col],errors="coerce")
    return df.dropna(subset=["datetime","open","high","low","close"])[["datetime","open","high","low","close","volume"]].sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)


def _fetch_lse(symbol,start,end,timeframe="5m",chunk_days=6):
    key=os.getenv("LSE_API_KEY","").strip() or os.getenv("LSE_KEY","").strip()
    if not key: raise RuntimeError("LSE_API_KEY/LSE_KEY is not configured")
    from lse import LSE
    client=LSE(api_key=key); parts=[]; cursor=start
    while cursor<end:
        chunk_end=min(cursor+timedelta(days=chunk_days),end)
        raw=client.candles(symbol,timeframe,start=cursor.date().isoformat(),end=chunk_end.date().isoformat())
        frame=_normalize(raw)
        if not frame.empty: parts.append(frame)
        cursor=chunk_end
    if not parts: raise RuntimeError(f"LSE returned no {timeframe} candles for {symbol}")
    return pd.concat(parts,ignore_index=True).sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)


def _resample(m5,minutes):
    return (m5.set_index("datetime")[["open","high","low","close","volume"]].resample(f"{minutes}min",label="left",closed="left").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna(subset=["open","high","low","close"]).reset_index())


def _context(frame,ts): return frame[frame["datetime"]<=pd.Timestamp(ts)].reset_index(drop=True)


def _resolve(direction,entry,sl,tp,future):
    risk=abs(entry-sl); rr=abs(tp-entry)/risk if risk else 0
    for _,c in future.iterrows():
        high,low=float(c.high),float(c.low); hit_sl=low<=sl if direction=="BUY" else high>=sl; hit_tp=high>=tp if direction=="BUY" else low<=tp
        when=str(c.datetime)
        if hit_sl and hit_tp:return "AMBIGUOUS",0.0,when
        if hit_tp:return "WIN",rr,when
        if hit_sl:return "LOSS",-1.0,when
    return "OPEN",None,None


def replay_symbol(symbol,start,end,dry_run=False):
    market=SYMBOLS[symbol]; m5=_fetch_lse(market,start-timedelta(days=7),end,"5m",6)
    if len(m5)<500: raise RuntimeError(f"Not enough LSE M5 history for {symbol}: {len(m5)}")
    m15,h1=_resample(m5,15),_resample(m5,60); generated=inserted=0; outcomes={"WIN":0,"LOSS":0,"AMBIGUOUS":0,"OPEN":0,"NO_TRADE":0}; rejected={}; used=set()
    for i in range(100,len(m5)-1):
        ts=pd.Timestamp(m5.iloc[i].datetime)
        if ts<pd.Timestamp(start) or ts>=pd.Timestamp(end): continue
        m5c=m5.iloc[:i+1].reset_index(drop=True); m15c=_context(m15,ts); h1c=_context(h1,ts)
        if len(m15c)<60 or len(h1c)<60: continue
        setup=engine.analyze_structure_setup(m5c,m15c,h1c,len(m5c)-1); signal=setup.get("signal"); valid=signal in ("BUY","SELL") and setup.get("valid")
        if not valid or (setup.get("setup_key") and setup.get("setup_key") in used):
            reason=setup.get("rejection_reasons",[]) if not valid else ["DUPLICATE_SETUP"]
            for r in reason: rejected[r]=rejected.get(r,0)+1
            sid=f"REPLAY-V8-{symbol}-{ts.strftime('%Y%m%dT%H%MZ')}-NO_TRADE"; payload={"signal_id":sid,"symbol":symbol,"signal":"NO_TRADE","closed_candle":ts.isoformat(),"created_at":ts.isoformat(),"replay":True,"replay_source":"LSE_HISTORICAL_OHLCV","engine_version":engine.ENGINE_VERSION,"v8_setup":setup,"rejection_reasons":reason,"no_trade_reasons":reason}
            generated+=1; outcomes["NO_TRADE"]+=1
            if not dry_run and history.record_no_trade(payload): inserted+=1
            continue
        used.add(setup.get("setup_key")); levels=setup["trade_levels"]; sid=f"REPLAY-V8-{symbol}-{ts.strftime('%Y%m%dT%H%MZ')}-{signal}"; payload={"signal_id":sid,"symbol":symbol,"signal":signal,"closed_candle":ts.isoformat(),"created_at":ts.isoformat(),"replay":True,"replay_source":"LSE_HISTORICAL_OHLCV","engine_version":engine.ENGINE_VERSION,"pattern_signal":signal,"m5_direction":signal,"v8_setup":setup,"trade_levels":levels,"rejection_reasons":setup.get("rejection_reasons",[])}
        result,r,when=_resolve(signal,levels["entry"],levels["sl"],levels["tp"],m5.iloc[i+1:i+1+int(engine.FORWARD_BARS)+1]); generated+=1; outcomes[result]+=1
        if not dry_run:
            if history.record_signal(payload): inserted+=1
            if result!="OPEN": history.set_result(sid,result,r,when)
    return {"symbol":symbol,"engine_version":engine.ENGINE_VERSION,"provider":"LSE","generated":generated,"inserted":inserted,"outcomes":outcomes,"rejected":dict(sorted(rejected.items(),key=lambda x:x[1],reverse=True)[:15])}


def main():
    p=argparse.ArgumentParser(); p.add_argument("--start",required=True); p.add_argument("--end",required=True); p.add_argument("--symbol",choices=["BTC","GOLD","ALL"],default="ALL"); p.add_argument("--dry-run",action="store_true"); a=p.parse_args(); start,end=_bounds(a.start,a.end); symbols=["BTC","GOLD"] if a.symbol=="ALL" else [a.symbol]; results=[replay_symbol(s,start,end,a.dry_run) for s in symbols]; print(json.dumps({"status":"dry-run" if a.dry_run else "completed","engine_version":engine.ENGINE_VERSION,"provider":"LSE","start":a.start,"end":a.end,"results":results},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
