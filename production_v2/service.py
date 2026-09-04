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
    return {
        "state": getattr(result, "state", "ANALYSIS_COMPLETE_NO_TRADE"),
        "blocked_by": getattr(result, "blocked_by", None),
        "wait_bars": int(getattr(result, "wait_bars", 0) or 0),
    }


class LiveService:
    def __init__(self):
        self.pipeline = ProductionPipeline()
        self.data = LiveMarketData()
        self.interval = int(os.getenv("SIGNAL_INTERVAL_SECONDS", "60"))
        self.status_interval_seconds = int(os.getenv("STATUS_INTERVAL_SECONDS", "900"))
        self.max_candle_age_seconds = int(os.getenv("MAX_CANDLE_AGE_SECONDS", "600"))
        self._started = False
        self._last_candle: dict[str, str] = {}
        self._last_status_slot: str | None = None
        self._runtime_errors: dict[str, str] = {}
        self._last_prices: dict[str, float] = {}
        self._latest_results: dict[str, object] = {}
        self._last_no_trade_slot: str | None = None

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        send(format_startup(list(self.data.symbols().keys())))
        threading.Thread(target=self._loop, name="production-v2-scheduler", daemon=True).start()

    def _send_status(self, now: datetime) -> None:
        market_states = {}
        for alias in self.data.symbols():
            try:
                market_states[alias] = "MARKET_OPEN" if self.data.market_is_open(alias, now) else "MARKET_CLOSED"
            except Exception as exc:
                market_states[alias] = "MARKET_STATUS_UNKNOWN"
                self._runtime_errors[alias] = f"market status: {exc}"
        send(format_status({"prices": dict(self._last_prices), "market_states": market_states, "timeframe": "M5", "timestamp": now, "architecture": "E1 -> E2 -> E3 -> E4 -> E5 -> E6 -> E7 -> E8 -> E9"}))
        self._last_status_slot = now.strftime("%Y%m%d%H%M")

    def _send_aligned_status(self) -> None:
        now = datetime.now(BANGKOK_TZ)
        if now.minute % 15 != 0:
            return
        slot = now.strftime("%Y%m%d%H%M")
        if slot == self._last_status_slot:
            return
        try:
            self._send_status(now)
        except Exception as exc:
            print(f"[PRODUCTION V2] Telegram status error: {exc}", flush=True)

    def _send_aligned_no_trade(self) -> None:
        now = datetime.now(BANGKOK_TZ)
        if now.minute % 10 != 0:
            return
        slot = now.strftime("%Y%m%d%H%M")
        if slot == self._last_no_trade_slot:
            return
        symbols = self.data.symbols()
        market_open = {}
        for alias in symbols:
            try:
                market_open[alias] = self.data.market_is_open(alias, now)
            except Exception as exc:
                market_open[alias] = False
                self._runtime_errors[alias] = f"market status: {exc}"
        active_results = {alias: result for alias, result in self._latest_results.items() if alias in symbols and market_open.get(alias, False)}
        if not active_results:
            self._last_no_trade_slot = slot
            return
        if any(getattr(result, "decision", None) in {"BUY", "SELL"} and bool(getattr(result, "gate_passed", False)) for result in active_results.values()):
            self._last_no_trade_slot = slot
            return
        try:
            send_no_trade(dict(active_results), now)
            self._last_no_trade_slot = slot
        except Exception as exc:
            print(f"[PRODUCTION V2] Telegram no-trade error: {exc}", flush=True)

    @staticmethod
    def _candle_age_seconds(candle: str) -> float | None:
        try:
            timestamp = datetime.fromisoformat(candle.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - timestamp).total_seconds())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _reasoning(engine) -> dict:
        output = engine.output or {}
        reasoning = output.get("professional_reasoning") or {}
        specialists = output.get("specialists") or {}
        if engine.engine_id == "E1":
            market_state = reasoning.get("market_state") or output.get("market_state") or "UNCLEAR"
            volatility = reasoning.get("volatility_state") or output.get("volatility_state") or "UNKNOWN"
            structure = reasoning.get("structure_state") or output.get("structure_state") or "UNCLEAR"
            transition = reasoning.get("transition") or output.get("transition") or "UNKNOWN"
            pressure = reasoning.get("directional_pressure") or output.get("directional_pressure") or "BALANCED"
            trend_state = reasoning.get("trend_state") or output.get("trend_state") or "NONE"
            conclusion = f"MARKET_STATE={market_state}; VOLATILITY={volatility}; STRUCTURE={structure}; PRESSURE={pressure}; TREND_STATE={trend_state}; TRANSITION={transition}"
            observations = []
            brain_evidence = output.get("evidence") or reasoning.get("evidence") or []
            if isinstance(brain_evidence, (list, tuple)):
                observations.extend(str(x) for x in brain_evidence if x)
            trace = output.get("reasoning_trace") or []
            if isinstance(trace, (list, tuple)):
                observations.extend(str(x) for x in trace if x)
            for key in ("directional_pressure", "trend_state", "volatility_state", "structure_state", "compression", "expansion", "transition"):
                value = reasoning.get(key) or output.get(key)
                if value is not None:
                    observations.append(f"{key}={value}")
            if isinstance(specialists, dict):
                for item in specialists.values():
                    if not isinstance(item, dict):
                        continue
                    observations.extend(str(x) for x in (item.get("observations") or []) if x)
            return {"question": reasoning.get("question") or output.get("question") or output.get("specialist_question"), "conclusion": str(conclusion), "observations": list(dict.fromkeys(observations))[:12], "reasons": sorted(set(str(x) for x in (engine.reason_codes or [])))[:16], "role": "MARKET_STATE_ANALYST"}
        if engine.engine_id == "E2":
            observations = []
            for source in (output.get("observations") or [], output.get("evidence") or [], output.get("decision_factors") or []):
                observations.extend(str(x) for x in source if x)
            observations.extend(f"counter_evidence={x}" for x in (output.get("counter_evidence") or []) if x)
            observations.extend(f"missing_evidence={x}" for x in (output.get("missing_evidence") or []) if x)
            reasons = list(engine.reason_codes or [])
            if not reasons and output.get("opportunity_decision"):
                reasons.append(str(output["opportunity_decision"]))
            return {"question": reasoning.get("question") or output.get("question") or "What opportunity is the market offering right now?", "conclusion": str(reasoning.get("conclusion") or output.get("thesis") or "UNRESOLVED"), "observations": list(dict.fromkeys(observations))[:12], "reasons": sorted(set(str(x) for x in reasons if str(x).strip()))[:16], "role": output.get("reasoning_role", "OPPORTUNITY_REGIME_ANALYST")}
        if engine.engine_id == "E3":
            observations = []
            for source in (output.get("observations"), output.get("evidence"), reasoning.get("evidence")):
                if isinstance(source, (list, tuple)):
                    observations.extend(str(x) for x in source if x)
            reasons = list(engine.reason_codes or []) + list(reasoning.get("reason_codes") or []) + list(output.get("reasons") or [])
            return {"question": reasoning.get("question") or output.get("question") or "What is price structure communicating?", "conclusion": str(reasoning.get("finding") or reasoning.get("conclusion") or output.get("finding") or "STRUCTURE_UNRESOLVED"), "observations": list(dict.fromkeys(observations))[:12], "reasons": sorted(set(str(x) for x in reasons if str(x).strip()))[:16], "role": "MARKET_STRUCTURE_ANALYST"}
        if engine.engine_id == "E4":
            observations = []
            for source in (output.get("observations"), reasoning.get("evidence")):
                if isinstance(source, (list, tuple)):
                    observations.extend(str(x) for x in source if x)
            audit = output.get("audit") or {}
            for key in ("closed_candle_only", "no_lookahead", "liquidity_side", "liquidity_kind", "touches", "freshness", "event", "event_age_bars", "actor_identification", "auction_state", "lifecycle", "follow_through_bars", "consecutive_confirmation_bars", "true_acceptance_gate", "contextual_hint_not_authority"):
                if key in audit:
                    observations.append(f"{key}={audit[key]}")
            reasons = list(engine.reason_codes or []) + list(output.get("reasons") or [])
            return {"question": reasoning.get("question") or output.get("question") or "Where is liquidity, who took it, and did price accept or reject the auction?", "conclusion": str(reasoning.get("conclusion") or output.get("analyst_conclusion") or output.get("finding") or "UNRESOLVED"), "observations": list(dict.fromkeys(observations))[:20], "reasons": sorted(set(str(x) for x in reasons if str(x).strip()))[:20], "role": "LIQUIDITY_AUCTION_ANALYST"}
        if engine.engine_id == "E5":
            observations = list(output.get("observations") or [])
            observations.extend(str(x) for x in (output.get("reasoning_trace") or []) if x)
            observations.append(f"direction={output.get('direction', 'NEUTRAL')}")
            observations.append(f"location_quality={output.get('location_quality', 'UNKNOWN')}")
            observations.append(f"preferred_location={output.get('preferred_location', 'NONE')}")
            reasons = list(engine.reason_codes or []) + list(output.get("counter_evidence") or [])
            return {"question": reasoning.get("question") or output.get("question") or "Is current location advantageous?", "conclusion": str(output.get("location_state") or reasoning.get("thesis") or "E5_DATA_UNRESOLVED"), "observations": list(dict.fromkeys(str(x) for x in observations if str(x)))[:16], "reasons": sorted(set(str(x) for x in reasons if str(x).strip()))[:20], "role": "LOCATION_VALUE_ANALYST"}
        if engine.engine_id == "E6":
            observations = []
            observations.extend(str(x) for x in (output.get("supporting_evidence") or []) if x)
            observations.extend(f"counter_evidence={x}" for x in (output.get("counter_evidence") or []) if x)
            observations.extend(f"missing_proof={x}" for x in (output.get("missing_proof") or []) if x)
            observations.extend(str(x) for x in (output.get("reason_codes") or []) if x)
            return {"question": reasoning.get("question") or output.get("question") or "Is there a causal setup thesis from E1-E5?", "conclusion": str(reasoning.get("conclusion") or output.get("finding") or "E6_DATA_UNRESOLVED"), "observations": list(dict.fromkeys(observations))[:20], "reasons": sorted(set(str(x) for x in (engine.reason_codes or []) if str(x).strip()))[:20], "role": "OPPORTUNITY_THESIS_ANALYST"}
        conclusion = reasoning.get("conclusion") or output.get("analyst_conclusion") or output.get("finding") or "UNRESOLVED"
        question = reasoning.get("question") or output.get("question") or output.get("specialist_question")
        observations = []
        reasons = list(engine.reason_codes or [])
        if isinstance(specialists, dict):
            for item in specialists.values():
                if not isinstance(item, dict):
                    continue
                observations.extend(item.get("observations") or [])
                reasons.extend(item.get("reason_codes") or [])
        return {"question": question, "conclusion": str(conclusion), "observations": [str(x) for x in observations[:12]], "reasons": sorted(set(str(x) for x in reasons))[:16], "role": output.get("reasoning_role", "TRADE_ECONOMICS_RISK")}

    def _trace_result(self, alias: str, result) -> None:
        trace = _pipeline_trace_fields(result)
        print(f"[PRODUCTION V2] {alias} PIPELINE decision={result.decision} state={trace['state']} blocked_by={trace['blocked_by']} wait_bars={trace['wait_bars']} gate={result.gate_passed} engines={len(result.engines)}", flush=True)
        for engine in result.engines:
            if engine.engine_id == "E9":
                reasoning = engine.output.get("professional_reasoning") or {}
                print(f"[PRODUCTION V2] {alias} E9 MASTER decision={engine.output.get('decision', result.decision)} reason={engine.output.get('decision_reasons', list(engine.reason_codes))} thesis={reasoning.get('primary_thesis', 'UNRESOLVED')} setup={((reasoning.get('independent_setup') or reasoning.get('setup') or {}).get('state', reasoning.get('setup_state', 'UNKNOWN')))} execution={((reasoning.get('execution') or {}).get('state', reasoning.get('execution_state', 'UNKNOWN')))} conflicts={reasoning.get('conflicts', [])} invalidations={reasoning.get('hard_invalidations', [])}", flush=True)
                continue
            why = self._reasoning(engine)
            print(f"[PRODUCTION V2] {alias} {engine.engine_id} ROLE={why['role']} question={why['question']} finding={why['conclusion']} observations={why['observations']} reasons={why['reasons']}", flush=True)

    def _loop(self) -> None:
        while True:
            for alias in self.data.symbols():
                try:
                    raw = self.data.candles(alias)
                    if raw.get("market_state") == "MARKET_CLOSED" and not raw.get("bars"):
                        self._runtime_errors.pop(alias, None)
                        print(f"[PRODUCTION V2] {alias} MARKET_CLOSED action=SKIP_EVALUATION", flush=True)
                        continue
                    payload = normalize_market_data(raw)
                    if payload["bars"]:
                        self._last_prices[alias] = payload["bars"][-1]["close"]
                        store.update_price(alias, self._last_prices[alias])
                    candle = payload.get("candle_close_timestamp") or ""
                    if not candle:
                        self._runtime_errors[alias] = "missing candle timestamp"
                        continue
                    age = self._candle_age_seconds(candle)
                    if age is not None and age > self.max_candle_age_seconds:
                        print(f"[PRODUCTION V2] {alias} STALE_CANDLE candle={candle} age_seconds={int(age)} action=SKIP_EVALUATION", flush=True)
                        self._runtime_errors[alias] = f"stale candle: {candle}"
                        continue
                    if self._last_candle.get(alias) == candle:
                        print(f"[PRODUCTION V2] {alias} DUPLICATE_CANDLE candle={candle} action=SKIP_EVALUATION", flush=True)
                        continue
                    self._last_candle[alias] = candle
                    print(f"[PRODUCTION V2] {alias} LSE M5 new closed candle bars={len(raw.get('bars') or [])} candle={candle}", flush=True)
                    print(f"[PRODUCTION V2] {alias} PIPELINE_STAGE ENTER E6_E7_E8_E9 candle={candle}", flush=True)
                    result = self.pipeline.run(payload)
                    print(f"[PRODUCTION V2] {alias} PIPELINE_STAGE EXIT E6_E7_E8_E9 candle={candle}", flush=True)
                    self._runtime_errors.pop(alias, None)
                    self._latest_results[alias] = result
                    store.record(result, self._last_prices.get(alias))
                    self._trace_result(alias, result)
                    if result.decision in {"BUY", "SELL"} and result.gate_passed:
                        send_decision(result)
                except Exception as exc:
                    self._runtime_errors[alias] = f"{type(exc).__name__}: {exc}"
                    print(f"[PRODUCTION V2] {alias} PIPELINE_EXCEPTION type={type(exc).__name__} message={exc}", flush=True)
                    traceback.print_exc()
            self._send_aligned_no_trade()
            self._send_aligned_status()
            time.sleep(self.interval)


_service = None


def start_live_service() -> None:
    global _service
    if _service is None:
        _service = LiveService()
    _service.start()
