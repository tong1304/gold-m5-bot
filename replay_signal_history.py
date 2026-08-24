"""V12 historical replay entry point."""
from __future__ import annotations
import json
from replay_signal_history_v11 import main

if __name__ == "__main__":
    # The underlying replay implementation uses the V12 engine contract.
    result = main()
    print(json.dumps(result, ensure_ascii=False, default=str, allow_nan=False), flush=True)
