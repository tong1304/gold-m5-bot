"""V9 standalone signal engine for BTC + GOLD.
No V8 imports or legacy core dependencies.
"""
from __future__ import annotations
import math, os
from datetime import datetime, timezone
import pandas as pd
import requests
from flask import Flask

ENGINE_VERSION="9.0"
app=Flask(__name__)
SYMBOL=os.getenv("SYMBOL","BTC/USDT")
SPREAD=float(os.getenv("SPREAD","0.20")); SLIPPAGE=float(os.getenv("SLIPPAGE","0.05"))
MINIMUM_ATR=float(os.getenv("MINIMUM_ATR","0")); MIN_STOP_ATR=float(os.getenv("MIN_STOP_ATR","0")); MAX_STOP_ATR=float(os.getenv("MAX_STOP_ATR","4"))
MIN_RISK_REWARD=max(float(os.getenv("MIN_RISK_REWARD","2.0")),2.0); RISK_REWARD=MIN_RISK_REWARD
FORWARD_BARS=int(os.getenv("FORWARD_BARS","24")); SIGNAL_HISTORY_POINTS=int(os.getenv("SIGNAL_HISTORY_POINTS","200"))

def _f(v,d=0.0):
    try:
        x=float(v); return x if math.isfinite(x) else d
    except (TypeError,ValueError): return d

def _atr(df,i,period=14):
    if df is None or len(df)==0 or i<1:return 1e-9
    h=pd.to_numeric(df.high,errors="coerce"); l=pd.to_numeric(df.low,errors="coerce"); c=pd.to_numeric(df.close,errors="coerce")
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    return max(_f(tr.rolling(period,min_periods=3).mean().iloc[i]),_f(h.iloc[i]-l.iloc[i]),1e-9)

def _ema_bias(df):
    if df is None or len(df)<50:return "NEUTRAL"
    c=pd.to_numeric(df.close,errors="coerce"); e20s=c.ewm(span=20,adjust=False).mean(); e20=e20s.iloc[-1]; e50=c.ewm(span=50,adjust=False).mean().iloc[-1]; last=_f(c.iloc[-1])
    if last>e20 and e20>=e50:return "BUY"
    if last<e20 and e20<=e50:return "SELL"
    slope=_f(e20-e20s.iloc[max(0,len(e20s)-6)])
    return "BUY" if slope>0 else "SELL" if slope<0 else "NEUTRAL"

def _structure(df,lookback=30):
    if df is None or len(df)<50:return {"bias":"NEUTRAL","high":None,"low":None}
    x=df.iloc[:-1].tail(lookback); hi,lo=_f(x.high.max()),_f(x.low.min()); bias=_ema_bias(df); c=_f(df.iloc[-1].close)
    if c>hi:bias="BUY"
    elif c<lo:bias="SELL"
    return {"bias":bias,"high":hi,"low":lo}

def _location(df,direction,lookback=48):
    if df is None or len(df)<30:return {"valid":False,"zone":"INSUFFICIENT_DATA"}
    x=df.tail(lookback); hi,lo=_f(x.high.max()),_f(x.low.min()); width=max(hi-lo,1e-9); c=_f(df.iloc[-1].close)
    if direction=="BUY":valid=c<=lo+width*.60;zone="DISCOUNT" if c<=lo+width*.50 else "MID_DISCOUNT"
    else:valid=c>=hi-width*.60;zone="PREMIUM" if c>=hi-width*.50 else "MID_PREMIUM"
    return {"valid":bool(valid),"zone":zone if valid else ("PREMIUM" if direction=="BUY" else "DISCOUNT"),"range_high":hi,"range_low":lo,"mid":lo+width*.5}

def _find_sweep(df,direction,window=18):
    if df is None or len(df)<35:return None
    for j in range(max(2,len(df)-window),len(df)):
        prior=df.iloc[max(0,j-window):j]
        if len(prior)<6:continue
        r=df.iloc[j]; ph,pl=_f(prior.high.max()),_f(prior.low.min()); h,l,c=_f(r.high),_f(r.low),_f(r.close)
        if direction=="BUY" and l<pl and c>=pl:return {"index":j,"type":"LIQUIDITY_SWEEP_LOW","level":pl,"extreme":l,"close":c,"confirmed":True}
        if direction=="SELL" and h>ph and c<=ph:return {"index":j,"type":"LIQUIDITY_SWEEP_HIGH","level":ph,"extreme":h,"close":c,"confirmed":True}
    return None

