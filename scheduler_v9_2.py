"""V10.0 scheduler adapter using the multi-strategy scanner."""
import scheduler_v9 as _base
import live_scanner_v9_2
_base._scanner = lambda: live_scanner_v9_2
run_scan_cycle = _base.run_scan_cycle
start = _base.start
stop = _base.stop
_asset_market_status = _base._asset_market_status
_symbols = _base._symbols
_interval_seconds = _base._interval_seconds
_original_status = status = _base.status

def status():
    payload = _original_status()
    payload["engine_version"] = "V10.0"
    payload["scanner"] = "live_scanner_v9_2"
    payload["multi_strategy"] = True
    return payload
