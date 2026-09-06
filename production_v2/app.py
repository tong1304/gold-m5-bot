from __future__ import annotations

import logging
import os

from flask import Flask, jsonify, request

from .market_data import normalize_market_data
from . import pipeline as pipeline_module
from .pipeline import ProductionPipeline
from .bootstrap_surgery import install as install_bootstrap_surgery
from .e4_event_lifecycle_surgery import install as install_e4_event_lifecycle_surgery
from .e6_pending_event_surgery import install as install_e6_pending_event_surgery
from .runtime_compatibility import install as install_runtime_compatibility, fingerprint as runtime_fingerprint
from .execution_geometry_surgery import install as install_execution_geometry
from .brain_handoff import attach_result_chain
from .professional_opportunity_surgery import enrich_decision
from .opportunity_memory import (
    load_all as load_opportunity_memory,
    backend as opportunity_memory_backend,
    last_error as opportunity_memory_last_error,
    require_persistent_backend,
)
from .statistics import build_statistics, store

logger = logging.getLogger(__name__)
app = Flask(__name__)
# Install compatibility before any live worker is constructed. This makes a
# stale 4-argument lifecycle helper harmless while retaining causal_anchor on
# current builds, and prevents a healthy HTTP process from hiding a broken
# opportunity pipeline.
install_runtime_compatibility(pipeline_module)
install_bootstrap_surgery(pipeline_module)
install_e4_event_lifecycle_surgery(pipeline_module)
install_e6_pending_event_surgery(pipeline_module)
install_execution_geometry(pipeline_module)
pipeline = ProductionPipeline()
app.config["PRODUCTION_V2_LIVE_REQUIRED"] = True
_runtime_started = False
_last_opportunity_lifecycle: dict[str, dict] = load_opportunity_memory()
ARCHITECTURE = "SINGLE_AXIS:E1 -> E2 -> E3 -> E4 -> E5 -> E6 -> E7 -> E8 -> E9 -> OPPORTUNITY_SYNTHESIS"


def _load_historical_calibration():
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


def _connect_brains(result):
    """Attach the result chain without replacing pipeline-owned lifecycle state."""
    result = attach_result_chain(result)
    risk = dict(result.risk or {})
    lifecycle = risk.get("opportunity_lifecycle")
    if not isinstance(lifecycle, dict):
        symbol = str(result.symbol or "UNKNOWN").upper()
        lifecycle = _last_opportunity_lifecycle.get(symbol, {})
    if isinstance(lifecycle, dict):
        _last_opportunity_lifecycle[str(result.symbol or "UNKNOWN").upper()] = lifecycle
        risk["opportunity_lifecycle"] = lifecycle
        risk["next_required_event"] = (
            "NEXT_CLOSED_M5_CANDLE"
            if lifecycle.get("state") in {"WATCHING", "WAITING", "READY"}
            else None
        )
        risk["wait_bars"] = int(lifecycle.get("bars_waited", 0) or 0)
    return result.__class__(
        result.symbol,
        result.timeframe,
        result.decision,
        result.gate_passed,
        result.score,
        result.engines,
        risk,
        result.reason_codes,
    )


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
    require_persistent_backend()
    from .service import start_live_service
    start_live_service()
    _runtime_started = True
    print(
        f"[PRODUCTION V2] Live M5 runtime started; architecture={ARCHITECTURE}; "
        f"opportunity_memory_backend={opportunity_memory_backend()}; "
        f"records={len(_last_opportunity_lifecycle)}; "
        f"runtime={runtime_fingerprint(pipeline_module)}",
        flush=True,
    )


start_production_runtime()


@app.get("/")
def index():
    return jsonify(
        {
            "system": "9-ENGINE",
            "version": "production-v2",
            "architecture": ARCHITECTURE,
            "sub_engines": False,
            "parallel_peer_analysis": False,
            "decision_authority": "E9",
            "legacy_runtime": False,
            "live_runtime": "RUNNING" if _runtime_started else "NOT_RUNNING",
            "environment": os.getenv("RENDER_ENV", "production"),
            "opportunity_memory_backend": opportunity_memory_backend(),
            "opportunity_memory_records": len(_last_opportunity_lifecycle),
            "opportunity_memory_error": opportunity_memory_last_error(),
            "runtime_fingerprint": runtime_fingerprint(pipeline_module),
        }
    )


@app.get("/health")
def health():
    return jsonify(
        {
            "status": "ok" if _runtime_started else "degraded",
            "system": "9-ENGINE",
            "version": "production-v2",
            "architecture": ARCHITECTURE,
            "sub_engines": False,
            "parallel_peer_analysis": False,
            "decision_authority": "E9",
            "legacy_runtime": False,
            "timeframe": "M5",
            "opportunity_memory_backend": opportunity_memory_backend(),
            "opportunity_memory_records": len(_last_opportunity_lifecycle),
            "opportunity_memory_error": opportunity_memory_last_error(),
            "runtime_fingerprint": runtime_fingerprint(pipeline_module),
        }
    ), (200 if _runtime_started else 503)


@app.get("/api/statistics")
@app.get("/statistics")
def statistics():
    return jsonify(build_statistics())


@app.post("/signal")
def signal():
    try:
        market_data = normalize_market_data(request.get_json(silent=True) or {})
        result = pipeline.run(
            market_data,
            historical_calibration=_load_historical_calibration(),
        )
        result = _connect_brains(result)
        result = enrich_decision(result)
        price = market_data["bars"][-1]["close"] if market_data["bars"] else None
        store.record(result, price)
        return jsonify(result.as_dict())
    except ValueError as exc:
        return jsonify({"error": str(exc), "system": "9-engine", "legacy_runtime": False}), 400
    except Exception as exc:
        logger.exception("production-v2 pipeline failure")
        return jsonify({"error": "PIPELINE_ERROR", "detail": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
