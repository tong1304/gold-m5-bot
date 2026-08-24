from __future__ import annotations
import os
import pandas as pd
from .data_quality import validate_frame
from .risk import calculate as calculate_risk, MIN_RISK_REWARD as _MIN_RISK_REWARD, min_rr_for_strategy
from .regime import classify_regime
from .strategy_engine import evaluate_all_allowed_with_trace, enrich_selected
from .btc_engines import evaluate_btc_engines
from .setup_state import SetupState, can_emit_entry
from .decision_priority import choose_priority_setup, signal_reason
ENGINE_VERSION="12.3-MTF-H1-HARD-GATE-M15-M5-BTC-B1-B3"
FORWARD_BARS=12
MIN_RISK_REWARD=_MIN_RISK_REWARD;RISK_REWARD=MIN_RISK_REWARD
BTC_STRATEGIES=("E1_TREND","E2_TREND_PULLBACK","E3_BREAKOUT","E4_BREAKOUT_RETEST","E5_MOMENTUM","E6_MEAN_REVERSION","E7_LIQUIDITY_REVERSAL","E8_RANGE","B1_RANGE_SWEEP_DISPLACEMENT","B2_HTF_ZONE_M5_FVG_RETEST","B3_VOLATILITY_EXPANSION_BREAKOUT_RETEST");GOLD_STRATEGIES=BTC_STRATEGIES

def detect_m5_trend(m5):
    from .regime import _direction
    return {"direction":_direction(m5),"bars":min(100,len(m5))}
def _asof_context(frame,target_time,timeframe_minutes,max_bars=100):
    if frame is None or not isinstance(frame,pd.DataFrame) or frame.empty:return frame
    out=frame.copy();out["datetime"]=pd.to_datetime(out["datetime"],utc=True,errors="coerce");target=pd.Timestamp(target_time)
    if target.tzinfo is None:target=target.tz_localize("UTC")
    else:target=target.tz_convert("UTC")
    cutoff=target-pd.Timedelta(minutes=timeframe_minutes);return out.loc[out["datetime"]<=cutoff].sort_values("datetime").tail(max_bars).reset_index(drop=True)
def _finalize(payload):
    payload=dict(payload);payload["reason"]=signal_reason(payload);payload["signal_reason"]=payload["reason"];return payload
def _btc_target_rr(engine):return {"B1":1.5,"B2":2.0,"B3":1.5}.get(str(engine).upper(),MIN_RISK_REWARD)
def _btc_trade_levels(selected):
    evidence=selected.get("evidence",{}) or {};entry=float(evidence.get("entry_price",0) or 0);sl=float(evidence.get("sl_price",0) or 0);tp=float(evidence.get("tp_price",0) or 0);rr=float(evidence.get("risk_reward",0) or 0)
    target=_btc_target_rr(selected.get("engine"))
    if entry<=0 or sl<=0 or tp<=0 or rr<target:return {"valid":False,"reason":"BTC_ENGINE_LEVELS_UNAVAILABLE","target_rr":target}
    risk=abs(entry-sl);direction=str(selected.get("direction",""))
    if risk<=0 or (direction=="BUY" and not(sl<entry<tp)) or (direction=="SELL" and not(tp<entry<sl)):return {"valid":False,"reason":"BTC_ENGINE_INVALID_LEVELS","entry":entry,"sl":sl,"tp":tp,"target_rr":target}
    return {"valid":True,"entry":entry,"sl":sl,"tp":tp,"tp1":tp,"tp2":None,"tp3":None,"risk":risk,"risk_reward":rr,"effective_rr":rr,"target_rr":target,"minimum_rr":target,"strategy":selected.get("strategy"),"structure_type":"BTC_ENGINE","structure_level":sl,"sl_buffer":0.0,"tp_levels":[{"price":tp,"risk_reward":rr,"type":"TP1","allocation_pct":100}],"tp_count":1,"tp_allocations":[100],"tp_structure_levels":[tp],"tp_selection":"BTC_ENGINE_EXACT_SPEC_LEVELS"}