def _find_mss(df,sweep,direction,window=10):
    if not sweep:return None
    for j in range(sweep["index"]+1,min(len(df),sweep["index"]+window+1)):
        prior=df.iloc[max(0,j-6):j]
        if len(prior)<3:continue
        r=df.iloc[j]; ph,pl=_f(prior.high.max()),_f(prior.low.min()); c=_f(r.close)
        if direction=="BUY" and c>ph:return {"index":j,"type":"BULLISH_MSS_BOS","level":ph}
        if direction=="SELL" and c<pl:return {"index":j,"type":"BEARISH_MSS_BOS","level":pl}
    return None

def _retest(df,mss,direction,tolerance_atr=.45):
    if not mss:return {"valid":False,"reason":"NO_MSS_BOS"}
    level=_f(mss["level"]); r=df.iloc[-1]; i=len(df)-1; tol=_atr(df,i)*tolerance_atr
    if direction=="BUY":touched=_f(r.low)<=level+tol;held=_f(r.close)>=level;confirm=_f(r.close)>_f(r.open)
    else:touched=_f(r.high)>=level-tol;held=_f(r.close)<=level;confirm=_f(r.close)<_f(r.open)
    continuation=i>mss["index"] and ((_f(r.close)>level) if direction=="BUY" else (_f(r.close)<level))
    valid=(touched and held and confirm) or (continuation and i-mss["index"]<=3 and confirm)
    return {"valid":bool(valid),"level":level,"touched":bool(touched),"held":bool(held),"confirmation":bool(confirm),"continuation":bool(continuation),"reason":None if valid else "WAITING_FOR_PULLBACK_CONFIRMATION"}

def _target_liquidity(df,direction,entry,lookback=120):
    x=df.iloc[:-1].tail(lookback)
    vals=sorted([_f(v) for v in (x.high if direction=="BUY" else x.low) if (_f(v)>entry if direction=="BUY" else _f(v)<entry)],reverse=direction=="SELL")
    return vals[0] if vals else None

def execution_price(raw,side):
    adverse=max(_f(SPREAD)/2+_f(SLIPPAGE),0);p=_f(raw);return p+adverse if side=="BUY" else p-adverse

def _candle_pattern(df,direction):
    if df is None or len(df)<25:return None
    x=df.reset_index(drop=True);r=x.iloc[-1];p=x.iloc[-2];i=len(x)-1;atr=_atr(x,i)
    o,h,l,c=map(float,(r.open,r.high,r.low,r.close));po,ph,pl,pc=map(float,(p.open,p.high,p.low,p.close));body=abs(c-o);rng=max(h-l,1e-12);upper=h-max(o,c);lower=min(o,c)-l;prev=abs(pc-po)
    if direction=="BUY":
        if c>o and pc<po and o<=pc and c>=po and body>=max(prev*.9,atr*.2):return {"name":"BULLISH_ENGULFING","direction":"BUY","index":i,"strength":"CLEAR"}
        if c>o and lower>=max(body*2,atr*.35) and upper<=body*.8 and (c-l)/rng>=.65:return {"name":"BULLISH_PIN_BAR","direction":"BUY","index":i,"strength":"CLEAR"}
        if c>ph and body>=max(atr*.25,rng*.35):return {"name":"BULLISH_BREAKOUT","direction":"BUY","index":i,"strength":"CLEAR"}
    else:
        if c<o and pc>po and o>=pc and c<=po and body>=max(prev*.9,atr*.2):return {"name":"BEARISH_ENGULFING","direction":"SELL","index":i,"strength":"CLEAR"}
        if c<o and upper>=max(body*2,atr*.35) and lower<=body*.8 and (h-c)/rng>=.65:return {"name":"BEARISH_PIN_BAR","direction":"SELL","index":i,"strength":"CLEAR"}
        if c<pl and body>=max(atr*.25,rng*.35):return {"name":"BEARISH_BREAKOUT","direction":"SELL","index":i,"strength":"CLEAR"}
    return None

