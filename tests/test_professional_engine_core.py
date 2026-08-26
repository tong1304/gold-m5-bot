import numpy as np
import pandas as pd
from professional_engine_core import analyze, ENGINE_VERSION


def frame(n=220, slope=0.2):
    t=pd.date_range("2026-01-01",periods=n,freq="5min",tz="UTC")
    base=2000+np.arange(n)*slope
    return pd.DataFrame({"datetime":t,"open":base,"high":base+1,"low":base-1,"close":base+0.5,"volume":1000})


def test_engine_is_native_professional():
    x=frame()
    r=analyze(x,x,x,symbol="GOLD")
    assert r["engine_version"]==ENGINE_VERSION
    assert r["decision_authority"]=="E9"
    assert set(r["professional_decision"])=={"e1","e2","e3","e4","e5","e6","e7","e8","e9"}


def test_no_confirmation_cannot_authorize_trade():
    x=frame(slope=0.01)
    r=analyze(x,x,x,symbol="BTC")
    assert r["signal"]=="NO_TRADE"
    assert r["professional_decision"]["e9"]["execution_eligible"] is False
