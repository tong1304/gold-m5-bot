from __future__ import annotations
from datetime import timedelta
from typing import Callable
import pandas as pd
from . import engine
from .setup_state import SetupState
REPLAY_M5_CONTEXT_BARS=100;REPLAY_M15_CONTEXT_BARS=100

def _timestamp(value):
    if value is None or value=="":return None
    ts=pd.Timestamp(value);return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
def _bounded_context(frame,end_position,max_bars):
    end_position=max(0,min(int(end_position),len(frame)));return frame.iloc[max(0,end_position-max_bars):end_position].reset_index(drop=True)
def _m15_context_end_positions(m5,m15):
    times=pd.DatetimeIndex(m15["datetime"]);return [int(times.searchsorted(ts-timedelta(minutes=15),side="right")) for ts in m5["datetime"]]
def _resolve_trade(trade,candle):
    high=float(candle.high);low=float(candle.low);direction=trade["signal"];levels=trade["trade_levels"];entry=float(levels["entry"]);sl=float(levels["sl"]);tp=float(levels["tp"]);hit_sl=low<=sl if direction=="BUY" else high>=sl;hit_tp=high>=tp if direction=="BUY" else low<=tp
    if hit_sl and hit_tp:return {"result":"AMBIGUOUS","r_multiple":0.0,"resolved_at":str(candle.datetime)}
    if hit_tp:return {"result":"WIN","r_multiple":round(abs(tp-entry)/abs(entry-sl),4),"resolved_at":str(candle.datetime)}
    if hit_sl:return {"result":"LOSS","r_multiple":-1.0,"resolved_at":str(candle.datetime)}
    return None
def _pct(n,d):return round(100*n/d,2) if d else 0.0
def _max_drawdown(values):
    equity=peak=drawdown=0.0
    for value in values:equity+=float(value);peak=max(peak,equity);drawdown=max(drawdown,peak-equity)
    return round(drawdown,4)
def summarize_rows(rows):
    wins=sum(r.get("result")=="WIN" for r in rows);losses=sum(r.get("result")=="LOSS" for r in rows);open_=sum(r.get("result")=="OPEN" for r in rows);amb=sum(r.get("result")=="AMBIGUOUS" for r in rows);no_trade=sum(r.get("result")=="NO_TRADE" for r in rows);rs=[float(r.get("r_multiple") or 0) for r in rows if r.get("result") in ("WIN","LOSS")];decided=wins+losses;gross_profit=sum(r for r in rs if r>0);gross_loss=abs(sum(r for r in rs if r<0));net=sum(rs);strategies={}
    for r in rows:
        name=str(r.get("strategy") or "NONE");s=strategies.setdefault(name,{"evaluated":0,"trades":0,"wins":0,"losses":0,"open":0,"ambiguous":0,"no_trade":0,"net_r":0.0});s["evaluated"]+=1;result=r.get("result")
        if result=="NO_TRADE":s["no_trade"]+=1
        else:s["trades"]+=1
        if result=="WIN":s["wins"]+=1
        elif result=="LOSS":s["losses"]+=1
        elif result=="OPEN":s["open"]+=1
        elif result=="AMBIGUOUS":s["ambiguous"]+=1
        if result in ("WIN","LOSS"):s["net_r"]+=float(r.get("r_multiple") or 0)
    for s in strategies.values():
        d=s["wins"]+s["losses"];s["net_r"]=round(s["net_r"],4);s["win_rate"]=_pct(s["wins"],d);s["expectancy_r"]=round(s["net_r"]/d,4) if d else 0.0
    return {"rows":len(rows),"trades":decided+open_+amb,"decided":decided,"wins":wins,"losses":losses,"open":open_,"ambiguous":amb,"no_trade":no_trade,"win_rate":_pct(wins,decided),"loss_rate":_pct(losses,decided),"net_r":round(net,4),"gross_profit_r":round(gross_profit,4),"gross_loss_r":round(gross_loss,4),"profit_factor":round(gross_profit/gross_loss,4) if gross_loss else None,"expectancy_r":round(net/decided,4) if decided else 0.0,"max_drawdown_r":_max_drawdown(rs),"strategies":strategies}

