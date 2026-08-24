from __future__ import annotations

from datetime import timedelta
from typing import Callable

import pandas as pd

from . import engine

REPLAY_M5_CONTEXT_BARS = 100
REPLAY_M15_CONTEXT_BARS = 100


def _setup_key(setup: dict) -> str:
    ev = setup.get("selected_strategy", {}).get("evidence") or {}
    anchor = ev.get("setup_anchor", ev.get("breakout_level", ev.get("sweep_level", ev.get("vwap", ""))))
    try:
        anchor = f"{float(anchor):.8f}"
    except (TypeError, ValueError):
        anchor = str(anchor)
    return f"{setup.get('symbol')}|{setup.get('strategy')}|{setup.get('signal')}|{anchor}"


def _flatten_trade(row: dict) -> dict:
    levels = row.get("trade_levels") or {}
    return {"candle_time":row.get("candle_time"),"symbol":row.get("symbol"),"signal":row.get("signal"),"strategy":row.get("strategy"),"valid":bool(row.get("valid")),"entry":levels.get("entry"),"sl":levels.get("sl"),"tp":levels.get("tp"),"tp1":levels.get("tp1",levels.get("tp")),"tp2":levels.get("tp2"),"tp3":levels.get("tp3"),"rr":levels.get("risk_reward",levels.get("effective_rr")),"risk_reward":levels.get("risk_reward",levels.get("effective_rr")),"trade_levels":levels,"setup_key":row.get("setup_key"),"signal_id":row.get("signal_id"),"result":row.get("result"),"r_multiple":row.get("r_multiple",0.0),"resolved_at":row.get("resolved_at"),"engine_version":row.get("engine_version")}


def _resolve_active(active: dict, candle: pd.Series) -> dict | None:
    high=float(candle.high); low=float(candle.low); direction=active["signal"]; levels=active["trade_levels"]; entry=float(levels["entry"]); sl=float(levels["sl"]); tp=float(levels["tp"])
    hit_sl=low<=sl if direction=="BUY" else high>=sl; hit_tp=high>=tp if direction=="BUY" else low<=tp
    if hit_sl and hit_tp:return {"result":"AMBIGUOUS","r_multiple":0.0,"resolved_at":str(candle.datetime)}
    if hit_tp:return {"result":"WIN","r_multiple":round(abs(tp-entry)/abs(entry-sl),4),"resolved_at":str(candle.datetime)}
    if hit_sl:return {"result":"LOSS","r_multiple":-1.0,"resolved_at":str(candle.datetime)}
    return None


def resolve_outcome(signal: dict, future: pd.DataFrame):
    if signal.get("signal") not in ("BUY","SELL"):return {"result":"NO_TRADE","r_multiple":0.0}
    for _,row in future.iterrows():
        outcome=_resolve_active(signal,row)
        if outcome:return outcome
    return {"result":"OPEN","r_multiple":0.0}


def _pct(numerator:int,denominator:int)->float:return round(100.0*numerator/denominator,2) if denominator else 0.0


def _max_drawdown(values:list[float])->float:
    equity=peak=max_dd=0.0
    for value in values:
        equity+=float(value);peak=max(peak,equity);max_dd=max(max_dd,peak-equity)
    return round(max_dd,4)


