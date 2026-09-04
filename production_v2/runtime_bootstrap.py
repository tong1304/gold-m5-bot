from __future__ import annotations

import logging
import os
from threading import Lock

from flask import jsonify, request

logger = logging.getLogger(__name__)
_runtime_started = False
_runtime_lock = Lock()

ARCHITECTURE = "SINGLE_AXIS:E1 -> E2 -> E3 -> E4 -> E5 -> E6 -> E7 -> E8 -> E9 -> OPPORTUNITY_SYNTHESIS"


def start_production_runtime() -> bool:
    """Start the live scanner exactly once and fail loudly when production is misconfigured."""
    global _runtime_started
    if _runtime_started:
        return True
    with _runtime_lock:
        if _runtime_started:
            return True
        if os.getenv("PRODUCTION_V2_DISABLE_LIVE", "").strip() == "1":
            logger.info("[PRODUCTION V2] Live runtime disabled by test environment")
            _runtime_started = True
            return True
        key = os.getenv("LSE_API_KEY", "").strip()
        if not key:
            raise RuntimeError("LSE_API_KEY is required for production-v2 live runtime")
        from .service import start_live_service
        start_live_service()
        _runtime_started = True
        print(
            f"[PRODUCTION V2] Live M5 runtime started; architecture={ARCHITECTURE}",
            flush=True,
        )
        return True


def install_routes(app, *, pipeline, load_historical_calibration, connect_brains, enrich_decision, normalize_market_data, build_statistics, store):
    """Restore the application boundary that must exist around the nine-brain runtime."""
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
            }
        )

    @app.get("/health")
    def health():
        healthy = _runtime_started
        return jsonify(
            {
                "status": "ok" if healthy else "degraded",
                "system": "9-ENGINE",
                "version": "production-v2",
                "architecture": ARCHITECTURE,
                "decision_authority": "E9",
                "legacy_runtime": False,
                "timeframe": "M5",
                "live_runtime": healthy,
            }
        ), (200 if healthy else 503)

    @app.get("/ready")
    def ready():
        ready_state = _runtime_started
        return jsonify(
            {
                "ready": ready_state,
                "live_runtime": ready_state,
                "scanner_contract": "STARTED",
                "architecture": ARCHITECTURE,
            }
        ), (200 if ready_state else 503)

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
                historical_calibration=load_historical_calibration(),
            )
            result = connect_brains(result)
            result = enrich_decision(result)
            price = market_data["bars"][-1]["close"] if market_data["bars"] else None
            store.record(result, price)
            return jsonify(result.as_dict())
        except ValueError as exc:
            return jsonify(
                {"error": str(exc), "system": "9-ENGINE", "legacy_runtime": False}
            ), 400
        except Exception as exc:
            logger.exception("[PRODUCTION V2] pipeline failure")
            return jsonify({"error": "PIPELINE_ERROR", "detail": str(exc)}), 500

    logger.info(
        "[PRODUCTION V2] HTTP boundary installed routes=/,/health,/ready,/signal,/statistics"
    )
