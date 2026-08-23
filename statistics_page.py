"""V9.1 statistics/replay route registration.

Register the historical pages independently so a replay import problem cannot
remove the statistics page, and make registration idempotent for Gunicorn.
"""
import json
import logging

import statistics_page_v9 as _statistics

logger = logging.getLogger(__name__)


def _has_route(app, path):
    return any(rule.rule == path for rule in app.url_map.iter_rules())


def register(app):
    # Statistics is the primary legacy UI and must survive replay failures.
    if not _has_route(app, "/statistics"):
        _statistics.register(app)
        logger.info("V9.1 statistics route registered: /statistics")

    # Recover replay independently if nested registration was skipped.
    if not _has_route(app, "/replay"):
        try:
            import replay_web
            replay_web.register(app)
            logger.info("Historical replay route registered: /replay")
        except Exception:
            logger.exception("Failed to register Historical Replay route")

    # Diagnostic route for Render deployments; exposes only route names.
    if not _has_route(app, "/routes"):
        from flask import Response

        @app.route("/routes", strict_slashes=False)
        def route_status():
            routes = sorted({rule.rule for rule in app.url_map.iter_rules()})
            return Response(
                json.dumps({
                    "status": "ok",
                    "engine_version": "V9.1",
                    "statistics": "/statistics" in routes,
                    "replay": "/replay" in routes,
                    "routes": routes,
                }, ensure_ascii=False),
                mimetype="application/json",
            )


__all__ = ["register"]
