from __future__ import annotations
import os
import pandas as pd
from .data_quality import validate_frame
from .risk import calculate as calculate_risk, MIN_RISK_REWARD as _MIN_RISK_REWARD, min_rr_for_strategy
from .regime import classify_regime
from .strategy_engine import evaluate_all_allowed_with_trace, enrich_selected
from .setup_state import SetupState, can_emit_entry
ENGINE_VERSION="12.1-MTF-H1-M15-M5-REGIME-8-ENGINE-REENTRY"
FORWARD_BARS=12
MIN_RISK_REWARD=_MIN_RISK_REWARD;RISK_REWARD=MIN_RISK_REWARD
BTC_STRATEGIES=("E1_TREND","E2_TREND_PULLBACK","E3_BREAKOUT","E4_BREAKOUT_RETEST","E5_MOMENTUM","E6_MEAN_REVERSION","E7_LIQUIDITY_REVERSAL","E8_RANGE");GOLD_STRATEGIES=BTC_STRATEGIES


def detect_m5_trend(m5):
    from .regime import _direction
    return {"direction":_direction(m5),"bars":min(100,len(m5))}


def _asof_context(frame, target_time, timeframe_minutes, max_bars=100):
    """Return only higher-TF candles that were closed before the M5 trigger.

    The higher-TF candle must have opened at least one full timeframe before the
    M5 trigger timestamp. This prevents H1/M15 lookahead in both live and replay.
    """
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    out=frame.copy()
    out["datetime"]=pd.to_datetime(out["datetime"],utc=True,errors="coerce")
    target=pd.Timestamp(target_time)
    if target.tzinfo is None: target=target.tz_localize("UTC")
    else: target=target.tz_convert("UTC")
    cutoff=target-pd.Timedelta(minutes=timeframe_minutes)
    out=out.loc[out["datetime"]<=cutoff].sort_values("datetime").tail(max_bars).reset_index(drop=True)
    return out


def analyze(m5,m15=None,symbol=None,index=None,setup_state=None,h1=None):
    if index is not None:m5=m5.iloc[:index+1].reset_index(drop=True)
    m5=m5.reset_index(drop=True)
    q5=validate_frame(m5,minimum=60,timeframe_minutes=5,market=symbol)
    if len(m5):
        trigger_time=pd.to_datetime(m5.iloc[-1]["datetime"],utc=True)
        m15=_asof_context(m15,trigger_time,15,100)
        h1=_asof_context(h1,trigger_time,60,100)
    q15=validate_frame(m15,minimum=60,timeframe_minutes=15,market=symbol) if m15 is not None else ["M15_CONTEXT_REQUIRED"]
    q1=validate_frame(h1,minimum=60,timeframe_minutes=60,market=symbol) if h1 is not None else ["H1_CONTEXT_REQUIRED"]
    base={"engine_version":ENGINE_VERSION,"symbol":symbol,"live_orders_allowed":False,"analysis_window":{"m5_context_bars":100,"m15_context_bars":100,"h1_context_bars":100,"timeframe_mode":"MTF:H1→M15→M5","alignment":"H1/M15 closed before M5 trigger"}}
    if q5 or q15 or q1:return {**base,"valid":False,"signal":"NO_TRADE","strategy":"NONE","regime":None,"allowed_engines":[],"rejection_reasons":q5+q15+q1,"trade_levels":{"valid":False},"data_quality":{"m5":q5,"m15":q15,"h1":q1}}
    regime=classify_regime(m5,m15,h1);base.update({"regime":regime,"m5_trend":detect_m5_trend(m5),"h1_bias":regime.get("h1_bias"),"m15_regime":regime.get("m15_regime"),"allowed_engines":regime.get("allowed_engines",[])})
    if regime.get("regime")=="CONFLICT":return {**base,"valid":False,"signal":"NO_TRADE","strategy":"NONE","setup_candidates":[],"selected_setup":None,"rejection_reasons":[regime.get("reason","MTF_FILTER_CONFLICT")],"trade_levels":{"valid":False},"decision_trace":[]}
    candidates,trace=evaluate_all_allowed_with_trace(m5,regime);base["decision_trace"]=trace
    if not candidates:return {**base,"valid":False,"signal":"NO_TRADE","strategy":"NONE","setup_candidates":[],"selected_setup":None,"rejection_reasons":["NO_ALLOWED_ENGINE_SETUP"],"trade_levels":{"valid":False}}
    selected=enrich_selected(candidates[0],symbol,regime["regime"],str(m5.iloc[-1].get("datetime","")));score=selected.get("score_detail",{});base.update({"setup_candidates":candidates,"selected_setup":selected,"strategy":selected["strategy"],"engine":selected["engine"],"setup_id":selected["setup_id"],"trigger_id":selected["trigger_id"],"setup_score":score})
    if not score.get("qualified"):return {**base,"valid":False,"signal":"NO_TRADE","entry_type":None,"rejection_reasons":["SETUP_SCORE_BELOW_THRESHOLD"],"trade_levels":{"valid":False}}
    state=setup_state if isinstance(setup_state,SetupState) else SetupState();max_reentries=int(os.getenv("MAX_REENTRIES_PER_SETUP","2"));emit,entry_type=can_emit_entry(state,selected["setup_id"],selected["trigger_id"],max_reentries=max_reentries)
    if not emit:return {**base,"valid":False,"signal":"NO_TRADE","entry_type":entry_type,"rejection_reasons":[entry_type],"trade_levels":{"valid":False}}
    strategy=selected["strategy"];target_rr=min_rr_for_strategy(strategy);levels=calculate_risk(m5,selected["direction"],strategy,selected.get("evidence"),rr=target_rr);actual_rr=float(levels.get("risk_reward",levels.get("effective_rr",0)) or 0)
    if not levels.get("valid") or actual_rr<target_rr:return {**base,"valid":False,"signal":"NO_TRADE","entry_type":entry_type,"rejection_reasons":[levels.get("reason","INVALID_RISK_OR_RR")],"trade_levels":levels,"rr_target":target_rr}
    return {**base,"valid":True,"signal":selected["direction"],"direction":selected["direction"],"strategy":strategy,"engine":selected["engine"],"entry_type":entry_type,"setup_id":selected["setup_id"],"trigger_id":selected["trigger_id"],"trade_levels":levels,"risk_engine":{"method":"STRUCTURE+ATR","risk_reward":levels.get("risk_reward"),"minimum_rr":target_rr},"rr_target":target_rr,"rejection_reasons":[],"data_quality":{"m5":[],"m15":[],"h1":[]},"setup_state":{"reentries_used":state.reentry_count(selected["setup_id"]),"max_reentries":max_reentries},"live_orders_allowed":False}

analyze_structure_setup=analyze