def build_trade_levels(df,index,direction,invalidation,target,pattern=None):
    if target is None:return {"valid":False,"reason":"LEVELS_UNAVAILABLE"}
    entry=execution_price(df.iloc[index].close,direction);atr=_atr(df,index)
    if invalidation is None:invalidation=_f(df.iloc[index].low if direction=="BUY" else df.iloc[index].high)
    buffer=max(atr*.12,1e-9);sl=_f(invalidation)-buffer if direction=="BUY" else _f(invalidation)+buffer;tp=_f(target)
    if direction=="BUY" and not sl<entry<tp:return {"valid":False,"reason":"INVALID_LEVEL_ORDER"}
    if direction=="SELL" and not sl>entry>tp:return {"valid":False,"reason":"INVALID_LEVEL_ORDER"}
    risk=abs(entry-sl);reward=abs(tp-entry);rr=reward/risk if risk else 0
    if rr<MIN_RISK_REWARD:return {"valid":False,"reason":"RR_BELOW_2R","entry":entry,"sl":sl,"tp":tp,"risk":risk,"reward":reward,"risk_reward":rr}
    return {"valid":True,"entry":round(entry,8),"sl":round(sl,8),"tp":round(tp,8),"risk":round(risk,8),"reward":round(reward,8),"risk_reward":round(rr,3),"effective_rr":round(rr,3),"source":"structure_v9"}

def analyze_structure_setup(m5,m15,h1,index=None):
    if index is None:index=len(m5)-1
    m5=m5.iloc[:index+1].reset_index(drop=True)
    if len(m5)<80 or len(m15)<60 or len(h1)<60:return {"signal":"NO_TRADE","engine_version":ENGINE_VERSION,"valid":False,"rejection_reasons":["INSUFFICIENT_CONTEXT"]}
    h1s=_structure(h1);m15s=_structure(m15);direction=h1s["bias"] if h1s["bias"] in ("BUY","SELL") else m15s["bias"]
    if direction not in ("BUY","SELL"):return {"signal":"NO_TRADE","engine_version":ENGINE_VERSION,"valid":False,"rejection_reasons":["NO_DIRECTIONAL_STRUCTURE"],"structure_bias":h1s,"m15_structure":m15s}
    reasons=[]
    if m15s["bias"] in ("BUY","SELL") and m15s["bias"]!=direction:reasons.append("M15_OPPOSES_H1")
    loc=_location(m15,direction)
    if not loc["valid"]:reasons.append("M15_LOCATION_INVALID")
    pattern=_candle_pattern(m5,direction)
    if not pattern:reasons.append("NO_CLEAR_M5_PATTERN")
    sweep=_find_sweep(m5,direction);mss=_find_mss(m5,sweep,direction)
    if sweep and not mss:mss=_find_mss(m5,sweep,direction,window=16)
    confirmations=[]
    if sweep:confirmations.append("LIQUIDITY_SWEEP")
    if mss:confirmations.append("MSS_BOS")
    if pattern:confirmations.append("CLEAR_M5_PATTERN")
    retest=_retest(m5,mss,direction) if mss else {"valid":False,"reason":"NO_MSS_BOS_CONFIRMATION_OPTIONAL"}
    entry=_f(m5.iloc[-1].close);target=_target_liquidity(m5,direction,entry)
    if target is None:reasons.append("NO_LIQUIDITY_TARGET")
    invalidation=sweep["extreme"] if sweep else None;levels=build_trade_levels(m5,len(m5)-1,direction,invalidation,target,pattern)
    if not levels.get("valid"):reasons.append(levels.get("reason","LEVELS_INVALID"))
    signal=direction if not reasons else "NO_TRADE";pname=(pattern or {}).get("name","NONE");sidx=sweep.get("index") if sweep else "NO_SWEEP";midx=mss.get("index") if mss else "NO_MSS"
    return {"signal":signal,"engine_version":ENGINE_VERSION,"valid":signal in ("BUY","SELL") and levels.get("valid",False),"structure_bias":h1s,"m15_structure":m15s,"location":loc,"pattern":pattern,"pattern_valid":bool(pattern),"confirmations":confirmations,"liquidity_event":sweep,"m5_trigger":mss,"pullback":retest,"target_liquidity":target,"invalidation":invalidation,"trade_levels":levels,"setup_key":f"{direction}:{pname}:{sidx}:{midx}","rejection_reasons":reasons}

