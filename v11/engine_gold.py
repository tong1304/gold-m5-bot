from __future__ import annotations

import os
import hashlib
import pandas as pd

from .data_quality import validate_frame
from .regime import classify_regime
from .asset_strategies import evaluate_asset_strategies
from .asset_strategy_registry import native_strategy_ids
from .setup_state import SetupState, can_emit_entry
from .decision_priority import signal_reason

ENGINE_VERSION = "12.12-ASSET-ISOLATED"
GOLD_ENGINES = ("G1", "G2", "G3")
MIN_RR = {"G1": 2.0, "G2": 2.0, "G3": 1.5}


def _stable_id(prefix, *parts):
    raw = "|".join("" if p is None else str(p).strip() for p in parts)
    return f"{prefix}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def _asof_context(frame, target_time, timeframe_minutes, max_bars=100):
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:return frame
    out=frame.copy();out["datetime"]=pd.to_datetime(out["datetime"],utc=True,errors="coerce");target=pd.Timestamp(target_time);target=target.tz_localize("UTC") if target.tzinfo is None else target.tz_convert("UTC");cutoff=target-pd.Timedelta(minutes=timeframe_minutes)
    return out.loc[out["datetime"]<=cutoff].sort_values("datetime").tail(max_bars).reset_index(drop=True)


def _finalize(payload):
    payload=dict(payload);payload["reason"]=signal_reason(payload);payload["signal_reason"]=payload["reason"];return payload


def _setup_ids(selected, symbol, candle_time):
    engine=selected["engine"];direction=selected["direction"];anchor=selected.get("setup_anchor");mode=selected.get("strategy_mode","NATIVE");source=selected.get("source_asset",symbol)
    sid=_stable_id("SETUP",symbol,mode,source,engine,direction,round(float(anchor),8) if anchor is not None else "NA")
    tid=_stable_id("TRIGGER",engine,direction,candle_time,selected.get("trigger_signature",""))
    return sid,tid


def _trade_levels(selected):
    ev=selected.get("evidence") or {};entry=float(ev.get("entry_price",0) or 0);sl=float(ev.get("sl_price",0) or 0);primary=float(ev.get("tp_price",0) or 0);minimum=float(selected.get("effective_min_rr") or MIN_RR.get(selected.get("engine"),2.0))
    if entry<=0 or sl<=0 or primary<=0:return {"valid":False,"reason":"ENGINE_LEVELS_UNAVAILABLE"}
    risk=abs(entry-sl)
    if risk<=0:return {"valid":False,"reason":"ZERO_RISK"}
    if selected["direction"]=="BUY" and not sl<entry:return {"valid":False,"reason":"INVALID_BUY_LEVELS"}
    if selected["direction"]=="SELL" and not sl>entry:return {"valid":False,"reason":"INVALID_SELL_LEVELS"}
    rr=abs(primary-entry)/risk
    if rr<minimum:return {"valid":False,"reason":"RR_BELOW_MINIMUM","risk_reward":rr,"target_rr":minimum}
    return {"valid":True,"entry":entry,"sl":sl,"tp":primary,"tp1":primary,"tp2":None,"tp3":None,"risk":risk,"risk_reward":rr,"effective_rr":rr,"minimum_rr":minimum,"target_rr":minimum,"tp_levels":[{"price":primary,"risk_reward":rr,"type":"TP1","allocation_pct":100}],"tp_count":1,"tp_allocations":[100],"tp_structure_levels":[primary],"tp_selection":"ASSET_STRATEGY_PRIMARY_TARGET"}


