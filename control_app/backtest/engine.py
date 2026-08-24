from __future__ import annotations

import math
import os
from datetime import datetime
from typing import Any, Callable

from .data import load_historical_frames
from .models import BacktestResult


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    try:
        return _json_safe(value.item())
    except Exception:
        return str(value)


def _trade_view(row: dict[str, Any]) -> dict[str, Any]:
    levels = row.get("trade_levels") or {}
    return _json_safe(
        {
            "signal_id": row.get("signal_id"),
            "candle_time": row.get("candle_time"),
            "closed_candle": row.get("closed_candle"),
            "resolved_at": row.get("resolved_at"),
            "symbol": row.get("symbol"),
            "side": row.get("signal"),
            "strategy": row.get("strategy"),
            "engine": row.get("engine"),
            "entry_type": row.get("entry_type"),
            "setup_id": row.get("setup_id"),
            "trigger_id": row.get("trigger_id"),
            "h1_bias": row.get("h1_bias"),
            "m15_regime": row.get("m15_regime"),
            "entry": levels.get("entry"),
            "sl": levels.get("sl"),
            "tp": levels.get("tp"),
            "risk_reward": levels.get("risk_reward"),
            "result": row.get("result"),
            "r_multiple": row.get("r_multiple", 0.0),
        }
    )


def _breakdown(trades: list[dict[str, Any]], key: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for trade in trades:
        name = str(trade.get(key) or "NONE")
        item = out.setdefault(name, {"trades": 0, "wins": 0, "losses": 0, "open": 0, "ambiguous": 0, "net_r": 0.0})
        result = trade.get("result")
        if result != "NO_TRADE":
            item["trades"] += 1
        if result == "WIN":
            item["wins"] += 1
        elif result == "LOSS":
            item["losses"] += 1
        elif result == "OPEN":
            item["open"] += 1
        elif result == "AMBIGUOUS":
            item["ambiguous"] += 1
        if result in ("WIN", "LOSS"):
            item["net_r"] += float(trade.get("r_multiple") or 0)
    for item in out.values():
        item["net_r"] = round(item["net_r"], 4)
        decided = item["wins"] + item["losses"]
        item["win_rate"] = round(100 * item["wins"] / decided, 2) if decided else 0.0
    return out


def run_backtest(
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    run_id: str = "",
    api_key: str | None = None,
    data_loader: Callable[..., dict[str, Any]] = load_historical_frames,
) -> BacktestResult:
    symbol = symbol.upper().strip()
    if symbol not in {"BTC", "GOLD"}:
        raise ValueError("symbol must be BTC or GOLD")
    frames = data_loader(symbol, start, end, api_key=api_key)
    from v11.replay_m5 import replay_frames

    replay = replay_frames(
        frames["5m"],
        frames["15m"],
        frames["1h"],
        symbol=symbol,
        start_time=start,
        end_time=end,
    )
    trades = [_trade_view(row) for row in replay.get("trade_history", [])]
    performance = replay.get("performance", {})
    decided = [t for t in trades if t.get("result") in ("WIN", "LOSS")]
    wins = sum(t.get("result") == "WIN" for t in trades)
    losses = sum(t.get("result") == "LOSS" for t in trades)
    net_r = round(sum(float(t.get("r_multiple") or 0) for t in decided), 4)
    gross_profit = round(sum(max(float(t.get("r_multiple") or 0), 0) for t in decided), 4)
    gross_loss = round(abs(sum(min(float(t.get("r_multiple") or 0), 0) for t in decided)), 4)
    statistics = {
        "total_trades": len(trades),
        "wins": wins,
        "losses": losses,
        "be": 0,
        "open": sum(t.get("result") == "OPEN" for t in trades),
        "ambiguous": sum(t.get("result") == "AMBIGUOUS" for t in trades),
        "win_rate": round(100 * wins / len(decided), 2) if decided else 0.0,
        "net_r": net_r,
        "average_r": round(net_r / len(decided), 4) if decided else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
        "max_drawdown_r": performance.get("max_drawdown_r", 0.0),
        "gross_profit_r": gross_profit,
        "gross_loss_r": gross_loss,
        "candles_evaluated": replay.get("candles_evaluated", 0),
        "strategy_breakdown": _breakdown(trades, "strategy"),
        "side_breakdown": _breakdown(trades, "side"),
    }
    return BacktestResult(
        run_id=run_id,
        symbol=symbol,
        start_time=start.isoformat(),
        end_time=end.isoformat(),
        engine_version=replay.get("engine_version", "12.9-MTF-H1-M15-TREND-M5-BTC-GOLD-MULTI-TP"),
        statistics=statistics,
        trades=trades,
        metadata={
            "timeframe_mode": "MTF:H1→M15→M5",
            "lookahead_safe": True,
            "live_orders_allowed": False,
            "telegram_alert_sent": False,
            "gold_session_filter": "New York DST session gate",
        },
    )
