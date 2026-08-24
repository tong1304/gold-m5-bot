from ...common import candle_metrics, atr14, ema
from ...contracts import StrategyResult

def evaluate(m5,direction,context=None):
    x=m5.tail(60).reset_index(drop=True); a=float(atr14(x).iloc[-1]); e20=ema(x,20); e50=ema(x,50); last=candle_metrics(x.iloc[-1]); reasons=[]
    aligned=last["close"]>e20.iloc[-1]>e50.iloc[-1] if direction=="BUY" else last["close"]<e20.iloc[-1]<e50.iloc[-1]
    touches=[]
    for i in range(max(0,len(x)-4),len(x)):
        touched=(x.low.iloc[i]<=e20.iloc[i]+a*.35) if direction=="BUY" else (x.high.iloc[i]>=e20.iloc[i]-a*.35)
        if touched: touches.append(len(x)-1-i)
    freshness=min(touches) if touches else 999
    if not aligned:reasons.append("EMA20_EMA50_ALIGNMENT_FAILED")
    if not touches:reasons.append("NO_FRESH_EMA20_PULLBACK_TOUCH")
    if freshness>3:reasons.append("PULLBACK_SETUP_STALE")
    evidence={"atr":a,"freshness_bars":freshness,"setup_timestamp":str(x.iloc[-1].datetime) if "datetime" in x.columns else None}
    if not reasons:return StrategyResult.pass_("TREND_PULLBACK",direction,evidence,quality=70.0,freshness_bars=freshness,setup_timestamp=evidence["setup_timestamp"])
    return StrategyResult.fail("TREND_PULLBACK",direction,reasons,evidence)