def analyze(m5,m15=None,symbol=None,index=None,setup_state=None,h1=None):
    if index is not None:m5=m5.iloc[:index+1].reset_index(drop=True)
    m5=m5.reset_index(drop=True);q5=validate_frame(m5,minimum=60,timeframe_minutes=5,market=symbol)
    if len(m5):
        trigger_time=pd.to_datetime(m5.iloc[-1]["datetime"],utc=True);m15=_asof_context(m15,trigger_time,15);h1=_asof_context(h1,trigger_time,60)
    q15=validate_frame(m15,minimum=60,timeframe_minutes=15,market=symbol) if m15 is not None else ["M15_CONTEXT_REQUIRED"]
    q1=validate_frame(h1,minimum=60,timeframe_minutes=60,market=symbol) if h1 is not None else ["H1_CONTEXT_REQUIRED"]
    base={"engine_version":ENGINE_VERSION,"symbol":symbol,"live_orders_allowed":False,"analysis_window":{"m5_context_bars":100,"m15_context_bars":100,"h1_context_bars":100,"timeframe_mode":"MTF:H1→M15→M5","alignment":"H1/M15 closed before M5 trigger"}}
    if q5 or q15 or q1:return _finalize({**base,"valid":False,"signal":"NO_TRADE","strategy":"NONE","allowed_engines":list(GOLD_ENGINES),"rejection_reasons":q5+q15+q1,"trade_levels":{"valid":False},"data_quality":{"m5":q5,"m15":q15,"h1":q1}})
    regime=classify_regime(m5,m15,h1);current_regime=regime.get("m5_regime") or regime.get("regime","TRANSITION");native_ids=native_strategy_ids("GOLD",current_regime);base.update({"regime":regime,"m5_regime":current_regime,"h1_bias":regime.get("h1_bias"),"m15_regime":regime.get("m15_regime"),"m15_trend":regime.get("m15_trend"),"m15_role":"CONTEXT_ONLY","allowed_engines":list(GOLD_ENGINES),"native_regime_strategies":native_ids,"strategy_selection_order":["NATIVE"]})
    candidates,trace=evaluate_asset_strategies("GOLD",m5,regime);strategy_mode="NATIVE" if candidates else "NONE";source_asset="GOLD"
    base["strategy_mode"]=strategy_mode
    base["source_asset"]=source_asset
    base["decision_trace"]=trace
    if not candidates:
        return _finalize({**base,"valid":False,"signal":"NO_TRADE","strategy":"NONE","setup_candidates":[],"selected_setup":None,"rejection_reasons":["NO_GOLD_NATIVE_STRATEGY_PASSED_CORE_GATE_SCORE_FILTER"],"trade_levels":{"valid":False}})
    selected=candidates[0];sid,tid=_setup_ids(selected,symbol,str(m5.iloc[-1].get("datetime","")));selected={**selected,"setup_id":sid,"trigger_id":tid,"symbol":symbol,"strategy_mode":"NATIVE","source_asset":"GOLD"};score=selected.get("score_detail") or {};base.update({"setup_candidates":candidates,"selected_setup":selected,"strategy":selected["strategy"],"engine":selected["engine"],"setup_id":sid,"trigger_id":tid,"setup_score":score,"strategy_mode":"NATIVE","source_asset":"GOLD"})
    if not score.get("qualified"):return _finalize({**base,"valid":False,"signal":"NO_TRADE","entry_type":None,"rejection_reasons":["SETUP_SCORE_BELOW_THRESHOLD"],"trade_levels":{"valid":False}})
    state=setup_state if isinstance(setup_state,SetupState) else SetupState();max_reentries=int(os.getenv("MAX_REENTRIES_PER_SETUP","2"));emit,entry_type=can_emit_entry(state,sid,tid,max_reentries=max_reentries)
    if not emit:return _finalize({**base,"valid":False,"signal":"NO_TRADE","entry_type":entry_type,"rejection_reasons":[entry_type],"trade_levels":{"valid":False}})
    levels=_trade_levels(selected)
    if not levels.get("valid"):return _finalize({**base,"valid":False,"signal":"NO_TRADE","entry_type":entry_type,"rejection_reasons":[levels.get("reason","INVALID_RISK_OR_RR")],"trade_levels":levels,"rr_target":levels.get("target_rr",2.0)})
    return _finalize({**base,"valid":True,"signal":selected["direction"],"direction":selected["direction"],"strategy":selected["strategy"],"engine":selected["engine"],"entry_type":entry_type,"setup_id":sid,"trigger_id":tid,"trade_levels":levels,"risk_engine":{"method":"ASSET_STRATEGY_PRIMARY_TARGET","risk_reward":levels["risk_reward"],"minimum_rr":levels["minimum_rr"],"strategy_mode":"NATIVE"},"rr_target":levels["minimum_rr"],"rejection_reasons":[],"data_quality":{"m5":[],"m15":[],"h1":[]},"setup_state":{"reentries_used":state.reentry_count(sid),"max_reentries":max_reentries},"live_orders_allowed":False})
