from ...common import candle_metrics, atr14
from ...contracts import StrategyResult

def evaluate(m5,direction,context=None):
    x=m5.tail(45).reset_index(drop=True); a=float(atr14(x).iloc[-1]); last=candle_metrics(x.iloc[-1]); p=x.iloc[:-1].tail(20); hi=float(p.high.max()); lo=float(p.low.min()); reasons=[]
    ok=(last["low"]<=lo+a*.20 and last["close"]>lo and last["lower_wick"]>=last["body"]*1.2) if direction=="BUY" else (last["high"]>=hi-a*.20 and last["close"]<hi and last["upper_wick"]>=last["body"]*1.2)
    if not ok:reasons.append("SR_REVERSAL_REJECTION_NOT_CONFIRMED")
    return StrategyResult.pass_("SR_REVERSAL",direction,{"support":lo,"resistance":hi,"atr":a}) if not reasons else StrategyResult.fail("SR_REVERSAL",direction,reasons,{"support":lo,"resistance":hi,"atr":a})