def replay_frames(m5,m15,symbol,*,limit=None,start_time=None,end_time=None,progress_callback:Callable[...,None]|None=None):
    m5=m5.sort_values("datetime").reset_index(drop=True);m15=m15.sort_values("datetime").reset_index(drop=True);start_ts,end_ts=_timestamp(start_time),_timestamp(end_time);indices=list(range(60,len(m5)))
    if start_ts is not None:indices=[i for i in indices if pd.Timestamp(m5.iloc[i].datetime)>=start_ts]
    if end_ts is not None:indices=[i for i in indices if pd.Timestamp(m5.iloc[i].datetime)<end_ts]
    if limit:indices=indices[-int(limit):]
    context_ends=_m15_context_end_positions(m5,m15);rows=[];trades=[];active=[];state=SetupState();total=len(indices)
    if progress_callback:progress_callback("engine_progress",symbol=symbol,completed=0,total=total,percent=0,trades=0,wins=0,losses=0,open=0,ambiguous=0,net_r=0.0)
    for n,i in enumerate(indices,start=1):
        candle=m5.iloc[i];ts=candle.datetime;still=[]
        for trade in active:
            outcome=_resolve_trade(trade,candle)
            if outcome:
                trade.update(outcome)
                for row in reversed(trades):
                    if row.get("signal_id")==trade.get("signal_id"):row.update(outcome);break
            else:still.append(trade)
        active=still;m5_context=_bounded_context(m5,i+1,REPLAY_M5_CONTEXT_BARS);m15_context=_bounded_context(m15,context_ends[i],REPLAY_M15_CONTEXT_BARS);setup=engine.analyze(m5_context,m15_context,symbol,setup_state=state);setup.update({"candle_time":str(ts),"closed_candle":str(ts),"symbol":symbol,"engine_version":engine.ENGINE_VERSION});signal=setup.get("signal");valid=bool(setup.get("valid")) and signal in ("BUY","SELL") and bool((setup.get("trade_levels") or {}).get("valid"))
        if valid:
            setup_id=setup.get("setup_id");different_active=any(t.get("setup_id")!=setup_id for t in active)
            if different_active:row={**setup,"signal":"NO_TRADE","valid":False,"result":"NO_TRADE","lock_reason":"DIFFERENT_SETUP_ACTIVE"}
            else:
                signal_id=f"REPLAY-{symbol}-{pd.Timestamp(ts).strftime('%Y%m%dT%H%M%SZ')}-{signal}-{setup.get('trigger_id','NONE')}";trade={"signal":signal,"strategy":setup.get("strategy"),"engine":setup.get("engine"),"trade_levels":setup["trade_levels"],"setup_id":setup_id,"trigger_id":setup.get("trigger_id"),"signal_id":signal_id,"result":"OPEN","r_multiple":0.0,"resolved_at":None};active.append(trade);trades.append({**setup,"signal_id":signal_id,"result":"OPEN","r_multiple":0.0,"resolved_at":None});state.record(setup_id,setup.get("trigger_id"));row=trades[-1]
        else:row={**setup,"signal":"NO_TRADE","result":"NO_TRADE","r_multiple":0.0,"lock_reason":None}
        rows.append(row);decided=[t for t in trades if t.get("result") in ("WIN","LOSS")];wins=sum(t.get("result")=="WIN" for t in trades);losses=sum(t.get("result")=="LOSS" for t in trades);opens=sum(t.get("result")=="OPEN" for t in trades);amb=sum(t.get("result")=="AMBIGUOUS" for t in trades);net=sum(float(t.get("r_multiple") or 0) for t in decided)
        if progress_callback and (n==total or n==1 or n%10==0):progress_callback("engine_progress",symbol=symbol,completed=n,total=total,percent=round(100*n/total,1) if total else 100,trades=len(trades),wins=wins,losses=losses,open=opens,ambiguous=amb,net_r=round(net,4))
    performance=summarize_rows(trades);evaluated=summarize_rows(rows);return {"status":"completed","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"candles_evaluated":len(rows),"signals":len(trades),"wins":performance["wins"],"losses":performance["losses"],"ambiguous":performance["ambiguous"],"open":performance["open"],"net_r":performance["net_r"],"performance":{**performance,"evaluated_rows":evaluated["rows"],"locked_rows":sum(1 for r in rows if r.get("lock_reason"))},"rows":rows,"trade_history":trades,"live_orders_allowed":False,"m15_policy":"CLOSED_AT_M5_CLOSE_MINUS_15M","lookahead_safe":True,"warmup_bars":60,"setup_reentry_policy":"SAME_SETUP_NEW_TRIGGER_ALLOWED_WITH_CONFIGURED_LIMIT"}
