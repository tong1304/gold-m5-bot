"""V11 scheduler adapter."""
import scheduler_v9 as _base
import live_scanner_v11

_base._scanner=lambda: live_scanner_v11
run_scan_cycle=_base.run_scan_cycle
start=_base.start
stop=_base.stop
_asset_market_status=_base._asset_market_status
_symbols=_base._symbols
_interval_seconds=_base._interval_seconds
_original_status=_base.status

def status():
    payload=_original_status(); payload.update({"engine_version":"11.0-M5-M15-STRATEGY-SPLIT","scanner":"live_scanner_v11","multi_strategy":True,"timeframes":["5m","15m"]}); return payload
