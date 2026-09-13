from __future__ import annotations

import logging
from typing import Any

from .contracts import DecisionResult, EngineResult
from . import opportunity_memory

logger = logging.getLogger(__name__)

_STAGE_RANK = {"WATCH": 0, "CONFIRMED": 1, "E6_THESIS": 2, "E7_CONFIRMED": 3, "E8_READY": 4, "TRADE": 5}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _engine(result: DecisionResult, engine_id: str) -> EngineResult | None:
    return next((e for e in result.engines if e.engine_id == engine_id), None)


def _out(result: DecisionResult, engine_id: str) -> dict[str, Any]:
    engine = _engine(result, engine_id)
    return dict(engine.output or {}) if engine else {}


def _repair_item(item: dict[str, Any], *, candle: Any) -> dict[str, Any]:
    repaired = dict(item)
    old_stage = _text(repaired.get("lifecycle_stage")) or "UNKNOWN"
    history = list(repaired.get("stage_history") or [])
    history.append({"stage": "WATCH", "candle": str(candle or ""), "reason": "STATE_RECONCILIATION_CONFIRMED_WITHOUT_CURRENT_PROOF"})
    repaired.update({
        "lifecycle_stage": "WATCH",
        "lifecycle_state": "WATCH",
        "opportunity_phase": "OPPORTUNITY_WATCH",
        "state": "WATCHING",
        "wait_for_stage": "CONFIRMED",
        "trade_authorized": False,
        "terminal_stage": None,
        "terminal_reason": None,
        "execution_state": "NONE",
        "stage_history": history,
        "state_reconciliation": {
            "applied": True,
            "from_stage": old_stage,
            "to_stage": "WATCH",
            "reason": "CURRENT_E4_PENDING_E7_UNCONFIRMED_E6_NOT_PROVEN",
        },
    })
    return repaired


def _needs_repair(lifecycle: dict[str, Any], result: DecisionResult) -> bool:
    stage = _text(lifecycle.get("lifecycle_stage"))
    if _STAGE_RANK.get(stage, -1) < _STAGE_RANK["CONFIRMED"]:
        return False
    if _bool_trade(lifecycle) or _text(lifecycle.get("terminal_stage")) in {"INVALIDATED", "EXPIRED", "REPLACED", "TOO_LATE"}:
        return False
    e4 = _out(result, "E4")
    e6 = _out(result, "E6")
    e7 = _out(result, "E7")
    e8 = _out(result, "E8")
    e4_state = _text(e4.get("auction_state") or e4.get("auction_phase") or e4.get("state"))
    e7_state = _text(e7.get("confirmation_state") or e7.get("confirmation") or e7.get("proof_state") or e7.get("trigger_state"))
    e6_proven = bool(e6.get("e6_thesis_proven") or e6.get("setup_exists") or e6.get("trade_ready"))
    e8_ready = bool(e8.get("risk_ready") or e8.get("gate_passed"))
    e9_decision = _text(_out(result, "E9").get("decision") or result.decision)
    return e4_state not in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "RECLAIMED"} and e7_state not in {"PASS", "PASSED", "CONFIRMED", "TRIGGER_CONFIRMED", "PROVEN", "VALIDATED", "TRADE_READY"} and not e6_proven and not e8_ready and e9_decision not in {"BUY", "SELL", "TRADE"}


def _bool_trade(lifecycle: dict[str, Any]) -> bool:
    return bool(lifecycle.get("trade_authorized")) or _text(lifecycle.get("lifecycle_stage")) == "TRADE"


