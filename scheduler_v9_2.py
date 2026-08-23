"""V9.2 scheduler adapter using the V9.2 scanner."""
import scheduler_v9 as _base
import live_scanner_v9_2
_base._scanner = lambda: live_scanner_v9_2
_base._notify_error = _base._notify_error
run_scan_cycle = _base.run_scan_cycle
start = _base.start
stop = _base.stop
status = _base.status
_asset_market_status = _base._asset_market_status
_symbols = _base._symbols
_interval_seconds = _base._interval_seconds
_original_status = status

def status():
    payload = _original_status()
    payload["engine_version"] = "V9.2"
    payload["scanner"] = "live_scanner_v9_2"
    return payload
