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
ARCHITECTURE = "PARALLEL_BASELINE:E1-E8 -> PARALLEL_PEER_REANALYSIS:E1-E8 -> E9"


def start_production_runtime() -> None:
    global _runtime_started
    if _runtime_started:
        return
    if os.getenv("PRODUCTION_V2_DISABLE_LIVE", "").strip() == "1":
        logger.info("[PRODUCTION V2] Live runtime disabled by PRODUCTION_V2_DISABLE_LIVE")
        print("[PRODUCTION V2] Live runtime disabled by test environment", flush=True)
        _runtime_started = True
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
    logger.info("[PRODUCTION V2] Live M5 runtime started; architecture=%s", ARCHITECTURE)
    print(f"[PRODUCTION V2] Live M5 runtime started; architecture={ARCHITECTURE}", flush=True)


start_production_runtime()


@app.get("/")
def index():
    return jsonify({
        "system": "9-ENGINE",
        "version": "production-v2",
        "architecture": ARCHITECTURE,
        "specialist_mode": "PARALLEL_SHARED_MARKET_AND_PEER_EVIDENCE",
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
        "architecture": ARCHITECTURE,
        "specialist_mode": "PARALLEL_SHARED_MARKET_AND_PEER_EVIDENCE",
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
