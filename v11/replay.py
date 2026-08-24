"""V12.1 replay compatibility entry point.

The historical replay contract is now H1 bias -> M15 regime -> M5 trigger.
Use v11.replay_m5 for the implementation; this module keeps the public replay
function importable for existing callers.
"""
from .replay_m5 import (
    REPLAY_M5_CONTEXT_BARS,
    REPLAY_M15_CONTEXT_BARS,
    REPLAY_H1_CONTEXT_BARS,
    normalize_replay_window,
    summarize_rows,
    replay_frames as _replay_frames,
)

def replay_frames(m5,m15,h1=None,symbol=None,**kwargs):
    return _replay_frames(m5,m15,h1,symbol,**kwargs)