def install(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_OPPORTUNITY_STATE_RECONCILIATION_INSTALLED", False):
        return
    original = pipeline_module.ProductionPipeline.run

    def wrapped(self, market_data, *, wait_bars=0, resume_state=None, historical_calibration=None):
        result = original(self, market_data, wait_bars=wait_bars, resume_state=resume_state, historical_calibration=historical_calibration)
        lifecycle = result.risk.get("opportunity_lifecycle") if isinstance(result.risk, dict) else None
        if not isinstance(lifecycle, dict) or not _needs_repair(lifecycle, result):
            return result

        direction = _text(lifecycle.get("direction"))
        opportunities = dict(lifecycle.get("opportunities") or {}) if isinstance(lifecycle.get("opportunities"), dict) else {}
        item = dict(opportunities.get(direction) or {}) if direction in {"BUY", "SELL"} else {}
        if not item:
            item = dict(lifecycle)
        candle = market_data.get("candle_close_timestamp") or market_data.get("candle")
        repaired = _repair_item(item, candle=candle)
        if direction in {"BUY", "SELL"}:
            opportunities[direction] = repaired
            lifecycle["opportunities"] = opportunities
        for key in ("lifecycle_stage", "lifecycle_wait_for_stage", "lifecycle_terminal_state", "lifecycle_terminal_reason"):
            lifecycle[key] = {"lifecycle_stage": "WATCH", "lifecycle_wait_for_stage": "CONFIRMED", "lifecycle_terminal_state": None, "lifecycle_terminal_reason": None}[key]
        lifecycle.update({
            "state": "WATCHING",
            "lifecycle_state": "WATCH",
            "opportunity_phase": "OPPORTUNITY_WATCH",
            "wait_for_stage": "CONFIRMED",
            "trade_authorized": False,
            "state_reconciliation": repaired.get("state_reconciliation"),
        })

        engines = []
        for engine in result.engines:
            if engine.engine_id != "E9":
                engines.append(engine)
                continue
            out = dict(engine.output or {})
            out["opportunity_lifecycle"] = lifecycle
            out["lifecycle_stage"] = "WATCH"
            out["lifecycle_wait_for_stage"] = "CONFIRMED"
            out["lifecycle_terminal_state"] = None
            out["lifecycle_terminal_reason"] = None
            out["state_reconciliation"] = repaired.get("state_reconciliation")
            reasons = list(engine.reason_codes or ())
            if "LIFECYCLE_STATE_RECONCILED" not in reasons:
                reasons.append("LIFECYCLE_STATE_RECONCILED")
            engines.append(EngineResult(engine.engine_id, engine.name, False, engine.score, out, tuple(reasons)))

        risk = dict(result.risk or {})
        risk["opportunity_lifecycle"] = lifecycle
        risk["lifecycle_stage"] = "WATCH"
        risk["lifecycle_wait_for_stage"] = "CONFIRMED"
        risk["trade_authorized"] = False
        risk["state_reconciliation"] = repaired.get("state_reconciliation")
        updated = DecisionResult(
            result.symbol, result.timeframe, "NO_TRADE", False, result.score,
            tuple(engines), risk,
            tuple(dict.fromkeys(list(result.reason_codes) + ["LIFECYCLE_STATE_RECONCILED"])),
            "ANALYSIS_COMPLETE_NO_TRADE", result.blocked_by,
            result.wait_bars, result.execution_state,
        )
        symbol = str(market_data.get("symbol") or market_data.get("asset") or result.symbol or "UNKNOWN").upper()
        self._opportunity_lifecycle[symbol] = lifecycle
        opportunity_memory.save(symbol, lifecycle)
        logger.info("[PRODUCTION V2] OPPORTUNITY_LIFECYCLE_REPAIR symbol=%s from=%s to=WATCH reason=CURRENT_E4_PENDING_E7_UNCONFIRMED_E6_NOT_PROVEN", symbol, repaired["state_reconciliation"]["from_stage"])
        return updated

    pipeline_module.ProductionPipeline.run = wrapped
    pipeline_module._OPPORTUNITY_STATE_RECONCILIATION_INSTALLED = True
    print("[PRODUCTION V2] OPPORTUNITY_STATE_RECONCILIATION binding=STALE_STAGE_REPAIR", flush=True)
