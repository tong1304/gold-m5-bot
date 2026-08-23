from ...common import candle_metrics, atr14
from ...contracts import StrategyResult

def evaluate(m5,direction,context=None):
    x=m5.tail(60).reset_index(drop=True); a=float(atr14(x).iloc[-1]); last=candle_metrics(x.iloc[-1]); reasons=[]; found=False; level=None
    for j in range(max(20,len(x)-10),len(x)-1):
        p=x.iloc[max(0,j-20):j]; lv=float(p.high.max()) if direction=="BUY" else float(p.low.min()); b=candle_metrics(x.iloc[j]); broke=(b["close"]>lv and b["bull"]) if direction=="BUY" else (b["close"]<lv and b["bear"])
        if broke:
            level=lv; found=(last["low"]<=lv+a*.55 and last["close"]>=lv) if direction=="BUY" else (last["high"]>=lv-a*.55 and last["close"]<=lv)
            break
    if not found:reasons.append("BREAKOUT_RETEST_SEQUENCE_NOT_CONFIRMED")
    return StrategyResult.pass_("BREAKOUT_RETEST",direction,{"level":level,"atr":a}) if not reasons else StrategyResult.fail("BREAKOUT_RETEST",direction,reasons,{"level":level,"atr":a})
