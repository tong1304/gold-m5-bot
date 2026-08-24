"""V11 statistics and historical replay route registration."""
import json
import logging
from flask import Response, request
import statistics_page_v11 as _statistics
logger=logging.getLogger(__name__)


def _has_route(app,path): return any(rule.rule==path for rule in app.url_map.iter_rules())


def register(app):
    if not _has_route(app,"/statistics"):
        _statistics.register(app); logger.info("V11 backtest statistics route registered: /statistics")
    if not _has_route(app,"/replay"):
        try:
            import replay_web; replay_web.register(app); logger.info("V11 historical replay route registered: /replay")
        except Exception: logger.exception("Failed to register V11 historical replay route")

    # During a replay the API used to return status=running, while the
    # statistics page intentionally hid the normal cards in that state.
    # Convert the live progress snapshot into the same statistics payload
    # shape so the existing page can render useful data immediately.
    @app.after_request
    def _statistics_live_progress(response):
        if request.path != "/api/statistics" or response.mimetype != "application/json":
            return response
        try:
            payload=json.loads(response.get_data(as_text=True))
            if payload.get("status") != "running":
                return response
            p=payload.get("progress") or {}
            wins=int(p.get("wins") or 0); losses=int(p.get("losses") or 0); decided=wins+losses
            trades=int(p.get("trades") or 0); open_count=int(p.get("open") or 0); ambiguous=int(p.get("ambiguous") or 0)
            payload["status"]="ok"
            payload["phase"]="running"
            payload["performance"]={
                "rows":int(p.get("completed") or 0),
                "trades":trades,
                "decided":decided,
                "wins":wins,
                "losses":losses,
                "open":open_count,
                "ambiguous":ambiguous,
                "no_trade":max(0,int(p.get("completed") or 0)-trades),
                "win_rate":round(100*wins/decided,2) if decided else 0.0,
                "loss_rate":round(100*losses/decided,2) if decided else 0.0,
                "net_r":float(p.get("net_r") or 0.0),
                "gross_profit_r":0.0,
                "gross_loss_r":0.0,
                "profit_factor":None,
                "expectancy_r":round(float(p.get("net_r") or 0.0)/decided,4) if decided else 0.0,
            }
            payload["trade_history"]=[]
            payload["strategies"]={}
            payload["reports"]=[]
            response.set_data(json.dumps(payload,ensure_ascii=False,allow_nan=False))
            response.headers["Cache-Control"]="no-store"
        except Exception:
            logger.exception("Failed to transform live statistics progress")
        return response

    if not _has_route(app,"/routes"):
        @app.route("/routes",strict_slashes=False)
        def route_status():
            routes=sorted({rule.rule for rule in app.url_map.iter_rules()})
            return Response(json.dumps({"status":"ok","engine_version":"11.1-HARDENED","statistics":"/statistics" in routes,"replay":"/replay" in routes,"routes":routes},ensure_ascii=False),mimetype="application/json")

__all__=["register"]
