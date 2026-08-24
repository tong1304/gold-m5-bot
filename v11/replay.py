from __future__ import annotations

from datetime import timedelta

import pandas as pd

from . import engine


def resolve_outcome(signal: dict, future: pd.DataFrame):
    if signal.get("signal") not in ("BUY", "SELL"):
        return {"result": "NO_TRADE", "r_multiple": 0.0}
    levels = signal.get("trade_levels") or {}
    entry = float(levels["entry"])
    sl = float(levels["sl"])
    tp = float(levels["tp"])
    direction = signal["signal"]
    for _, row in future.iterrows():
        high = float(row.high)
        low = float(row.low)
        ts = str(row.datetime)
        hit_sl = low <= sl if direction == "BUY" else high >= sl
        hit_tp = high >= tp if direction == "BUY" else low <= tp
        if hit_sl and hit_tp:
            return {"result": "AMBIGUOUS", "r_multiple": 0.0, "resolved_at": ts}
        if hit_tp:
            return {"result": "WIN", "r_multiple": round(abs(tp - entry) / abs(entry - sl), 4), "resolved_at": ts}
        if hit_sl:
            return {"result": "LOSS", "r_multiple": -1.0, "resolved_at": ts}
    return {"result": "OPEN", "r_multiple": 0.0}


def _pct(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 2) if denominator else 0.0


def _max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += float(value)
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return round(max_dd, 4)


def summarize_rows(rows: list[dict]) -> dict:
    """Summarize replay outcomes; NO_TRADE is not a trade."""
    counts = {key: 0 for key in ("WIN", "LOSS", "OPEN", "AMBIGUOUS", "NO_TRADE")}
    decided_r: list[float] = []
    strategies: dict[str, dict] = {}
    for row in rows:
        result = str(row.get("result") or "NO_TRADE").upper()
        if result not in counts:
            result = "NO_TRADE"
        counts[result] += 1
        strategy = str(row.get("strategy") or "NONE")
        s = strategies.setdefault(strategy, {"evaluated": 0, "trades": 0, "wins": 0, "losses": 0, "open": 0, "ambiguous": 0, "no_trade": 0, "net_r": 0.0})
        s["evaluated"] += 1
        if result == "NO_TRADE": s["no_trade"] += 1
        else: s["trades"] += 1
        if result == "WIN": s["wins"] += 1
        elif result == "LOSS": s["losses"] += 1
        elif result == "OPEN": s["open"] += 1
        elif result == "AMBIGUOUS": s["ambiguous"] += 1
        r = float(row.get("r_multiple") or 0.0)
        if result in ("WIN", "LOSS"):
            decided_r.append(r)
            s["net_r"] += r

    wins, losses = counts["WIN"], counts["LOSS"]
    decided = wins + losses
    trades = decided + counts["OPEN"] + counts["AMBIGUOUS"]
    gross_profit = round(sum(r for r in decided_r if r > 0), 4)
    gross_loss = round(abs(sum(r for r in decided_r if r < 0)), 4)
    net_r = round(sum(decided_r), 4)
    for s in strategies.values():
        s["net_r"] = round(s["net_r"], 4)
        s["win_rate"] = _pct(s["wins"], s["wins"] + s["losses"])
        s["expectancy_r"] = round(s["net_r"] / (s["wins"] + s["losses"]), 4) if (s["wins"] + s["losses"]) else 0.0
    return {
        "rows": len(rows), "trades": trades, "decided": decided,
        "wins": wins, "losses": losses, "open": counts["OPEN"], "ambiguous": counts["AMBIGUOUS"], "no_trade": counts["NO_TRADE"],
        "win_rate": _pct(wins, decided), "loss_rate": _pct(losses, decided), "net_r": net_r,
        "gross_profit_r": gross_profit, "gross_loss_r": gross_loss,
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else (None if gross_profit == 0 else float("inf")),
        "expectancy_r": round(net_r / decided, 4) if decided else 0.0,
        "max_drawdown_r": _max_drawdown(decided_r), "strategies": strategies,
    }


def _timestamp(value):
    if value is None or value == "": return None
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def replay_frames(m5: pd.DataFrame, m15: pd.DataFrame, symbol: str, *, limit: int | None = None, start_time=None, end_time=None):
    """Replay the exact V11 decision path with historical warm-up and no lookahead."""
    m5 = m5.sort_values("datetime").reset_index(drop=True)
    m15 = m15.sort_values("datetime").reset_index(drop=True)
    start_ts, end_ts = _timestamp(start_time), _timestamp(end_time)
    indices = list(range(60, len(m5)))
    if start_ts is not None: indices = [i for i in indices if pd.Timestamp(m5.iloc[i].datetime) >= start_ts]
    if end_ts is not None: indices = [i for i in indices if pd.Timestamp(m5.iloc[i].datetime) < end_ts]
    if limit: indices = indices[-limit:]
    rows = []
    for i in indices:
        ts = m5.iloc[i].datetime
        context = m15[m15.datetime <= ts - timedelta(minutes=15)].reset_index(drop=True)
        setup = engine.analyze(m5.iloc[:i + 1].reset_index(drop=True), context, symbol, i)
        outcome = resolve_outcome(setup, m5.iloc[i + 1:i + 1 + engine.FORWARD_BARS])
        rows.append({"candle_time": str(ts), "signal": setup.get("signal", "NO_TRADE"), "strategy": setup.get("strategy", "NONE"), "valid": bool(setup.get("valid")), "trade_levels": setup.get("trade_levels"), "result": outcome["result"], "r_multiple": outcome["r_multiple"], "resolved_at": outcome.get("resolved_at"), "engine_version": engine.ENGINE_VERSION})
    summary = summarize_rows(rows)
    return {"status": "completed", "engine_version": engine.ENGINE_VERSION, "symbol": symbol, "candles_evaluated": len(rows), "signals": sum(r["valid"] for r in rows), "wins": summary["wins"], "losses": summary["losses"], "ambiguous": summary["ambiguous"], "open": summary["open"], "net_r": summary["net_r"], "performance": summary, "rows": rows, "live_orders_allowed": False, "m15_policy": "CLOSED_AT_M5_CLOSE_MINUS_15M", "lookahead_safe": True, "warmup_bars": 60}
