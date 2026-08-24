from __future__ import annotations
import json,os
from datetime import timedelta
from pathlib import Path
import pandas as pd
from lse import LSE
from v11.replay_m5 import REPLAY_M5_CONTEXT_BARS,normalize_replay_window,replay_frames
START="2026-08-21";END="2026-08-24";SYMBOLS=("BTC","GOLD");OUT=Path("backtest_results.json")
def historical_m5(client,symbol,start,end):
    market={"BTC":"BTC/USD","GOLD":"XAU/USD"}[symbol];warmup=start-timedelta(minutes=5*REPLAY_M5_CONTEXT_BARS)
    frames=[];days=[];day=pd.Timestamp(warmup.date());last=pd.Timestamp((end-pd.Timedelta(nanoseconds=1)).date())
    while day<=last:
        api_start=day.date().isoformat();api_end=(day+pd.Timedelta(days=1)).date().isoformat()
        raw=client.candles(market,"5m",start=api_start,end=api_end,limit=1000,order="asc");rows=raw.get("data") if isinstance(raw,dict) else raw
        if isinstance(rows,dict):rows=rows.get("data") or rows.get("rows")
        if not isinstance(rows,(list,tuple)):raise RuntimeError(f"LSE_INVALID_RESPONSE:{symbol}:5m:{api_start}")
        frame=pd.DataFrame(rows)
        for candidate in ("timestamp","time","date"):
            if "datetime" not in frame.columns and candidate in frame.columns:frame=frame.rename(columns={candidate:"datetime"})
        required=("datetime","open","high","low","close");missing=[c for c in required if c not in frame.columns]
        if missing:raise RuntimeError(f"LSE_INVALID_RESPONSE:{symbol}:missing={missing}:day={api_start}")
        frame["datetime"]=pd.to_datetime(frame["datetime"],utc=True,errors="coerce")
        for c in required[1:]:frame[c]=pd.to_numeric(frame[c],errors="coerce")
        frame=frame.dropna(subset=list(required)).sort_values("datetime").drop_duplicates("datetime",keep="last").reset_index(drop=True);frames.append(frame);days.append(api_start);day+=pd.Timedelta(days=1)
    frame=pd.concat(frames,ignore_index=True).sort_values("datetime").drop_duplicates("datetime",keep="last").reset_index(drop=True)
    if len(frame)<REPLAY_M5_CONTEXT_BARS+1:raise RuntimeError(f"INSUFFICIENT_HISTORICAL_M5:{symbol}:{len(frame)}")
    target=frame[(frame["datetime"]>=start)&(frame["datetime"]<end)].copy()
    if target.empty:raise RuntimeError(f"NO_TARGET_HISTORICAL_M5:{symbol}")
    gaps=target["datetime"].diff().dropna()/pd.Timedelta(minutes=5)
    quality={"source":"LSE_HISTORICAL_M5_OHLCV","historical_rows":len(frame),"target_m5_rows":len(target),"first_target_candle":str(target.iloc[0].datetime),"last_target_candle":str(target.iloc[-1].datetime),"five_minute_gap_count":int((gaps>1).sum()),"warmup_bars":REPLAY_M5_CONTEXT_BARS,"api_start":days[0],"api_end":days[-1],"calendar_days_fetched":len(days)}
    return frame,quality
def main():
    start,end=normalize_replay_window(START,END);client=LSE(api_key=os.environ["LSE_API_KEY"]);reports=[];quality=[]
    for symbol in SYMBOLS:
        frame,q=historical_m5(client,symbol,start,end);report=replay_frames(frame,None,symbol,start_time=start,end_time=end);report["data_quality"]=q;quality.append({"symbol":symbol,**q});reports.append({"symbol":symbol,"engine_version":report.get("engine_version"),"candles_evaluated":report.get("candles_evaluated"),"signals":report.get("signals"),"wins":report.get("wins"),"losses":report.get("losses"),"ambiguous":report.get("ambiguous"),"open":report.get("open"),"net_r":report.get("net_r"),"performance":report.get("performance"),"data_quality":q,"trade_history":report.get("trade_history",[])})
    payload={"status":"completed","engine_version":reports[0]["engine_version"] if reports else None,"engine_name":"REGIME-8-ENGINE-REENTRY","source":"LSE_HISTORICAL_M5_OHLCV","timeframe_mode":"M5-only","lookahead_safe":True,"warmup_bars":REPLAY_M5_CONTEXT_BARS,"start":str(start),"end":str(end),"requested_window":{"start":START,"end":END},"symbols":list(SYMBOLS),"data_quality":quality,"reports":reports}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,default=str,indent=2),encoding="utf-8")
    print(json.dumps({"status":payload["status"],"start":payload["start"],"end":payload["end"],"data_quality":quality,"reports":[{k:r[k] for k in ("symbol","candles_evaluated","signals","wins","losses","net_r")} for r in reports]},ensure_ascii=False))
if __name__=="__main__":main()
