import pandas as pd
import v11.replay_m5 as replay

def _frame(rows,freq):
    return pd.DataFrame({"datetime":pd.date_range("2026-08-01",periods=rows,freq=freq,tz="UTC"),"open":[100.0]*rows,"high":[101.0]*rows,"low":[99.0]*rows,"close":[100.5]*rows,"volume":[1.0]*rows})

def test_replay_passes_only_bounded_mtf_history_to_engine(monkeypatch):
    m5=_frame(140,"5min");m15=_frame(140,"15min");h1=_frame(140,"1h");seen=[]
    def fake_analyze(m5_arg,m15=None,h1=None,symbol=None,setup_state=None,index=None):
        seen.append((len(m5_arg),len(m15),len(h1),index));return {"signal":"NO_TRADE","strategy":"NONE","valid":False,"trade_levels":{"valid":False}}
    monkeypatch.setattr(replay.engine,"analyze",fake_analyze)
    replay.replay_frames(m5,m15,h1,"BTC",start_time=m5.iloc[120].datetime,end_time=m5.iloc[125].datetime)
    assert seen
    assert all(m5_len<=100 and m15_len<=100 and h1_len<=100 for m5_len,m15_len,h1_len,_ in seen)
    assert all(index is None for *_,index in seen)
