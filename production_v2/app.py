from __future__ import annotations

import logging
import os

from flask import Flask, jsonify, request

from .market_data import normalize_market_data
from .pipeline import ProductionPipeline
from .statistics import build_statistics, store

logger = logging.getLogger(__name__)
app = Flask(__name__)
pipeline = ProductionPipeline()
app.config["PRODUCTION_V2_LIVE_REQUIRED"] = True
_runtime_started = False


def start_production_runtime() -> None:
    """Start the production-v2 live M5 runtime exactly once at import time."""
    global _runtime_started
    if _runtime_started:
        return

    key = os.getenv("LSE_API_KEY", "").strip()
    if not key:
        logger.error("[PRODUCTION V2] LSE_API_KEY is missing; live M5 runtime cannot start")
        print("[PRODUCTION V2] FATAL: LSE_API_KEY is missing; live M5 runtime cannot start", flush=True)
        raise RuntimeError("LSE_API_KEY is required for production-v2 live runtime")

    logger.info("[PRODUCTION V2] Initializing live M5 runtime")
    print("[PRODUCTION V2] Initializing live M5 runtime", flush=True)

    from .service import start_live_service
    start_live_service()
    _runtime_started = True

    logger.info("[PRODUCTION V2] Live M5 runtime started; architecture=E1->E2->E3->E4->E5->E6->E7->E8->E9")
    print("[PRODUCTION V2] Live M5 runtime started; architecture=E1->E2->E3->E4->E5->E6->E7->E8->E9", flush=True)


start_production_runtime()


@app.get("/")
def index():
    return jsonify({
        "system": "9-ENGINE",
        "version": "production-v2",
        "architecture": "E1 -> E2 -> E3 -> E4 -> E5 -> E6 -> E7 -> E8 -> E9",
        "decision_authority": "E9",
        "legacy_runtime": False,
        "live_runtime": "RUNNING" if _runtime_started else "NOT_RUNNING",
        "environment": os.getenv("RENDER_ENV", "production"),
    })


@app.get("/health")
def health():
    return jsonify({
        "status": "ok" if _runtime_started else "degraded",
        "system": "9-ENGINE",
        "version": "production-v2",
        "legacy_runtime": False,
        "decision_authority": "E9",
        "live_runtime": "RUNNING" if _runtime_started else "NOT_RUNNING",
        "timeframe": "M5",
    }), (200 if _runtime_started else 503)


@app.get("/api/statistics")
@app.get("/statistics")
def statistics():
    return jsonify(build_statistics())


@app.post("/signal")
def signal():
    try:
        market_data = normalize_market_data(request.get_json(silent=True) or {})
        result = pipeline.run(market_data)
        price = market_data["bars"][-1]["close"] if market_data["bars"] else None
        store.record(result, price)
        return jsonify(result.as_dict())
    except ValueError as exc:
        return jsonify({"error": str(exc), "system": "9-ENGINE", "legacy_runtime": False}), 400
    except Exception as exc:
        app.logger.exception("production-v2 pipeline failure")
        return jsonify({"error": "PIPELINE_ERROR", "detail": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
