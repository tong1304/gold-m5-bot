from __future__ import annotations
import os
import pandas as pd
from .data_quality import validate_frame
from .risk import MIN_RISK_REWARD as _MIN_RISK_REWARD
from .regime import classify_regime
from .strategy_engine import enrich_selected
from .new_btc_engines import evaluate_new_btc_engines
from .setup_state import SetupState, can_emit_entry
from .decision_priority import signal_reason
from .engine_gold import analyze as analyze_gold
ENGINE_VERSION="12.8-MTF-H1-M15-TREND-M5-BTC-GOLD-MULTI-TP"
MIN_RISK_REWARD=_MIN_RISK_REWARD
BTC_STRATEGIES=("B1_RANGE_SWEEP_DISPLACEMENT","B2_HTF_OB_M5_FVG_RETEST","B3_VOLATILITY_EXPANSION_BREAKOUT_RETEST")
GOLD_STRATEGIES=("G1_LIQUIDITY_SWEEP_CHOCH","G2_CONTINUATION_FVG_PULLBACK","G3_SESSION_BREAKOUT_RETEST")
def detect_m5_trend(m5):
    from .regime import _direction
    return {"direction":_direction(m5),"bars":min(100,len(m5))}
def _asof_context(frame,target_time,timeframe_minutes,max_bars=100):
    if frame is None or not isinstance(frame,pd.DataFrame) or frame.empty:return frame
    out=frame.copy();out["datetime"]=pd.to_datetime(out["datetime"],utc=True,errors="coerce");target=pd.Timestamp(target_time);target=target.tz_localize("UTC") if target.tzinfo is None else target.tz_convert("UTC");cutoff=target-pd.Timedelta(minutes=timeframe_minutes)
    return out.loc[out["datetime"]<=cutoff].sort_values("datetime").tail(max_bars).reset_index(drop=True)
def _finalize(payload):
    payload=dict(payload);payload["reason"]=signal_reason(payload);payload["signal_reason"]=payload["reason"];return payload
def _btc_target_rr(engine):return {"B1":2.0,"B2":3.0,"B3":1.5}.get(str(engine).upper(),MIN_RISK_REWARD)
def _btc_trade_levels(selected):
    e=selected.get("evidence",{}) or {};entry=float(e.get("entry_price",0) or 0);sl=float(e.get("sl_price",0) or 0);primary=float(e.get("tp_price",0) or 0);minimum=_btc_target_rr(selected.get("engine"));risk=abs(entry-sl);rr=abs(primary-entry)/max(risk,1e-12);direction=str(selected.get("direction",""))
    if entry<=0 or sl<=0 or primary<=0:return {"valid":False,"reason":"BTC_ENGINE_LEVELS_UNAVAILABLE","target_rr":minimum}
    if risk<=0 or (direction=="BUY" and not sl<entry<primary) or (direction=="SELL" and not primary<entry<sl):return {"valid":False,"reason":"BTC_ENGINE_INVALID_LEVELS","target_rr":minimum}
    if rr<minimum:return {"valid":False,"reason":"RR_BELOW_ENGINE_MINIMUM","risk_reward":rr,"target_rr":minimum}
    milestones=[2.0,4.0] if rr>=6.0 else ([2.0] if rr>=4.0 else []);tps=[]
    for r in milestones:
        p=entry+r*risk if direction=="BUY" else entry-r*risk
        if (direction=="BUY" and p<primary) or (direction=="SELL" and p>primary):tps.append(p)
    tps.append(primary);alloc={1:[100],2:[50,50],3:[40,30,30]}[len(tps)];levels=[{"price":p,"risk_reward":abs(p-entry)/risk,"type":f"TP{i+1}","allocation_pct":alloc[i]} for i,p in enumerate(tps)]
    return {"valid":True,"entry":entry,"sl":sl,"tp":tps[-1],"tp1":tps[0],"tp2":tps[1] if len(tps)>1 else None,"tp3":tps[2] if len(tps)>2 else None,"risk":risk,"risk_reward":levels[-1]["risk_reward"],"effective_rr":levels[-1]["risk_reward"],"target_rr":minimum,"minimum_rr":minimum,"tp_levels":levels,"tp_count":len(levels),"tp_allocations":alloc,"tp_structure_levels":tps,"tp_selection":"BTC_PRIMARY_TARGET_WITH_RR_STAGING"}
