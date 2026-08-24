from __future__ import annotations
from collections import defaultdict
from .replay import replay_frames
from . import engine

def validate(m5,m15,symbol,*,limit=1000):
    report=replay_frames(m5,m15,symbol,limit=limit);by=defaultdict(lambda:{"signals":0,"wins":0,"losses":0,"ambiguous":0,"open":0,"net_r":0.0})
    for row in report["rows"]:
        s=by[row.get("strategy","NONE")]
        if row.get("valid"):s["signals"]+=1
        result=row.get("result");
        if result in ("WIN","LOSS","AMBIGUOUS","OPEN"):s[result.lower()]+=1
        s["net_r"]+=float(row.get("r_multiple") or 0)
    report["validation_source"]="LSE_HISTORICAL_OHLCV";report["m15_policy"]="CLOSED_AT_M5_CLOSE_MINUS_15M";report["minimum_risk_reward"]=engine.MIN_RISK_REWARD;report["strategy_stats"]={k:{**v,"net_r":round(v["net_r"],4)} for k,v in by.items()};report["strategy_selection"]="REGIME_THEN_SETUP_SCORE_THEN_ENTRY_TRIGGER";return report
