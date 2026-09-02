from __future__ import annotations
import logging
import os
from flask import Flask, jsonify, request
from .market_data import normalize_market_data
from . import pipeline as pipeline_module
from .pipeline import ProductionPipeline
from .bootstrap_surgery import install as install_bootstrap_surgery
from .brain_handoff import attach_result_chain
from .professional_opportunity_surgery import enrich_decision
from .opportunity_lifecycle import advance_opportunity
from .statistics import build_statistics, store

logger = logging.getLogger(__name__)
app = Flask(__name__)
install_bootstrap_surgery(pipeline_module)
pipeline = ProductionPipeline()
app.config["PRODUCTION_V2_LIVE_REQUIRED"] = True
_runtime_started = False
_last_opportunity_lifecycle: dict[str, dict] = {}
ARCHITECTURE = "SINGLE_AXIS:E1 -> E2 -> E3 -> E4 -> E5 -> E6 -> E7 -> E8 -> E9 -> OPPORTUNITY_SYNTHESIS"


def _load_historical_calibration():
    """Load only completed E9 outcomes when an external journal is configured."""
    path = os.getenv("E9_LEARNING_PATH", "").strip()
    if not path:
        return None
    try:
        from .e9_learning import load_records
        records = load_records(path)
        completed = [
            record.__dict__
            for record in records
            if str(record.outcome or "").upper() in {"WIN", "LOSS", "TIMEOUT"}
            and record.realized_r is not None
        ]
        logger.info("[PRODUCTION V2] E9 calibration loaded path=%s completed=%d", path, len(completed))
        return completed
    except Exception:
        logger.exception("[PRODUCTION V2] E9 calibration load failed path=%s", path)
        return None


def _text(value) -> str:
    return str(value or "").upper().strip()


def _current_opportunity_input(result, candle: str) -> dict:
    engines = {engine.engine_id: engine.output or {} for engine in result.engines}
    e6 = engines.get("E6", {})
    e7 = engines.get("E7", {})
    e8 = engines.get("E8", {})
    e9 = engines.get("E9", {})

    direction = _text(e6.get("direction") or e6.get("direction_thesis") or e6.get("thesis_direction"))
    setup = _text(e6.get("setup") or e6.get("setup_family") or e6.get("setup_type"))
    e6_state = _text(e6.get("setup_state") or e6.get("opportunity_stage") or e6.get("state") or e6.get("finding"))
    e6_reasons = [_text(x) for x in (e6.get("reason_codes") or e6.get("reasons") or [])]
    confirmation = _text(e7.get("confirmation_state") or e7.get("confirmation") or "")
    profit_edge = e8.get("profit_edge") if isinstance(e8.get("profit_edge"), dict) else {}
    e9_decision = _text(e9.get("decision") or result.decision)

    thesis_status = e6_state if e6_state in {"FORMING", "VALIDATING", "MATURE", "CONFIRMED", "TRADE_READY"} else "NONE"
    candidate = bool(
        direction in {"BUY", "SELL"}
        and setup not in {"", "UNKNOWN", "NONE", "NO_SETUP"}
        and not any(token in e6_state for token in ("INVALIDATED", "NO_SETUP"))
        and "CAUSAL_SETUP_PROOF_INCOMPLETE" not in e6_reasons
    )
    ready = bool(
        candidate
        and e6_state in {"MATURE", "TRADE_READY", "CONFIRMED"}
        and confirmation in {"PROVEN", "CONFIRMED"}
        and bool(profit_edge.get("trusted"))
        and not profit_edge.get("blockers")
    )
    executed = bool(e9_decision in {"BUY", "SELL"} and result.gate_passed)
    invalidated = bool(
        any(token in e6_state for token in ("INVALIDATED",))
        or any("INVALIDATED" in code or "HARD_VETO" in code for code in e6_reasons)
    )
    return {
        "candidate": candidate,
        "direction": direction,
        "setup": setup,
        "ready": ready,
        "invalidated": invalidated,
        "executed": executed,
        "thesis_status": thesis_status,
        "candle": candle,
    }


