"""V11 statistics/replay route registration with robust JSON fallback."""
from __future__ import annotations
import json
import logging
from flask import Response
logger=logging.getLogger(__name__)

def _has_route(app,path):
    return any(rule.rule==path for rule in app.url_map.iter_rules())

def _json(payload,status=200):
    return Response(json.dumps(payload,ensure_ascii=False,allow_nan=False,default=str),status=status,mimetype="application/json",headers={"Cache-Control":"no-store"})

def _actual_replay_trades(result):
    trades=[]
    for report in (result.get("reports") or []):
        symbol=report.get("symbol")
        for trade in (report.get("trade_history") or []):
            item=dict(trade)
            item["symbol"]=symbol
            trades.append(item)
    trades.sort(key=lambda x:str(x.get("candle_time") or ""),reverse=True)
    return trades

def _rebuild_performance(result):
    trades=_actual_replay_trades(result)
    outcomes=[str(t.get("result") or "OPEN").upper() for t in trades]
    wins=sum(x=="WIN" for x in outcomes);losses=sum(x=="LOSS" for x in outcomes);opens=sum(x=="OPEN" for x in outcomes);ambiguous=sum(x=="AMBIGUOUS" for x in outcomes)
    decided=wins+losses
    r=[float(t.get("r_multiple") or 0.0) for t in trades if str(t.get("result") or "").upper() in ("WIN","LOSS")]
    net=round(sum(r),4);gross_profit=round(sum(x for x in r if x>0),4);gross_loss=round(abs(sum(x for x in r if x<0)),4)
    return {"trades":len(trades),"decided":decided,"wins":wins,"losses":losses,"open":opens,"ambiguous":ambiguous,"no_trade":0,"net_r":net,"gross_profit_r":gross_profit,"gross_loss_r":gross_loss,"win_rate":round(100*wins/decided,2) if decided else 0.0,"loss_rate":round(100*losses/decided,2) if decided else 0.0,"expectancy_r":round(net/decided,4) if decided else 0.0,"profit_factor":round(gross_profit/gross_loss,4) if gross_loss else None}

def _install_statistics_api_override(app):
    """Use one replay-state contract and calculate statistics from actual replay trades."""
    endpoint="statistics_api"
    if endpoint not in app.view_functions:return False
    try:
        import statistics_page_v11 as mod
        def statistics_api_fixed():
            state=mod._replay_state()
            result=state.get("result")
            live=mod._live_signals()
            if not result:
                if state.get("running"):
                    payload=mod._running_payload(state);payload["live_signal_count"]=len(live);payload["live_signals"]=live;return mod._json(payload)
                return mod._json({"status":"no_replay","engine_version":mod.ENGINE_VERSION,"source":"LSE_HISTORICAL_OHLCV","message":"ยังไม่มีผล V11 Replay","live_signal_count":len(live),"live_signals":live,"live_orders_allowed":False})
            payload=mod._replay_payload(result,state)
            actual=_actual_replay_trades(result)
            perf=_rebuild_performance(result)
            old=payload.get("performance") or {}
            perf["rows"]=old.get("rows",0)
            perf["evaluated_rows"]=old.get("evaluated_rows",old.get("rows",0))
            perf["locked_rows"]=old.get("locked_rows",0)
            payload["performance"]={**old,**perf}
            payload["trade_history"]=actual
            payload["live_signal_count"]=len(live);payload["live_signals"]=live;payload["progress"]=mod._progress(state) if state.get("running") else None
            return mod._json(payload)
        app.view_functions[endpoint]=statistics_api_fixed
        logger.warning("[V11 STARTUP] Statistics API override installed: actual replay trades")
        return True
    except Exception:
        logger.exception("[V11 STARTUP] Failed to install Statistics API override")
        return False

def register(app):
    try:
        import statistics_page_v11 as _statistics
        _statistics.register(app)
        _install_statistics_api_override(app)
        logger.warning("[V11 STARTUP] Statistics V11.2 routes registered")
    except Exception as exc:
        logger.exception("[V11 STARTUP] Statistics V11.2 import/register failed: %s",exc)
        if not _has_route(app,"/statistics"):
            @app.route("/statistics",strict_slashes=False)
            def statistics_fallback_page():
                return Response("""<!doctype html><html lang='th'><meta charset='utf-8'><title>V11.2 Statistics</title><body style='font-family:system-ui;background:#0b1220;color:#eee;padding:30px'><h1>📊 V11.2 Statistics</h1><p>Statistics module โหลดไม่สำเร็จ</p><pre id='e'></pre><p><a href='/replay' style='color:#70a7ff'>⏪ Replay</a></p><script>fetch('/api/statistics').then(async r=>document.getElementById('e').textContent=await r.text()).catch(e=>document.getElementById('e').textContent=String(e))</script></body></html>""",mimetype="text/html")
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
            return _json({"status":"ok","engine_version":"11.2-DYNAMIC-STRATEGIES","statistics":"/statistics" in routes,"statistics_api":"/api/statistics" in routes,"replay":"/replay" in routes})

__all__=["register"]