def analyze(m5,m15=None,symbol=None,index=None,setup_state=None,h1=None):
    if index is not None:m5=m5.iloc[:index+1].reset_index(drop=True)
    m5=m5.reset_index(drop=True);q5=validate_frame(m5,minimum=60,timeframe_minutes=5,market=symbol)
    if len(m5):
        trigger_time=pd.to_datetime(m5.iloc[-1]["datetime"],utc=True);m15=_asof_context(m15,trigger_time,15,100);h1=_asof_context(h1,trigger_time,60,100)
    q15=validate_frame(m15,minimum=60,timeframe_minutes=15,market=symbol) if m15 is not None else ["M15_CONTEXT_REQUIRED"];q1=validate_frame(h1,minimum=60,timeframe_minutes=60,market=symbol) if h1 is not None else ["H1_CONTEXT_REQUIRED"]
    base={"engine_version":ENGINE_VERSION,"symbol":symbol,"live_orders_allowed":False,"analysis_window":{"m5_context_bars":100,"m15_context_bars":100,"h1_context_bars":100,"timeframe_mode":"MTF:H1→M15→M5","alignment":"H1/M15 closed before M5 trigger"}}
    if q5 or q15 or q1:return _finalize({**base,"valid":False,"signal":"NO_TRADE","strategy":"NONE","regime":None,"allowed_engines":[],"rejection_reasons":q5+q15+q1,"trade_levels":{"valid":False},"data_quality":{"m5":q5,"m15":q15,"h1":q1}})
    regime=classify_regime(m5,m15,h1);base.update({"regime":regime,"m5_trend":detect_m5_trend(m5),"h1_bias":regime.get("h1_bias"),"h1_gate":regime.get("h1_gate"),"m15_regime":regime.get("m15_regime"),"allowed_engines":regime.get("allowed_engines",[])})
    candidates=[];trace=[];btc_candidates=[]
    if str(symbol or "").upper() in ("BTC","BTC/USD","BTC/USDT"):
        btc_candidates,btc_trace=evaluate_btc_engines(m5,m15,h1);candidates.extend(btc_candidates);trace.extend(btc_trace);base["allowed_engines"]=["B1","B2","B3"]+list(dict.fromkeys(base.get("allowed_engines",[])))
    if regime.get("regime")=="CONFLICT" and not candidates:return _finalize({**base,"valid":False,"signal":"NO_TRADE","strategy":"NONE","setup_candidates":[],"selected_setup":None,"rejection_reasons":[regime.get("reason","MTF_FILTER_CONFLICT")],"trade_levels":{"valid":False},"decision_trace":trace})
    legacy_candidates,legacy_trace=evaluate_all_allowed_with_trace(m5,regime);candidates.extend(legacy_candidates);trace.extend(legacy_trace);base["decision_trace"]=trace
    if not candidates:return _finalize({**base,"valid":False,"signal":"NO_TRADE","strategy":"NONE","setup_candidates":[],"selected_setup":None,"rejection_reasons":["NO_ALLOWED_ENGINE_SETUP"],"trade_levels":{"valid":False}})
    selected_candidate=(btc_candidates[0] if btc_candidates else choose_priority_setup(legacy_candidates));selected=enrich_selected(selected_candidate,symbol,regime["regime"],str(m5.iloc[-1].get("datetime","")));score=selected.get("score_detail",{})
    base.update({"setup_candidates":candidates,"selected_setup":selected,"strategy":selected["strategy"],"engine":selected["engine"],"setup_id":selected["setup_id"],"trigger_id":selected["trigger_id"],"setup_score":score})
    if not score.get("qualified"):return _finalize({**base,"valid":False,"signal":"NO_TRADE","entry_type":None,"rejection_reasons":["SETUP_SCORE_BELOW_THRESHOLD"],"trade_levels":{"valid":False}})
    state=setup_state if isinstance(setup_state,SetupState) else SetupState();max_reentries=int(os.getenv("MAX_REENTRIES_PER_SETUP","2"));emit,entry_type=can_emit_entry(state,selected["setup_id"],selected["trigger_id"],max_reentries=max_reentries)
    if selected.get("entry_type_hint") in ("BUY_LIMIT","SELL_LIMIT"):entry_type=selected["entry_type_hint"]
    if not emit:return _finalize({**base,"valid":False,"signal":"NO_TRADE","entry_type":entry_type,"rejection_reasons":[entry_type],"trade_levels":{"valid":False}})
    strategy=selected["strategy"];target_rr=_btc_target_rr(selected["engine"]) if selected.get("engine") in ("B1","B2","B3") else min_rr_for_strategy(strategy);levels=_btc_trade_levels(selected) if selected.get("engine") in ("B1","B2","B3") else calculate_risk(m5,selected["direction"],strategy,selected.get("evidence"),rr=target_rr);actual_rr=float(levels.get("risk_reward",levels.get("effective_rr",0)) or 0)
    if not levels.get("valid") or actual_rr<target_rr:return _finalize({**base,"valid":False,"signal":"NO_TRADE","entry_type":entry_type,"rejection_reasons":[levels.get("reason","INVALID_RISK_OR_RR")],"trade_levels":levels,"rr_target":target_rr})
    return _finalize({**base,"valid":True,"signal":selected["direction"],"direction":selected["direction"],"strategy":strategy,"engine":selected["engine"],"entry_type":entry_type,"setup_id":selected["setup_id"],"trigger_id":selected["trigger_id"],"trade_levels":levels,"risk_engine":{"method":"BTC_ENGINE_SPEC_LEVELS" if selected.get("engine") in ("B1","B2","B3") else "STRUCTURE+ATR","risk_reward":levels.get("risk_reward"),"minimum_rr":target_rr},"rr_target":target_rr,"rejection_reasons":[],"data_quality":{"m5":[],"m15":[],"h1":[]},"setup_state":{"reentries_used":state.reentry_count(selected["setup_id"]),"max_reentries":max_reentries},"live_orders_allowed":False})
analyze_structure_setup=analyze
