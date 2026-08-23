"""V11 DATE_RANGE replay adapter.

Uses the corrected LSE date-only fetcher while swapping its decision engine for
V11. Replay is candle-closed: for each M5 candle, M15 context is limited to the
latest M15 candle that was already closed at that M5 candle's close time. This
prevents future M15 candles from leaking into the historical test.
"""
from __future__ import annotations
from datetime import timedelta
import pandas as pd
from replay_signal_history_v10_3 import *
import replay_signal_history_v10_3 as _legacy
from v11 import engine as engine

engine.ENGINE_VERSION="11.0-M5-M15-STRATEGY-SPLIT"
engine.MIN_RISK_REWARD=2.0
engine.RISK_REWARD=2.0
_legacy.engine=engine


def _closed_m15_context(frame, ts):
    """Return only M15 candles closed by the M5 candle represented by ts.

    LSE candle timestamps are candle-open timestamps. A 15m candle stamped
    18:45 closes at 19:00, so an M5 candle stamped 18:50 may only use M15 data
    through 18:30. The live scanner follows the same closed-candle rule.
    """
    available_through=pd.Timestamp(ts)-timedelta(minutes=15)
    return frame[frame.datetime<=available_through].reset_index(drop=True)


# replay_signal_history_v10_3.replay_symbol resolves its helper through the
# module global, so replace that helper before delegating. The V10.3 engine
# object itself is also replaced above; no separate V10 strategy is evaluated.
_legacy._context=_closed_m15_context


def replay_symbol(symbol,start,end,dry_run=False):
    result=_legacy.replay_symbol(symbol,start,end,dry_run)
    if isinstance(result,dict):
        result["engine_version"]=engine.ENGINE_VERSION
        result["replay_source"]="LSE_HISTORICAL_OHLCV_V11"
        result["m15_alignment"]="CLOSED_AT_M5_CLOSE"
        result["minimum_risk_reward"]=2.0
    return result


def main():
    _legacy.engine=engine
    _legacy._context=_closed_m15_context
    return _legacy.main()

if __name__=="__main__": main()
