import os
import subprocess
import sys


def test_app_import_exposes_runtime_routes_without_live_credentials():
    env = os.environ.copy()
    env["PRODUCTION_V2_DISABLE_LIVE"] = "1"
    env["PYTHONPATH"] = "."
    code = (
        "from production_v2.app import app; "
        "paths = {rule.rule for rule in app.url_map.iter_rules()}; "
        "required = {'/', '/health', '/statistics', '/api/statistics', '/signal'}; "
        "assert required <= paths, (required - paths, sorted(paths))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
