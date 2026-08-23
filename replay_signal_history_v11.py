"""V11 DATE_RANGE replay adapter.

Uses the corrected V10.3 LSE date-only fetcher but swaps its decision engine for V11.
This keeps Bangkok calendar-date replay and warm-up behavior while ensuring the
exact same strategy-split engine is used by Live and Replay.
"""
from replay_signal_history_v10_3 import *
import replay_signal_history_v10_3 as _legacy
from v11 import engine as engine

engine.ENGINE_VERSION="11.0-M5-M15-STRATEGY-SPLIT"
_legacy.engine=engine

def replay_symbol(symbol,start,end,dry_run=False):
    return _legacy.replay_symbol(symbol,start,end,dry_run)

def main():
    _legacy.engine=engine
    return _legacy.main()

if __name__ == "__main__": main()
