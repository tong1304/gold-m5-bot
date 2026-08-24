import os
import tempfile
import pandas as pd
from v11.data_quality import validate_frame, require_closed
from v11.selection import select
from v11.risk import calculate
from signal_history import SignalHistory

def frame(n=80, start="2026-08-24 00:00:00"):
    ts=pd.date_range(start,periods=n,freq="5min",tz="UTC")
    close=pd.Series(range(100,n+100),dtype=float)
    return pd.DataFrame({"datetime":ts,"open":close-0.2,"high":close+1,"low":close-1,"close":close})

def test_data_quality_rejects_duplicates_and_bad_ohlc():
    df=frame(); df.loc[10,"datetime"]=df.loc[9,"datetime"]; df.loc[20,"high"]=df.loc[20,"low"]-1
    reasons=validate_frame(df,minimum=60,timeframe_minutes=5)
    assert "DUPLICATE_DATETIME" in reasons and "OHLC_INCONSISTENT" in reasons

def test_require_closed_removes_current_candle():
    df=frame(); now=df.iloc[-1].datetime+pd.Timedelta(minutes=4)
    out=require_closed(df,timeframe_minutes=5,now=now)
    assert out.iloc[-1].datetime < now.floor("5min")

def test_selection_is_not_registry_order():
    candidates=[{"strategy":"Z","direction":"BUY","status":"PASS","quality":60,"freshness_bars":2},{"strategy":"A","direction":"BUY","status":"PASS","quality":80,"freshness_bars":3}]
    assert select(candidates,"BUY")["strategy"]=="A"

def test_risk_is_at_least_two_r():
    df=frame(); result=calculate(df,"BUY","TEST",{"support":175})
    assert result["valid"] and result["risk_reward"]>=2.0 and result["sl"]<result["entry"]<result["tp"]

def test_risk_uses_latest_structural_support_below_entry():
    df=frame(80)
    df.loc[70:74,"low"]=[169,168,167,168,169]
    df.loc[75:79,"low"]=[179,180,181,180,179]
    df.loc[79,"close"]=180.0
    result=calculate(df,"BUY","TEST")
    assert result["valid"]
    assert result["support"] == 167.0
    assert result["sl"] < 167.0
    assert result["tp"] == result["entry"] + 2.0 * result["risk"]

def test_risk_uses_latest_structural_resistance_above_entry():
    df=frame(80)
    df.loc[70:74,"high"]=[189,188,187,188,189]
    df.loc[75:79,"high"]=[181,180,179,180,181]
    df.loc[79,"close"]=180.0
    result=calculate(df,"SELL","TEST")
    assert result["valid"]
    assert result["resistance"] == 187.0
    assert result["sl"] > 187.0
    assert result["tp"] == result["entry"] - 2.0 * result["risk"]

def test_risk_does_not_override_two_r_with_target_price():
    df=frame(); result=calculate(df,"BUY","TEST",{"target_price":9999})
    assert result["valid"]
    assert result["tp"] == result["entry"] + 2.0 * result["risk"]

def test_history_dedup_is_atomic():
    with tempfile.TemporaryDirectory() as d:
        h=SignalHistory(os.path.join(d,"signals.db")); payload={"signal_id":"X","symbol":"BTC","signal":"BUY","closed_candle":"2026-08-24T00:00:00+00:00","created_at":"2026-08-24T00:05:00+00:00","trade_levels":{"entry":100,"sl":99,"tp":102}}
        assert h.record_signal(payload) is True
        assert h.record_signal(payload) is False
        assert h.get("X")["result"]=="OPEN"
