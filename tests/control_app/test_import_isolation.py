from __future__ import annotations

import subprocess
import sys


def test_import_does_not_start_scheduler_or_live_price():
    code = "import threading; import control_app; print([t.name for t in threading.enumerate()])"
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    output = completed.stdout.lower()
    assert "scheduler" not in output
    assert "live-price" not in output
    assert "live_price" not in output
