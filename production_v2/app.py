from __future__ import annotations
import logging
import os
from flask import Flask, jsonify, request
from .market_data import normalize_market_data
from . import pipeline as pipeline_module
from .pipeline import ProductionPipeline
from .bootstrap_surgery import install as install_bootstrap_surgery
from .brain_handoff import attach_result_chain
from .professional_opportunity_surgery import enrich_decision
from .opportunity_lifecycle import advance_opportunity
from .statistics import build_statistics, store

logger = logging.getLogger(__name__)
app = Flask(__name__)
install_bootstrap_surgery(pipeline_module)
pipeline = ProductionPipeline()
app.config["PRODUCTION_V2_LIVE_REQUIRED"] = True
_runtime_started = False
_last_opportunity_lifecycle: dict[str, dict] = {}
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


def _text(value) -> str:
    return str(value or "").upper().strip()


def _direction_from_output(output: dict) -> str:
    """Extract directional intent without inventing a trade thesis."""
    for value in (
        output.get("direction"),
        output.get("opportunity_direction"),
        output.get("market_direction"),
        output.get("structure_direction"),
        output.get("pressure"),
        output.get("finding"),
        output.get("market_state"),
    ):
        text = _text(value)
        if text in {"BUY", "UP", "BULLISH", "TREND_UP"} or text.startswith(("BUY ", "BUY_", "BUY:")):
            return "BUY"
        if text in {"SELL", "DOWN", "BEARISH", "TREND_DOWN"} or text.startswith(("SELL ", "SELL_", "SELL:")):
            return "SELL"
    return "NEUTRAL"


def _pending_upstream_thesis(engines: dict[str, dict]) -> tuple[str, str, list[str]]:
    """Build a watch-only thesis from explicit E2/E4 pending evidence.

    This is deliberately NOT an executable setup. It gives lifecycle state an
    identity only when the upstream brains explicitly say an opportunity is
    developing or an auction/confirmation is pending.
    """
    e2 = engines.get("E2", {})
    e4 = engines.get("E4", {})
    e5 = engines.get("E5", {})
    direction = _direction_from_output(e2)
    if direction not in {"BUY", "SELL"}:
        direction = _direction_from_output(e4)
    if direction not in {"BUY", "SELL"}:
        return "NEUTRAL", "", []

    e2_finding = _text(e2.get("finding"))
    e2_maturity = _text(e2.get("opportunity_maturity"))
    e2_state = _text(e2.get("state"))
    e2_reasons = _text(e2.get("reasons"))
    e4_finding = _text(e4.get("finding"))
    e4_auction_state = _text(e4.get("auction_state") or e4.get("auction_phase"))
    e4_event = _text(e4.get("event") or e4.get("auction_event") or e4.get("liquidity_event"))
    e4_reasons = _text(e4.get("reasons"))
    e5_text = " ".join(_text(e5.get(key)) for key in ("finding", "value_response", "repricing_state", "reasons"))

    e2_developing = any(token in " ".join((e2_finding, e2_maturity, e2_state)) for token in ("DEVELOPING", "PENDING"))
    e4_pending = e4_auction_state in {"PENDING", "AWAITING_CONFIRMATION", "CONFIRMATION_PENDING"}
    e4_pending_finding = any(token in e4_finding for token in ("SWEEP", "FAILED_BREAK", "RECLAIM")) and any(token in e4_reasons for token in ("PENDING", "NOT_TERMINALLY_CONFIRMED", "CONFIRMATION_NOT_PROVEN"))
    has_pending = e2_developing or e4_pending or e4_pending_finding
    if not has_pending:
        return direction, "", []

    evidence: list[str] = []
    if e2_developing:
        evidence.append("E2_OPPORTUNITY_DEVELOPING")
    if e4_pending or e4_pending_finding:
        evidence.append("E4_AUCTION_PENDING")
    if e4_event:
        evidence.append("E4_EVENT_PRESENT")
    if "SPACE_CONSTRAINED" in e5_text:
        evidence.append("TARGET_SPACE_CURRENTLY_CONSTRAINED")
    return direction, "OPPORTUNITY_WATCH", evidence


