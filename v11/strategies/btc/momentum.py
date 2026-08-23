from ...common import candle_metrics, atr14, momentum_move
from ...contracts import StrategyResult

def evaluate(m5,direction,context=None):
    x=m5.tail(25).reset_index(drop=True); last=candle_metrics(x.iloc[-1]); a=float(atr14(x).iloc[-1]); move=momentum_move(x,5); reasons=[]
    if not (move>a if direction=="BUY" else move<-a):reasons.append("MOMENTUM_MOVE_BELOW_ATR")
    if not ((last["bull"] and last["body_ratio"]>=.45) if direction=="BUY" else (last["bear"] and last["body_ratio"]>=.45)):reasons.append("MOMENTUM_BODY_STRENGTH_FAILED")
    return StrategyResult.pass_("MOMENTUM",direction,{"move":move,"atr":a,"body_ratio":last["body_ratio"]}) if not reasons else StrategyResult.fail("MOMENTUM",direction,reasons,{"move":move,"atr":a,"body_ratio":last["body_ratio"]})
