"""V11 statistics/replay route registration with a JSON-safe fallback."""
from __future__ import annotations
import json
import logging
from flask import Response, request
logger=logging.getLogger(__name__)

def _has_route(app,path):
    return any(rule.rule==path for rule in app.url_map.iter_rules())

def _json(payload,status=200):
    return Response(json.dumps(payload,ensure_ascii=False,allow_nan=False,default=str),status=status,mimetype="application/json",headers={"Cache-Control":"no-store"})

def register(app):
    try:
        import statistics_page_v11 as _statistics
        _statistics.register(app)
        logger.warning("[V11 STARTUP] Statistics V11.2 routes registered")
    except Exception as exc:
        logger.exception("[V11 STARTUP] Statistics V11.2 import/register failed: %s",exc)
        if not _has_route(app,"/statistics"):
            @app.route("/statistics",strict_slashes=False)
            def statistics_fallback_page():
                return Response("""<!doctype html><html lang='th'><meta charset='utf-8'><title>V11.2 Statistics</title><body style='font-family:system-ui;background:#0b1220;color:#eee;padding:30px'><h1>📊 V11.2 Statistics</h1><p>Statistics module กำลังโหลดไม่สำเร็จ</p><pre id='e'></pre><p><a href='/replay' style='color:#70a7ff'>⏪ Replay</a></p><script>fetch('/api/statistics').then(r=>r.json()).then(x=>document.getElementById('e').textContent=JSON.stringify(x,null,2)).catch(e=>document.getElementById('e').textContent=String(e))</script></body></html>""",mimetype="text/html")
        if not _has_route(app,"/api/statistics"):
            @app.route("/api/statistics",strict_slashes=False)
            def statistics_api_fallback():
                return _json({"status":"statistics_route_error","engine_version":"11.2-DYNAMIC-STRATEGIES","message":"Statistics module failed to load","error_type":type(exc).__name__,"error":str(exc),"live_orders_allowed":False},500)
    if not _has_route(app,"/replay"):
        try:
            import replay_web
            replay_web.register(app)
            logger.warning("[V11 STARTUP] Replay route registered: /replay")
        except Exception as exc:
            logger.exception("[V11 STARTUP] Replay route registration failed: %s",exc)
    if not _has_route(app,"/routes"):
        @app.route("/routes",strict_slashes=False)
        def route_status():
            routes=sorted({rule.rule for rule in app.url_map.iter_rules()})
            return _json({"status":"ok","engine_version":"11.2-DYNAMIC-STRATEGIES","statistics":"/statistics" in routes,"statistics_api":"/api/statistics" in routes,"replay":"/replay" in routes,"routes":routes})

__all__=["register"]
