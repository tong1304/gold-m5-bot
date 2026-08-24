from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from .backtest.repository import BacktestRepository
from .config import database_path, max_backtest_days
from .state_store import StateStore
from .telegram_control import TelegramControl

UTC = timezone.utc


def _parse_dt(value: str) -> datetime:
    if not value:
        raise ValueError("date is required")
    text = value.strip()
    if len(text) == 10:
        dt = datetime.fromisoformat(text).replace(tzinfo=UTC)
    else:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    cfg = {"DB_PATH": str(database_path())}
    if test_config:
        cfg.update(test_config)
    app.config.update(cfg)

    store = StateStore(Path(app.config["DB_PATH"]))
    telegram = TelegramControl(store)
    repository = BacktestRepository(store)
    app.extensions["state_store"] = store
    app.extensions["telegram_control"] = telegram
    app.extensions["backtest_repository"] = repository

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        return jsonify(
            status="ok",
            service="v12.9-control-backtest",
            engine_version="12.9-MTF-H1-M15-TREND-M5-BTC-GOLD-MULTI-TP",
            telegram_enabled=telegram.get_telegram_enabled(),
            live_services_started=False,
        )

    @app.get("/api/telegram")
    def telegram_status():
        return jsonify(enabled=telegram.get_telegram_enabled())

    @app.post("/api/telegram/toggle")
    def telegram_toggle():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("enabled"), bool):
            return jsonify(status="error", message="enabled must be boolean"), 400
        enabled = telegram.set_telegram_enabled(payload["enabled"])
        return jsonify(status="ok", enabled=enabled)

    def _worker(run_id: str, symbol: str, start: datetime, end: datetime) -> None:
        try:
            from .backtest.engine import run_backtest
            result = run_backtest(
                symbol,
                start,
                end,
                run_id=run_id,
                api_key=os.getenv("LSE_API_KEY"),
            )
            repository.save_backtest(result, datetime.now(UTC).isoformat())
        except Exception as exc:
            store.fail_run(run_id, f"{type(exc).__name__}: {exc}", datetime.now(UTC).isoformat())

    @app.post("/api/backtest")
    def start_backtest():
        payload = request.get_json(silent=True) or {}
        symbol = str(payload.get("symbol", "BTC")).upper().strip()
        if symbol not in {"BTC", "GOLD"}:
            return jsonify(status="error", message="symbol must be BTC or GOLD"), 400
        try:
            start = _parse_dt(str(payload.get("start", "")))
            end = _parse_dt(str(payload.get("end", "")))
        except ValueError as exc:
            return jsonify(status="error", message=str(exc)), 400
        if end <= start:
            return jsonify(status="error", message="end must be after start"), 400
        if end - start > timedelta(days=max_backtest_days()):
            return jsonify(status="error", message=f"date range cannot exceed {max_backtest_days()} days"), 400
        run_id = f"BT-{symbol}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        store.create_run(run_id, symbol, start.isoformat(), end.isoformat(), datetime.now(UTC).isoformat())
        thread = threading.Thread(target=_worker, args=(run_id, symbol, start, end), name=f"backtest-{run_id}", daemon=True)
        thread.start()
        return jsonify(status="started", run_id=run_id), 202

    @app.get("/api/backtest/<run_id>")
    def get_backtest(run_id: str):
        result = repository.get_backtest(run_id)
        if result is None:
            return jsonify(status="not_found", run_id=run_id), 404
        return jsonify(result)

    @app.get("/api/backtests")
    def list_backtests():
        try:
            limit = int(request.args.get("limit", "20"))
        except ValueError:
            limit = 20
        return jsonify(runs=repository.list_backtests(limit))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