def analyze(m5,m15=None,symbol=None,index=None,setup_state=None,h1=None):
    if str(symbol or "").upper() in ("GOLD","XAU/USD","XAU/USDT","XAUUSD"):return analyze_gold(m5,m15,symbol,index,setup_state,h1)
    if index is not None:m5=m5.iloc[:index+1].reset_index(drop=True)
    m5=m5.reset_index(drop=True);q5=validate_frame(m5,minimum=60,timeframe_minutes=5,market=symbol)
    if len(m5):
        t=pd.to_datetime(m5.iloc[-1]["datetime"],utc=True);m15=_asof_context(m15,t,15);h1=_asof_context(h1,t,60)
    q15=validate_frame(m15,minimum=60,timeframe_minutes=15,market=symbol) if m15 is not None else ["M15_CONTEXT_REQUIRED"];q1=validate_frame(h1,minimum=60,timeframe_minutes=60,market=symbol) if h1 is not None else ["H1_CONTEXT_REQUIRED"]
    base={"engine_version":ENGINE_VERSION,"symbol":symbol,"live_orders_allowed":False,"analysis_window":{"m5_context_bars":100,"m15_context_bars":100,"h1_context_bars":100,"timeframe_mode":"MTF:H1→M15→M5","alignment":"H1/M15 closed before M5 trigger"}}
    if q5 or q15 or q1:return _finalize({**base,"valid":False,"signal":"NO_TRADE","strategy":"NONE","allowed_engines":list(BTC_STRATEGIES),"rejection_reasons":q5+q15+q1,"trade_levels":{"valid":False},"data_quality":{"m5":q5,"m15":q15,"h1":q1}})
    regime=classify_regime(m5,m15,h1);base.update({"regime":regime,"m5_trend":detect_m5_trend(m5),"h1_bias":regime.get("h1_bias"),"h1_gate":regime.get("h1_gate"),"m15_regime":regime.get("m15_regime"),"m15_trend":regime.get("m15_trend"),"m15_role":"TREND_ONLY","m15_regime_filter_enabled":False,"allowed_engines":list(BTC_STRATEGIES)})
    hb,mb=regime.get("h1_bias"),regime.get("m15_trend")
    if hb not in ("BUY","SELL") or mb not in ("BUY","SELL") or hb!=mb:return _finalize({**base,"valid":False,"signal":"NO_TRADE","strategy":"NONE","rejection_reasons":["MTF_DIRECTION_GATE_FAILED" if hb==mb else "H1_M15_TREND_CONFLICT"],"trade_levels":{"valid":False},"decision_trace":[]})
    candidates,trace=evaluate_new_btc_engines(m5,m15,h1);base["decision_trace"]=trace;candidates=[c for c in candidates if c.get("direction")==hb]
    if not candidates:return _finalize({**base,"valid":False,"signal":"NO_TRADE","strategy":"NONE","setup_candidates":[],"selected_setup":None,"rejection_reasons":["NO_ALLOWED_NEW_BTC_ENGINE_SETUP"],"trade_levels":{"valid":False}})
    selected=enrich_selected(candidates[0],symbol,regime.get("regime","UNKNOWN"),str(m5.iloc[-1].get("datetime","")));score=selected.get("score_detail",{});base.update({"setup_candidates":candidates,"selected_setup":selected,"strategy":selected["strategy"],"engine":selected["engine"],"setup_id":selected["setup_id"],"trigger_id":selected["trigger_id"],"setup_score":score})
    if not score.get("qualified"):return _finalize({**base,"valid":False,"signal":"NO_TRADE","entry_type":None,"rejection_reasons":["SETUP_SCORE_BELOW_THRESHOLD"],"trade_levels":{"valid":False}})
    state=setup_state if isinstance(setup_state,SetupState) else SetupState();emit,entry_type=can_emit_entry(state,selected["setup_id"],selected["trigger_id"],max_reentries=int(os.getenv("MAX_REENTRIES_PER_SETUP","2")))
    if selected.get("entry_type_hint") in ("BUY_LIMIT","SELL_LIMIT"):entry_type=selected["entry_type_hint"]
    if not emit:return _finalize({**base,"valid":False,"signal":"NO_TRADE","entry_type":entry_type,"rejection_reasons":[entry_type],"trade_levels":{"valid":False}})
    levels=_btc_trade_levels(selected)
    if not levels.get("valid"):return _finalize({**base,"valid":False,"signal":"NO_TRADE","entry_type":entry_type,"rejection_reasons":[levels.get("reason","INVALID_RISK_OR_RR")],"trade_levels":levels,"rr_target":levels.get("target_rr")})
    return _finalize({**base,"valid":True,"signal":selected["direction"],"direction":selected["direction"],"strategy":selected["strategy"],"engine":selected["engine"],"entry_type":entry_type,"setup_id":selected["setup_id"],"trigger_id":selected["trigger_id"],"trade_levels":levels,"risk_engine":{"method":"BTC_PRIMARY_TARGET_WITH_RR_STAGING","risk_reward":levels["risk_reward"],"minimum_rr":levels["minimum_rr"]},"rr_target":levels["minimum_rr"],"rejection_reasons":[],"data_quality":{"m5":[],"m15":[],"h1":[]},"live_orders_allowed":False})
analyze_structure_setup=analyze
