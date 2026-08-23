from ...common import candle_metrics, atr14, ema
from ...contracts import StrategyResult

def evaluate(m5,direction,context=None):
    x=m5.tail(30).reset_index(drop=True); e20=ema(x,20); a=float(atr14(x).iloc[-1]); prev=candle_metrics(x.iloc[-2]); last=candle_metrics(x.iloc[-1]); touch=(prev["low"]<=e20.iloc[-2]+a*.35) if direction=="BUY" else (prev["high"]>=e20.iloc[-2]-a*.35); confirm=(last["close"]>e20.iloc[-1]) if direction=="BUY" else (last["close"]<e20.iloc[-1]); reasons=[]
    if not touch:reasons.append("PREVIOUS_CANDLE_DID_NOT_TOUCH_EMA20")
    if not confirm:reasons.append("EMA20_DIRECTION_FAILED")
    return StrategyResult.pass_("EMA_PULLBACK",direction,{"ema20":float(e20.iloc[-1]),"atr":a}) if not reasons else StrategyResult.fail("EMA_PULLBACK",direction,reasons,{"ema20":float(e20.iloc[-1]),"atr":a})