def _run_with_lifecycle(self, market_data, *, wait_bars=0, resume_state=None, historical_calibration=None):
    """Run the full E1-E9 analysis while preserving a still-valid opportunity.

    Re-analysis on every new closed candle is intentional: the market must be
    re-validated. Lifecycle state prevents a valid opportunity from being
    forgotten between candles; it never bypasses E1-E9 or E9 authority.
    """
    symbol = str(market_data.get("symbol") or "UNKNOWN").upper()
    previous = dict(_last_opportunity_lifecycle.get(symbol) or {})
    if previous.get("state") in {"WAITING", "READY"}:
        market_data = dict(market_data)
        market_data["opportunity_resume_state"] = dict(previous)
        resume_state = dict(previous)
    result = _ORIGINAL_PIPELINE_RUN(
        self,
        market_data,
        wait_bars=wait_bars,
        resume_state=resume_state,
        historical_calibration=historical_calibration,
    )
    candle = str(market_data.get("candle_close_timestamp") or "")
    current = _current_opportunity_input(result, candle)
    lifecycle = advance_opportunity(previous, current)
    _last_opportunity_lifecycle[symbol] = lifecycle
    risk = dict(result.risk)
    risk["opportunity_lifecycle"] = lifecycle
    risk["next_required_event"] = "NEXT_CLOSED_M5_CANDLE" if lifecycle.get("state") in {"WAITING", "READY"} else None
    risk["wait_bars"] = int(lifecycle.get("bars_waited", 0) or 0)
    print(
        f"[PRODUCTION V2] {symbol} OPPORTUNITY_LIFECYCLE "
        f"state={lifecycle.get('state')} continuity={lifecycle.get('continuity')} "
        f"bars_waited={lifecycle.get('bars_waited', 0)} "
        f"opportunity_id={lifecycle.get('opportunity_id')} "
        f"candle={candle} next={risk['next_required_event']}",
        flush=True,
    )
    return result.__class__(result.symbol, result.timeframe, result.decision, result.gate_passed, result.score, result.engines, risk, result.reason_codes)


_ORIGINAL_PIPELINE_RUN = ProductionPipeline.run
ProductionPipeline.run = _run_with_lifecycle


def _connect_brains(result):
    """Attach evidence handoff without resetting the lifecycle owned by runtime."""
    result = attach_result_chain(result)
    symbol = str(result.symbol or "UNKNOWN").upper()
    lifecycle = dict(result.risk.get("opportunity_lifecycle") or _last_opportunity_lifecycle.get(symbol) or {})
    _last_opportunity_lifecycle[symbol] = lifecycle
    risk = dict(result.risk)
    risk["opportunity_lifecycle"] = lifecycle
    risk["next_required_event"] = "NEXT_CLOSED_M5_CANDLE" if lifecycle.get("state") in {"WAITING", "READY"} else None
    risk["wait_bars"] = int(lifecycle.get("bars_waited", 0) or 0)
    return result.__class__(result.symbol, result.timeframe, result.decision, result.gate_passed, result.score, result.engines, risk, result.reason_codes)


def start_production_runtime():
    global _runtime_started
    if _runtime_started:
        return
    if os.getenv("PRODUCTION_V2_DISABLE_LIVE", "").strip() == "1":
        print("[PRODUCTION V2] Live runtime disabled by test environment", flush=True)
        _runtime_started = True
        return
    key = os.getenv("LSE_API_KEY", "").strip()
    if not key:
        raise RuntimeError("LSE_API_KEY is required for production-v2 live runtime")
    from .service import start_live_service
    start_live_service()
    _runtime_started = True
    print(f"[PRODUCTION V2] Live M5 runtime started; architecture={ARCHITECTURE}", flush=True)


start_production_runtime()


@app.get("/")
def index():
    return jsonify({"system": "9-ENGINE", "version": "production-v2", "architecture": ARCHITECTURE, "sub_engines": False, "parallel_peer_analysis": False, "decision_authority": "E9", "legacy_runtime": False, "live_runtime": "RUNNING" if _runtime_started else "NOT_RUNNING", "environment": os.getenv("RENDER_ENV", "production")})


@app.get("/health")
def health():
    return jsonify({"status": "ok" if _runtime_started else "degraded", "system": "9-ENGINE", "version": "production-v2", "architecture": ARCHITECTURE, "sub_engines": False, "parallel_peer_analysis": False, "decision_authority": "E9", "legacy_runtime": False, "live_runtime": "RUNNING" if _runtime_started else "NOT_RUNNING", "timeframe": "M5"}), (200 if _runtime_started else 503)


@app.get("/api/statistics")
@app.get("/statistics")
def statistics():
    return jsonify(build_statistics())


@app.post("/signal")
def signal():
    try:
        market_data = normalize_market_data(request.get_json(silent=True) or {})
        result = pipeline.run(market_data, historical_calibration=_load_historical_calibration())
        result = _connect_brains(result)
        result = enrich_decision(result)
        price = market_data["bars"][-1]["close"] if market_data["bars"] else None
        store.record(result, price)
        return jsonify(result.as_dict())
    except ValueError as exc:
        return jsonify({"error": str(exc), "system": "9-ENGINE", "legacy_runtime": False}), 400
    except Exception as exc:
        logger.exception("production-v2 pipeline failure")
        return jsonify({"error": "PIPELINE_ERROR", "detail": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