def summarize_rows(rows:list[dict])->dict:
    counts={key:0 for key in ("WIN","LOSS","OPEN","AMBIGUOUS","NO_TRADE")};decided_r=[];strategies={}
    for row in rows:
        result=str(row.get("result") or "NO_TRADE").upper();result=result if result in counts else "NO_TRADE";counts[result]+=1;strategy=str(row.get("strategy") or "NONE")
        s=strategies.setdefault(strategy,{"evaluated":0,"trades":0,"wins":0,"losses":0,"open":0,"ambiguous":0,"no_trade":0,"net_r":0.0});s["evaluated"]+=1
        if result=="NO_TRADE":s["no_trade"]+=1
        else:s["trades"]+=1
        if result=="WIN":s["wins"]+=1
        elif result=="LOSS":s["losses"]+=1
        elif result=="OPEN":s["open"]+=1
        elif result=="AMBIGUOUS":s["ambiguous"]+=1
        r=float(row.get("r_multiple") or 0.0)
        if result in ("WIN","LOSS"):decided_r.append(r);s["net_r"]+=r
    wins,losses=counts["WIN"],counts["LOSS"];decided=wins+losses;trades=decided+counts["OPEN"]+counts["AMBIGUOUS"];gross_profit=round(sum(r for r in decided_r if r>0),4);gross_loss=round(abs(sum(r for r in decided_r if r<0)),4);net_r=round(sum(decided_r),4)
    for s in strategies.values():
        s["net_r"]=round(s["net_r"],4);d=s["wins"]+s["losses"];s["win_rate"]=_pct(s["wins"],d);s["expectancy_r"]=round(s["net_r"]/d,4) if d else 0.0
    return {"rows":len(rows),"trades":trades,"decided":decided,"wins":wins,"losses":losses,"open":counts["OPEN"],"ambiguous":counts["AMBIGUOUS"],"no_trade":counts["NO_TRADE"],"win_rate":_pct(wins,decided),"loss_rate":_pct(losses,decided),"net_r":net_r,"gross_profit_r":gross_profit,"gross_loss_r":gross_loss,"profit_factor":round(gross_profit/gross_loss,4) if gross_loss else None,"expectancy_r":round(net_r/decided,4) if decided else 0.0,"max_drawdown_r":_max_drawdown(decided_r),"strategies":strategies}


def _timestamp(value):
    if value is None or value=="":return None
    ts=pd.Timestamp(value);return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _m15_context_end_positions(m5:pd.DataFrame,m15:pd.DataFrame)->list[int]:
    m15_times=pd.DatetimeIndex(m15["datetime"]);return [int(m15_times.searchsorted(ts-timedelta(minutes=15),side="right")) for ts in m5["datetime"]]


def _bounded_context(frame:pd.DataFrame,end_position:int,max_bars:int)->pd.DataFrame:
    end_position=max(0,min(int(end_position),len(frame)));return frame.iloc[max(0,end_position-max_bars):end_position].reset_index(drop=True)


