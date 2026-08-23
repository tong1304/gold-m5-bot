"""V9.1 scheduler adapter using the V9.1 scanner."""
import scheduler_v9 as _base
import live_scanner_v9_1
_base._scanner=lambda: live_scanner_v9_1
_base._notify_error=_base._notify_error

# Re-export the existing scheduler API while its scanner dependency is V9.1.
run_scan_cycle=_base.run_scan_cycle
start=_base.start
stop=_base.stop
status=_base.status
_asset_market_status=_base._asset_market_status
_symbols=_base._symbols
_interval_seconds=_base._interval_seconds

# Keep status truthful about the active engine version.
_original_status=status
def status():
    payload=_original_status(); payload["engine_version"]="V9.1"; payload["scanner"]="live_scanner_v9_1"; return payload
