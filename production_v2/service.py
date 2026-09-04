from __future__ import annotations

from datetime import datetime, timezone
import os
import threading
import time
import traceback
from zoneinfo import ZoneInfo

from .live_data import LiveMarketData
from .market_data import normalize_market_data
from .notifications.no_trade import send_no_trade
from .notifications.telegram import format_startup, format_status, send, send_decision
from .pipeline import ProductionPipeline
from .statistics import store

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")


def _pipeline_trace_fields(result) -> dict[str, object]:
    return {"state": getattr(result, "state", "ANALYSIS_COMPLETE_NO_TRADE"), "blocked_by": getattr(result, "blocked_by", None), "wait_bars": int(getattr(result, "wait_bars", 0) or 0)}


class LiveService:
    def __init__(self):
        self.pipeline = ProductionPipeline(); self.data = LiveMarketData()
        self.interval = int(os.getenv("SIGNAL_INTERVAL_SECONDS", "60")); self.status_interval_seconds = int(os.getenv("STATUS_INTERVAL_SECONDS", "900")); self.max_candle_age_seconds = int(os.getenv("MAX_CANDLE_AGE_SECONDS", "600"))
        self._started = False; self._last_candle={}; self._last_status_slot=None; self._runtime_errors={}; self._last_prices={}; self._latest_results={}; self._last_no_trade_slot=None

    def start(self):
        if self._started: return
        self._started=True; send(format_startup(list(self.data.symbols().keys()))); threading.Thread(target=self._loop,name="production-v2-scheduler",daemon=True).start()

    def _send_status(self, now):
        market_states={}
        for alias in self.data.symbols():
            try: market_states[alias]="MARKET_OPEN" if self.data.market_is_open(alias,now) else "MARKET_CLOSED"
            except Exception as exc: market_states[alias]="MARKET_STATUS_UNKNOWN"; self._runtime_errors[alias]=f"market status: {exc}"
        send(format_status({"prices":dict(self._last_prices),"market_states":market_states,"timeframe":"M5","timestamp":now,"architecture":"E1 -> E2 -> E3 -> E4 -> E5 -> E6 -> E7 -> E8 -> E9"})); self._last_status_slot=now.strftime("%Y%m%d%H%M")

    def _send_aligned_status(self):
        now=datetime.now(BANGKOK_TZ)
        if now.minute%15: return
        slot=now.strftime("%Y%m%d%H%M")
        if slot==self._last_status_slot: return
        try: self._send_status(now)
        except Exception as exc: print(f"[PRODUCTION V2] Telegram status error: {exc}",flush=True)

    def _send_aligned_no_trade(self):
        now=datetime.now(BANGKOK_TZ)
        if now.minute%10: return
        slot=now.strftime("%Y%m%d%H%M")
        if slot==self._last_no_trade_slot: return
        symbols=self.data.symbols(); market_open={}
        for alias in symbols:
            try: market_open[alias]=self.data.market_is_open(alias,now)
            except Exception as exc: market_open[alias]=False; self._runtime_errors[alias]=f"market status: {exc}"
        active={a:r for a,r in self._latest_results.items() if a in symbols and market_open.get(a,False)}
        if not active or any(getattr(r,"decision",None) in {"BUY","SELL"} and bool(getattr(r,"gate_passed",False)) for r in active.values()): self._last_no_trade_slot=slot; return
        try: send_no_trade(dict(active),now); self._last_no_trade_slot=slot
        except Exception as exc: print(f"[PRODUCTION V2] Telegram no-trade error: {exc}",flush=True)

    @staticmethod
    def _candle_age_seconds(candle):
        try:
            timestamp=datetime.fromisoformat(candle.replace("Z","+00:00")); timestamp=timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc); return max(0.0,(datetime.now(timezone.utc)-timestamp).total_seconds())
        except (TypeError,ValueError): return None

    def _trace_result(self,alias,result):
        t=_pipeline_trace_fields(result); print(f"[PRODUCTION V2] {alias} PIPELINE decision={result.decision} state={t['state']} blocked_by={t['blocked_by']} wait_bars={t['wait_bars']} gate={result.gate_passed} engines={len(result.engines)}",flush=True)
        for engine in result.engines:
            if engine.engine_id=="E9":
                r=engine.output.get("professional_reasoning") or {}; print(f"[PRODUCTION V2] {alias} E9 MASTER decision={engine.output.get('decision',result.decision)} reason={engine.output.get('decision_reasons',list(engine.reason_codes))} thesis={r.get('primary_thesis','UNRESOLVED')} conflicts={r.get('conflicts',[])} invalidations={r.get('hard_invalidations',[])}",flush=True)
            else: print(f"[PRODUCTION V2] {alias} {engine.engine_id} reasons={list(engine.reason_codes or [])}",flush=True)

    def _loop(self):
        while True:
            for alias in self.data.symbols():
                try:
                    raw=self.data.candles(alias)
                    if raw.get("market_state")=="MARKET_CLOSED" and not raw.get("bars"):
                        self._runtime_errors.pop(alias,None); print(f"[PRODUCTION V2] {alias} MARKET_CLOSED action=SKIP_EVALUATION",flush=True); continue
                    payload=normalize_market_data(raw)
                    if payload["bars"]: self._last_prices[alias]=payload["bars"][-1]["close"]; store.update_price(alias,self._last_prices[alias])
                    candle=payload.get("candle_close_timestamp") or ""
                    if not candle: self._runtime_errors[alias]="missing candle timestamp"; continue
                    age=self._candle_age_seconds(candle)
                    if age is not None and age>self.max_candle_age_seconds:
                        print(f"[PRODUCTION V2] {alias} STALE_CANDLE candle={candle} age_seconds={int(age)} action=SKIP_EVALUATION",flush=True); self._runtime_errors[alias]=f"stale candle: {candle}"; continue
                    if self._last_candle.get(alias)==candle:
                        print(f"[PRODUCTION V2] {alias} DUPLICATE_CANDLE candle={candle} action=SKIP_EVALUATION",flush=True); continue
                    self._last_candle[alias]=candle; print(f"[PRODUCTION V2] {alias} LSE M5 new closed candle bars={len(raw.get('bars') or [])} candle={candle}",flush=True)
                    print(f"[PRODUCTION V2] {alias} PIPELINE_STAGE ENTER E6_E7_E8_E9 candle={candle}",flush=True)
                    result=self.pipeline.run(payload)
                    print(f"[PRODUCTION V2] {alias} PIPELINE_STAGE EXIT E6_E7_E8_E9 candle={candle}",flush=True)
                    self._runtime_errors.pop(alias,None); self._latest_results[alias]=result; store.record(result,self._last_prices.get(alias)); self._trace_result(alias,result)
                    if result.decision in {"BUY","SELL"} and result.gate_passed: send_decision(result)
                except Exception as exc:
                    self._runtime_errors[alias]=f"{type(exc).__name__}: {exc}"; print(f"[PRODUCTION V2] {alias} PIPELINE_EXCEPTION type={type(exc).__name__} message={exc}",flush=True); traceback.print_exc()
            self._send_aligned_no_trade(); self._send_aligned_status(); time.sleep(self.interval)

_service=None

def start_live_service():
    global _service
    if _service is None: _service=LiveService()
    _service.start()