def replay_frames(m5:pd.DataFrame,m15:pd.DataFrame,symbol:str,*,limit:int|None=None,start_time=None,end_time=None,progress_callback:Callable[...,None]|None=None):
    """Chronological replay with Live-equivalent active-signal and setup locks."""
    m5=m5.sort_values("datetime").reset_index(drop=True);m15=m15.sort_values("datetime").reset_index(drop=True);start_ts,end_ts=_timestamp(start_time),_timestamp(end_time);indices=list(range(60,len(m5)))
    if start_ts is not None:indices=[i for i in indices if pd.Timestamp(m5.iloc[i].datetime)>=start_ts]
    if end_ts is not None:indices=[i for i in indices if pd.Timestamp(m5.iloc[i].datetime)<end_ts]
    if limit:indices=indices[-limit:]
    context_ends=_m15_context_end_positions(m5,m15);rows=[];trade_history=[];total=len(indices);active=None;last_closed_setup_key=None
    if progress_callback:progress_callback("engine_progress",symbol=symbol,completed=0,total=total,percent=0,trades=0,wins=0,losses=0,open=0,ambiguous=0,net_r=0.0)
    for n,i in enumerate(indices,start=1):
        candle=m5.iloc[i];ts=candle.datetime
        if active:
            outcome=_resolve_active(active,candle)
            if outcome:
                active.update(outcome)
                for row in reversed(trade_history):
                    if row.get("signal_id")==active.get("signal_id"):
                        row.update(outcome);break
                active=None;last_closed_setup_key=active.get("setup_key")
        if active:
            rows.append({"candle_time":str(ts),"symbol":symbol,"signal":"NO_TRADE","strategy":active.get("strategy","ACTIVE_LOCK"),"valid":False,"trade_levels":None,"result":"NO_TRADE","r_multiple":0.0,"resolved_at":None,"setup_key":active.get("setup_key"),"signal_id":None,"engine_version":engine.ENGINE_VERSION,"lock_reason":"ACTIVE_SIGNAL_LOCK"})
        else:
            m5_context=_bounded_context(m5,i+1,REPLAY_M5_CONTEXT_BARS);m15_context=_bounded_context(m15,context_ends[i],REPLAY_M15_CONTEXT_BARS);setup=engine.analyze(m5_context,m15=m15_context,symbol=symbol,index=None);setup.update({"candle_time":str(ts),"closed_candle":str(ts),"symbol":symbol,"engine_version":engine.ENGINE_VERSION});signal=setup.get("signal");levels=setup.get("trade_levels") or {};valid=bool(setup.get("valid")) and signal in ("BUY","SELL") and bool(levels.get("valid")) and float(levels.get("risk_reward",levels.get("effective_rr",0)) or 0)>=2.0;setup["valid"]=valid
            if valid:
                setup["setup_key"]=_setup_key(setup)
                if last_closed_setup_key and setup["setup_key"]==last_closed_setup_key:
                    rows.append({**setup,"signal":"NO_TRADE","valid":False,"result":"NO_TRADE","r_multiple":0.0,"resolved_at":None,"lock_reason":"SAME_SETUP_AFTER_PREVIOUS_SIGNAL"})
                else:
                    signal_id=f"REPLAY-{symbol}-{ts.strftime('%Y%m%dT%H%M%SZ')}-{signal}";setup["signal_id"]=signal_id;active={"signal":signal,"strategy":setup.get("strategy","NONE"),"trade_levels":levels,"setup_key":setup["setup_key"],"signal_id":signal_id};trade=_flatten_trade({**setup,"result":"OPEN","r_multiple":0.0,"resolved_at":None,"symbol":symbol});trade_history.append(trade);rows.append({**setup,"result":"OPEN","r_multiple":0.0,"resolved_at":None})
            else:rows.append({**setup,"signal":"NO_TRADE" if signal not in ("BUY","SELL") else signal,"result":"NO_TRADE","r_multiple":0.0,"resolved_at":None,"lock_reason":None})
        # Refresh trade-history outcome counts from the actual trade records.
        decided=[t for t in trade_history if t.get("result") in ("WIN","LOSS")];wins=sum(t.get("result")=="WIN" for t in trade_history);losses=sum(t.get("result")=="LOSS" for t in trade_history);opens=sum(t.get("result")=="OPEN" for t in trade_history);amb=sum(t.get("result")=="AMBIGUOUS" for t in trade_history);net=round(sum(float(t.get("r_multiple") or 0) for t in decided),4)
        if progress_callback and (n==total or n==1 or n%10==0):progress_callback("engine_progress",symbol=symbol,completed=n,total=total,percent=round(100*n/total,1) if total else 100,trades=len(trade_history),wins=wins,losses=losses,open=opens,ambiguous=amb,net_r=net)
    # Rebuild the candle rows for trade outcomes from the trade-history records.
    outcome_by_id={t.get("signal_id"):t for t in trade_history}
    for row in rows:
        t=outcome_by_id.get(row.get("signal_id"))
        if t:row.update({"result":t.get("result"),"r_multiple":t.get("r_multiple"),"resolved_at":t.get("resolved_at")})
    summary=summarize_rows(rows)
    return {"status":"completed","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"candles_evaluated":len(rows),"signals":len(trade_history),"wins":summary["wins"],"losses":summary["losses"],"ambiguous":summary["ambiguous"],"open":summary["open"],"net_r":summary["net_r"],"performance":summary,"rows":rows,"trade_history":trade_history,"live_orders_allowed":False,"m15_policy":"CLOSED_AT_M5_CLOSE_MINUS_15M","lookahead_safe":True,"warmup_bars":60,"signal_lock_policy":"ONE_ACTIVE_SIGNAL_PER_SYMBOL","setup_lock_policy":"ONE_SIGNAL_PER_SETUP_UNTIL_NEW_SETUP"}
