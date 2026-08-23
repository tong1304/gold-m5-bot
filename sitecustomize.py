"""Runtime safety overrides loaded automatically by Python before the app.

Keeps the live engine at minimum 2R and, when the Render/Gunicorn process
starts with an empty signal database, launches one isolated V8 historical
replay so /statistics has real data to display. The replay subprocess is
marked so it cannot recursively bootstrap itself.
"""
import os
import sys
import threading
import subprocess
from datetime import datetime, timedelta

try:
    import engine_v42 as _base
    _base.MIN_RISK_REWARD = 2.0
    _base.RISK_REWARD = 2.0
except Exception:
    pass


def _bootstrap_statistics():
    if os.getenv("SIGNAL_HISTORY_BOOTSTRAP_CHILD") == "1":
        return
    if os.getenv("DISABLE_STATISTICS_BOOTSTRAP", "false").strip().lower() == "true":
        return
    argv = " ".join(sys.argv).lower()
    if "gunicorn" not in argv:
        return
    try:
        from signal_history import history
        if history.list_signals(days=3650, limit=1):
            return
    except Exception:
        return

    lock_path = os.getenv("SIGNAL_HISTORY_BOOTSTRAP_LOCK", "signal_history_bootstrap.lock")
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        return
    except Exception:
        return

    def run():
        try:
            end = datetime.utcnow().date()
            start = end - timedelta(days=int(os.getenv("STATISTICS_BOOTSTRAP_DAYS", "30")))
            env = os.environ.copy()
            env["SIGNAL_HISTORY_BOOTSTRAP_CHILD"] = "1"
            cmd = [sys.executable, "-u", "replay_signal_history.py",
                   "--start", start.isoformat(), "--end", end.isoformat(), "--symbol", "ALL"]
            proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                print("[STATISTICS BOOTSTRAP] " + line.rstrip(), flush=True)
            code = proc.wait()
            print(f"[STATISTICS BOOTSTRAP] replay finished rc={code}", flush=True)
        except Exception as exc:
            print(f"[STATISTICS BOOTSTRAP] failed: {type(exc).__name__}: {exc}", flush=True)

    threading.Thread(target=run, name="statistics-bootstrap", daemon=True).start()


try:
    _bootstrap_statistics()
except Exception:
    pass
