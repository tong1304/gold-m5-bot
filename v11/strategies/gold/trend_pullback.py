from ...common import candle_metrics, atr14, ema
from ...contracts import StrategyResult

def evaluate(m5,direction,context=None):
    x=m5.tail(60).reset_index(drop=True); a=float(atr14(x).iloc[-1]); e20=ema(x,20); e50=ema(x,50); last=candle_metrics(x.iloc[-1]); reasons=[]
    aligned=last["close"]>e20.iloc[-1]>e50.iloc[-1] if direction=="BUY" else last["close"]<e20.iloc[-1]<e50.iloc[-1]
    touch=any((x.low.iloc[i]<=e20.iloc[i]+a*.35) if direction=="BUY" else (x.high.iloc[i]>=e20.iloc[i]-a*.35) for i in range(max(0,len(x)-12),len(x)))
    if not aligned:reasons.append("EMA20_EMA50_ALIGNMENT_FAILED")
    if not touch:reasons.append("NO_EMA20_PULLBACK_TOUCH")
    return StrategyResult.pass_("TREND_PULLBACK",direction,{"atr":a}) if not reasons else StrategyResult.fail("TREND_PULLBACK",direction,reasons,{"atr":a})
