from ...common import candle_metrics, atr14
from ...contracts import StrategyResult

def evaluate(m5,direction,context=None):
    x=m5.tail(50).reset_index(drop=True); aa=atr14(x); a=float(aa.iloc[-1]); med=float(aa.dropna().tail(30).median()) if aa.notna().any() else 0; last=candle_metrics(x.iloc[-1]); p=x.iloc[:-1].tail(20); hi=float(p.high.max()); lo=float(p.low.min()); reasons=[]
    if med<=0 or a/med<1.25:reasons.append("VOLATILITY_EXPANSION_BELOW_1.25X")
    if not (last["close"]>hi if direction=="BUY" else last["close"]<lo):reasons.append("BREAKOUT_BOUNDARY_NOT_BROKEN")
    if not (last["bull"] if direction=="BUY" else last["bear"]):reasons.append("BREAKOUT_CANDLE_DIRECTION_FAILED")
    return StrategyResult.pass_("VOLATILITY_BREAKOUT",direction,{"atr":a,"atr_ratio":a/max(med,1e-9)}) if not reasons else StrategyResult.fail("VOLATILITY_BREAKOUT",direction,reasons,{"atr":a,"atr_ratio":a/max(med,1e-9)})
