from ...common import candle_metrics, atr14
from ...contracts import StrategyResult

def evaluate(m5,direction,context=None):
    x=m5.tail(35).reset_index(drop=True); a=float(atr14(x).iloc[-1]); last=candle_metrics(x.iloc[-1]); p=x.iloc[:-1].tail(12); hi=float(p.high.max()); lo=float(p.low.min()); reasons=[]
    ok=(last["low"]<lo-a*.05 and last["close"]>lo and last["bull"]) if direction=="BUY" else (last["high"]>hi+a*.05 and last["close"]<hi and last["bear"])
    if not ok:reasons.append("LIQUIDITY_SWEEP_REJECTION_NOT_CONFIRMED")
    return StrategyResult.pass_("LIQUIDITY_SWEEP",direction,{"sweep_high":hi,"sweep_low":lo,"atr":a}) if not reasons else StrategyResult.fail("LIQUIDITY_SWEEP",direction,reasons,{"sweep_high":hi,"sweep_low":lo,"atr":a})