def _current_opportunity_input(result, candle: str) -> dict:
    engines = {engine.engine_id: engine.output or {} for engine in result.engines}
    e2 = engines.get("E2", {})
    e4 = engines.get("E4", {})
    e6 = engines.get("E6", {})
    e7 = engines.get("E7", {})
    e8 = engines.get("E8", {})
    e9 = engines.get("E9", {})

    e6_direction = _direction_from_output(e6)
    e6_setup = _text(e6.get("setup") or e6.get("setup_family") or e6.get("setup_type"))
    e6_state = _text(e6.get("setup_state") or e6.get("opportunity_stage") or e6.get("state") or e6.get("finding"))
    e6_reasons = [_text(x) for x in (e6.get("reason_codes") or e6.get("reasons") or [])]

    real_setup = e6_direction in {"BUY", "SELL"} and e6_setup not in {"", "UNKNOWN", "NONE", "NO_SETUP"}
    pending_direction, pending_setup, pending_evidence = _pending_upstream_thesis(engines)
    if real_setup and not any(token in e6_state for token in ("INVALIDATED", "NO_SETUP")) and "CAUSAL_SETUP_PROOF_INCOMPLETE" not in e6_reasons:
        direction = e6_direction
        setup = e6_setup
        thesis_status = e6_state if e6_state in {"FORMING", "VALIDATING", "MATURE", "CONFIRMED", "TRADE_READY"} else "FORMING"
        candidate = True
        lifecycle_source = "E6_SETUP"
    elif pending_setup:
        direction = pending_direction
        setup = pending_setup
        thesis_status = "FORMING"
        candidate = True
        lifecycle_source = "E2_E4_UPSTREAM_WATCH"
    else:
        direction = e6_direction
        setup = e6_setup
        thesis_status = "NONE"
        candidate = False
        lifecycle_source = "NONE"

    confirmation = _text(e7.get("confirmation_state") or e7.get("confirmation") or "")
    profit_edge = e8.get("profit_edge") if isinstance(e8.get("profit_edge"), dict) else {}
    e9_decision = _text(e9.get("decision") or result.decision)
    ready = bool(
        real_setup
        and candidate
        and e6_state in {"MATURE", "TRADE_READY", "CONFIRMED"}
        and confirmation in {"PROVEN", "CONFIRMED"}
        and bool(profit_edge.get("trusted"))
        and not profit_edge.get("blockers")
    )
    executed = bool(e9_decision in {"BUY", "SELL"} and result.gate_passed)
    invalidated = bool(
        any(token in e6_state for token in ("INVALIDATED",))
        or any("INVALIDATED" in code or "HARD_VETO" in code for code in e6_reasons)
    )
    return {
        "candidate": candidate,
        "direction": direction,
        "setup": setup,
        "ready": ready,
        "invalidated": invalidated,
        "executed": executed,
        "thesis_status": thesis_status,
        "candle": candle,
        "lifecycle_source": lifecycle_source,
        "upstream_evidence": pending_evidence,
    }


def _run_with_lifecycle(self, market_data, *, wait_bars=0, resume_state=None, historical_calibration=None):
    """Run full E1-E9 analysis while preserving a still-valid opportunity.

    Re-analysis on every new closed candle is intentional. Lifecycle state only
    remembers a developing opportunity; it never bypasses E1-E9 or E9 authority.
    """
    symbol = str(market_data.get("symbol") or "UNKNOWN").upper()
    previous = dict(_last_opportunity_lifecycle.get(symbol) or {})
    if previous.get("state") in {"WAITING", "READY"}:
        market_data = dict(market_data)
        market_data["opportunity_resume_state"] = dict(previous)
        resume_state = dict(previous)
    result = _ORIGINAL_PIPELINE_RUN(
        self,
        market_data,
        wait_bars=wait_bars,
        resume_state=resume_state,
        historical_calibration=historical_calibration,
    )
    candle = str(market_data.get("candle_close_timestamp") or "")
    current = _current_opportunity_input(result, candle)
    lifecycle = advance_opportunity(previous, current)
    _last_opportunity_lifecycle[symbol] = lifecycle
    risk = dict(result.risk)
    risk["opportunity_lifecycle"] = lifecycle
    risk["next_required_event"] = "NEXT_CLOSED_M5_CANDLE" if lifecycle.get("state") in {"WAITING", "READY"} else None
    risk["wait_bars"] = int(lifecycle.get("bars_waited", 0) or 0)
    risk["lifecycle_source"] = current.get("lifecycle_source")
    risk["upstream_evidence"] = current.get("upstream_evidence", [])
    print(
        f"[PRODUCTION V2] {symbol} OPPORTUNITY_LIFECYCLE "
        f"state={lifecycle.get('state')} continuity={lifecycle.get('continuity')} "
        f"bars_waited={lifecycle.get('bars_waited', 0)} "
        f"opportunity_id={lifecycle.get('opportunity_id')} "
        f"source={current.get('lifecycle_source')} candle={candle} "
        f"next={risk['next_required_event']}",
        flush=True,
    )
    return result.__class__(result.symbol, result.timeframe, result.decision, result.gate_passed, result.score, result.engines, risk, result.reason_codes)


_ORIGINAL_PIPELINE_RUN = ProductionPipeline.run
ProductionPipeline.run = _run_with_lifecycle


def _connect_brains(result):
    """Attach evidence handoff without resetting lifecycle owned by runtime."""
    result = attach_result_chain(result)
    symbol = str(result.symbol or "UNKNOWN").upper()
    lifecycle = dict(result.risk.get("opportunity_lifecycle") or _last_opportunity_lifecycle.get(symbol) or {})
    _last_opportunity_lifecycle[symbol] = lifecycle
    risk = dict(result.risk)
    risk["opportunity_lifecycle"] = lifecycle
    risk["next_required_event"] = "NEXT_CLOSED_M5_CANDLE" if lifecycle.get("state") in {"WAITING", "READY"} else None
    risk["wait_bars"] = int(lifecycle.get("bars_waited", 0) or 0)
    return result.__class__(result.symbol, result.timeframe, result.decision, result.gate_passed, result.score, result.engines, risk, result.reason_codes)


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
        result = _connect_brains(result)
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
