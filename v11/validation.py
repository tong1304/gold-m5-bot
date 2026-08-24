from __future__ import annotations
from collections import defaultdict
from .replay_m5 import replay_frames
from . import engine
def validate(m5,m15=None,symbol=None,*,limit=1000):
    report=replay_frames(m5,None,symbol,limit=limit);by=defaultdict(lambda:{"signals":0,"wins":0,"losses":0,"ambiguous":0,"open":0,"net_r":0.0})
    for row in report["rows"]:
        s=by[row.get("strategy","NONE")]
        if row.get("valid"):s["signals"]+=1
        result=row.get("result")
        if result in ("WIN","LOSS","AMBIGUOUS","OPEN"):s[result.lower()]+=1
        s["net_r"]+=float(row.get("r_multiple") or 0)
    report["validation_source"]="LSE_HISTORICAL_M5_OHLCV";report["timeframe_mode"]="M5-only";report["minimum_risk_reward"]=engine.MIN_RISK_REWARD;report["strategy_stats"]={k:{**v,"net_r":round(v["net_r"],4)} for k,v in by.items()};report["strategy_selection"]="M5_REGIME_THEN_SETUP_SCORE_THEN_ENTRY_TRIGGER";return report
