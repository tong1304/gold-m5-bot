from __future__ import annotations
import logging
import os
from flask import Flask, jsonify, request
from .market_data import normalize_market_data
from . import pipeline as pipeline_module
from .pipeline import ProductionPipeline
from .bootstrap_surgery import install as install_bootstrap_surgery
from .professional_opportunity_surgery import enrich_decision
from .statistics import build_statistics, store

logger = logging.getLogger(__name__)
app = Flask(__name__)
install_bootstrap_surgery(pipeline_module)
pipeline = ProductionPipeline()
app.config["PRODUCTION_V2_LIVE_REQUIRED"] = True
_runtime_started = False
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