def calculate_trade_levels(df,i,direction,entry_price=None):
    s=analyze_structure_setup(df,df,df,i);return s["trade_levels"] if s.get("valid") and s.get("signal")==direction else {"valid":False,"reason":"NO_VALID_STRUCTURE_SETUP"}

def calculate_indicators(df):
    x=df.copy();c=pd.to_numeric(x.close,errors="coerce");x["ema20"]=c.ewm(span=20,adjust=False).mean();x["ema50"]=c.ewm(span=50,adjust=False).mean();h=pd.to_numeric(x.high,errors="coerce");l=pd.to_numeric(x.low,errors="coerce");prev=c.shift(1);tr=pd.concat([h-l,(h-prev).abs(),(l-prev).abs()],axis=1).max(axis=1);x["atr14"]=tr.rolling(14,min_periods=3).mean();return x

def remove_incomplete_last_candle(df,timeframe_minutes=5):
    if df is None or len(df)==0 or "datetime" not in df.columns:return df
    x=df.copy();ts=pd.to_datetime(x.datetime,utc=True,errors="coerce");cutoff=pd.Timestamp.now(tz="UTC").floor(f"{int(timeframe_minutes)}min");return x.loc[ts<cutoff].reset_index(drop=True)

def resolve_trade(direction,entry,sl,tp,future):
    risk=abs(float(entry)-float(sl));rr=abs(float(tp)-float(entry))/risk if risk else 0
    for _,r in future.iterrows():
        h,l=float(r.high),float(r.low);hit_sl=(l<=sl) if direction=="BUY" else (h>=sl);hit_tp=(h>=tp) if direction=="BUY" else (l<=tp);when=str(r.get("datetime",""))
        if hit_sl and hit_tp:return "AMBIGUOUS",0.0,when
        if hit_tp:return "WIN",rr,when
        if hit_sl:return "LOSS",-1.0,when
    return "OPEN",None,None

def evaluate_live_risk_guard(*args,**kwargs):
    reasons=[]
    for actual,env in (("price_jump_atr","LIVE_MAX_PRICE_JUMP_ATR"),("daily_loss_r","LIVE_MAX_DAILY_LOSS_R"),("slippage","LIVE_MAX_SLIPPAGE")):
        try:v=float(kwargs.get(actual,0));m=float(os.getenv(env,"0"))
        except (TypeError,ValueError):v=m=0
        if m>0 and v>m:reasons.append(f"{actual.upper()}_LIMIT")
    for actual,env in (("consecutive_losses","LIVE_MAX_CONSECUTIVE_LOSSES"),("trades_today","LIVE_MAX_TRADES_PER_DAY")):
        try:v=int(kwargs.get(actual,0));m=int(os.getenv(env,"0"))
        except (TypeError,ValueError):v=m=0
        if m>0 and v>m:reasons.append(f"{actual.upper()}_LIMIT")
    return {"allowed":not reasons,"valid":not reasons,"blocked":bool(reasons),"reasons":reasons}

def send_telegram(message):
    token=os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN");chat_id=os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHATID")
    if not token or not chat_id:return {"success":False,"error":"Telegram credentials not configured"}
    try:
        r=requests.post(f"https://api.telegram.org/bot{token}/sendMessage",json={"chat_id":chat_id,"text":str(message),"parse_mode":"HTML","disable_web_page_preview":True},timeout=15);data=r.json();return {"success":bool(r.ok and data.get("ok")),"status_code":r.status_code,"response":data}
    except Exception as exc:return {"success":False,"error_type":type(exc).__name__,"error":str(exc)}

base=None
