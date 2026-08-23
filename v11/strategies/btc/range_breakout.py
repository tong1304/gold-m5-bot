from ...common import candle_metrics
from ...contracts import StrategyResult

def evaluate(m5,direction,context=None):
    x=m5.tail(31).reset_index(drop=True); last=candle_metrics(x.iloc[-1]); p=x.iloc[:-1].tail(20); hi=float(p.high.max()); lo=float(p.low.min()); broken=last["close"]>hi if direction=="BUY" else last["close"]<lo; side=last["bull"] if direction=="BUY" else last["bear"]; reasons=[]
    if not broken:reasons.append("RANGE_BOUNDARY_NOT_BROKEN")
    if not side:reasons.append("BREAKOUT_CANDLE_DIRECTION_FAILED")
    if last["body_ratio"]<.30:reasons.append("BREAKOUT_BODY_TOO_SMALL")
    return StrategyResult.pass_("RANGE_BREAKOUT",direction,{"range_high":hi,"range_low":lo,"body_ratio":last["body_ratio"]}) if not reasons else StrategyResult.fail("RANGE_BREAKOUT",direction,reasons,{"range_high":hi,"range_low":lo,"body_ratio":last["body_ratio"]})
