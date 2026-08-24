"""V11 historical replay entry point."""
from __future__ import annotations

import json

from replay_signal_history_v11 import main


if __name__ == "__main__":
    # The web replay worker parses the final JSON line from stdout.
    # Always emit the returned report so a successful subprocess is not
    # incorrectly classified as failed merely because stdout is empty.
    result = main()
    print(json.dumps(result, ensure_ascii=False, default=str, allow_nan=False), flush=True)
