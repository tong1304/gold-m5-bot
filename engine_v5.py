import os, math, logging
from datetime import datetime, timezone
import pandas as pd
from flask import Flask, jsonify
import engine_v42 as base

ENGINE_VERSION = "5.0"
logger = logging.getLogger(__name__)
app = Flask(__name__)

# Reuse the established signal/pattern engine while replacing its execution,
# performance, and live-safety layer with conservative v5 behavior.
for _name in (
    "SYMBOL", "TIMEFRAME", "MINIMUM_ATR", "MIN_STOP_ATR", "MAX_STOP_ATR",
    "SPREAD", "SLIPPAGE", "BREAK_EVEN", "BREAK_EVEN_R", "FORWARD_BARS",
    "MIN_RISK_REWARD", "RISK_REWARD", "MIN_SCORE", "SELL_MIN_SCORE",
    "MIN_PATTERN_QUALITY", "SELL_MIN_PATTERN_QUALITY", "MIN_TRIGGER_QUALITY",
    "SELL_MIN_TRIGGER_QUALITY", "MIN_HISTORICAL_SAMPLE", "SIGNAL_HISTORY_POINTS",
    "ALLOW_OVERLAPPING_TRADES", "TIMEZONE_NAME", "LOCAL_TIMEZONE",
    "TWELVE_DATA_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"
):
    globals()[_name] = getattr(base, _name)

MAX_LIVE_SPREAD = float(os.getenv("MAX_LIVE_SPREAD", "0.50"))
MAX_LIVE_SLIPPAGE = float(os.getenv("MAX_LIVE_SLIPPAGE", "0.30"))
MAX_DATA_AGE_SECONDS = int(os.getenv("MAX_DATA_AGE_SECONDS", "420"))
MAX_PRICE_JUMP_ATR = float(os.getenv("MAX_PRICE_JUMP_ATR", "1.50"))
DAILY_LOSS_LIMIT_R = float(os.getenv("DAILY_LOSS_LIMIT_R", "-3.0"))
MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))
MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", "5"))
INTRABAR_AMBIGUITY_POLICY = "STOP_FIRST"


def _f(value, default=0.0):
    try:
        value = float(value)
        return default if not math.isfinite(value) else value
    except Exception:
        return default


def calculate_execution_price(raw_price, side, spread=None, slippage=None, is_entry=True):
    spread = _f(SPREAD if spread is None else spread)
    slippage = _f(SLIPPAGE if slippage is None else slippage)
    adverse = spread / 2.0 + slippage
    side = str(side).upper()
    if side == "BUY":
        return _f(raw_price) + adverse if is_entry else _f(raw_price) - adverse
    if side == "SELL":
        return _f(raw_price) - adverse if is_entry else _f(raw_price) + adverse
    raise ValueError("Invalid side")


def calculate_trade_levels(df, i, direction, entry_price=None):
    levels = base.calculate_trade_levels(df, i, direction, entry_price)
    risk = _f(levels.get("risk"))
    reward = _f(levels.get("reward"))
    levels["valid"] = risk > 0
    levels["effective_risk"] = round(risk, 5)
    levels["effective_reward"] = round(reward, 5)
    levels["effective_rr"] = round(reward / risk, 3) if risk else 0.0
    return levels


def validate_trade_levels(entry, sl, tp, spread=None, slippage=None):
    entry, sl, tp = map(_f, (entry, sl, tp))
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    cost = _f(SPREAD if spread is None else spread) + 2 * _f(SLIPPAGE if slippage is None else slippage)
    net_reward = max(0.0, reward - cost)
    effective_rr = net_reward / risk if risk else 0.0
    valid = risk > 0 and reward > 0 and effective_rr >= _f(MIN_RISK_REWARD)
    return {
        "valid": valid,
        "risk": round(risk, 5),
        "reward": round(reward, 5),
        "effective_rr": round(effective_rr, 3),
        "cost_price": round(cost, 5),
        "reason": None if valid else "INVALID_OR_LOW_EFFECTIVE_RR",
    }


def simulate_trade(df, signal_index, direction, setup_levels):
    entry_index = signal_index + 1
    if entry_index >= len(df):
        return None

    raw_entry = _f(df.iloc[entry_index]["open"])
    entry = calculate_execution_price(raw_entry, direction)
    levels = calculate_trade_levels(df, signal_index, direction, entry)
    original_sl = _f(levels.get("sl"))
    tp = _f(levels.get("tp"))
    risk = abs(entry - original_sl)
    validation = validate_trade_levels(entry, original_sl, tp)
    if not validation["valid"] or risk <= 0:
        return None

    end_index = min(len(df), entry_index + int(FORWARD_BARS) + 1)
    result = "TIMEOUT"
    exit_price = _f(df.iloc[end_index - 1]["close"])
    exit_index = end_index - 1
    max_favorable = -1e9
    max_adverse = 1e9
    moved_to_be = False
    one_r_reached = False
    tp_reached = False
    bars_to_1r = None
    bars_to_tp = None
    sl = original_sl

    for j in range(entry_index, end_index):
        candle = df.iloc[j]
        high = _f(candle["high"])
        low = _f(candle["low"])
        favorable = (high - entry) / risk if direction == "BUY" else (entry - low) / risk
        adverse = (low - entry) / risk if direction == "BUY" else (entry - high) / risk
        max_favorable = max(max_favorable, favorable)
        max_adverse = min(max_adverse, adverse)

        if favorable >= 1.0 and not one_r_reached:
            one_r_reached = True
            bars_to_1r = j - entry_index
        if favorable >= _f(levels.get("risk_reward"), 1.5) and not tp_reached:
            tp_reached = True
            bars_to_tp = j - entry_index

        stop_touch = low <= sl if direction == "BUY" else high >= sl
        target_touch = high >= tp if direction == "BUY" else low <= tp

        # Candle OHLC cannot reveal tick order. STOP_FIRST is deliberately conservative.
        if stop_touch:
            exit_price = calculate_execution_price(sl, direction, is_entry=False)
            exit_index = j
            result = "BREAKEVEN" if moved_to_be else "LOSS"
            break
        if target_touch:
            exit_price = calculate_execution_price(tp, direction, is_entry=False)
            exit_index = j
            result = "WIN"
            break

        # BE is a candle-close state transition, never an intrabar free move.
        if BREAK_EVEN and not moved_to_be and favorable >= _f(BREAK_EVEN_R):
            close = _f(candle["close"])
            close_favorable = (close - entry) / risk if direction == "BUY" else (entry - close) / risk
            if close_favorable >= _f(BREAK_EVEN_R):
                moved_to_be = True
                sl = entry

    if result == "TIMEOUT":
        close = _f(df.iloc[exit_index]["close"])
        exit_price = calculate_execution_price(close, direction, is_entry=False)

    r = (exit_price - entry) / risk if direction == "BUY" else (entry - exit_price) / risk
    if result == "BREAKEVEN":
        r = 0.0

    if result == "WIN":
        diagnosis = "TP_WIN"
    elif result == "BREAKEVEN":
        diagnosis = "BE_PROTECTED"
    elif result == "LOSS" and max_favorable >= 1.0:
        diagnosis = "LOSS_AFTER_1R"
    elif result == "LOSS":
        diagnosis = "EARLY_ENTRY_FAILURE"
    elif max_favorable >= 1.0:
        diagnosis = "TIMEOUT_AFTER_1R"
    elif max_favorable > 0:
        diagnosis = "TIMEOUT_WITH_PARTIAL_PROFIT"
    else:
        diagnosis = "TIMEOUT_WITHOUT_PROFIT"

    reference_exit = _f(df.iloc[exit_index]["close"])
    return {
        "setup_index": signal_index,
        "entry_index": entry_index,
        "exit_index": exit_index,
        "setup_time": str(df.iloc[signal_index]["datetime"]),
        "entry_time": str(df.iloc[entry_index]["datetime"]),
        "exit_time": str(df.iloc[exit_index]["datetime"]),
        "direction": direction,
        "entry_raw": round(raw_entry, 5),
        "entry": round(entry, 5),
        "sl": round(original_sl, 5),
        "tp": round(tp, 5),
        "exit": round(exit_price, 5),
        "result": result,
        "r": round(r, 4),
        "r_no_be": round(r, 4),
        "result_no_be": result,
        "be_delta_r": 0.0,
        "mae_r": round(max_adverse, 4),
        "mfe_r": round(max_favorable, 4),
        "break_even_used": moved_to_be,
        "one_r_reached": one_r_reached,
        "tp_reached": tp_reached,
        "bars_to_1r": bars_to_1r,
        "bars_to_tp": bars_to_tp,
        "timeout_mfe_ge_1r": max_favorable >= 1.0,
        "timeout_mfe_ge_tp": tp_reached,
        "exit_diagnosis": diagnosis,
        "risk": round(risk, 5),
        "reward": round(abs(tp - entry), 5),
        "risk_reward": round(_f(levels.get("risk_reward")), 3),
        "execution_cost": round(abs(entry - raw_entry) + abs(exit_price - reference_exit), 5),
        "intrabar_assumption": INTRABAR_AMBIGUITY_POLICY,
    }


def calculate_trade_statistics(trades):
    counts = {key: sum(1 for t in trades if t.get("result") == key) for key in ("WIN", "LOSS", "BREAKEVEN", "TIMEOUT")}
    total = len(trades)
    resolved = counts["WIN"] + counts["LOSS"] + counts["BREAKEVEN"]
    net = sum(_f(t.get("r")) for t in trades)
    profit = sum(max(_f(t.get("r")), 0) for t in trades)
    loss = abs(sum(min(_f(t.get("r")), 0) for t in trades))
    pf = profit / loss if loss else (None if profit == 0 else float("inf"))

    current_streak = longest_streak = 0
    equity = peak = max_drawdown = 0.0
    for trade in trades:
        if trade.get("result") == "LOSS":
            current_streak += 1
            longest_streak = max(longest_streak, current_streak)
        else:
            current_streak = 0
        equity += _f(trade.get("r"))
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    return {
        "trades": total,
        "wins": counts["WIN"],
        "losses": counts["LOSS"],
        "breakevens": counts["BREAKEVEN"],
        "timeouts": counts["TIMEOUT"],
        "resolved": resolved,
        "outcome_counts": counts,
        "net_profit_r": round(net, 4),
        "gross_expectancy_r": round(net / total, 4) if total else 0.0,
        "net_expectancy_r": round(net / total, 4) if total else 0.0,
        "expectancy_r": round(net / total, 4) if total else 0.0,
        "win_rate_percent": round(counts["WIN"] / resolved * 100, 2) if resolved else 0.0,
        "loss_rate_percent": round(counts["LOSS"] / total * 100, 2) if total else 0.0,
        "breakeven_rate_percent": round(counts["BREAKEVEN"] / total * 100, 2) if total else 0.0,
        "timeout_rate_percent": round(counts["TIMEOUT"] / total * 100, 2) if total else 0.0,
        "profit_factor": None if pf is None or not math.isfinite(pf) else round(pf, 3),
        "average_mae_r": round(sum(_f(t.get("mae_r")) for t in trades) / total, 4) if total else 0.0,
        "average_mfe_r": round(sum(_f(t.get("mfe_r")) for t in trades) / total, 4) if total else 0.0,
        "longest_losing_streak": longest_streak,
        "max_drawdown_r": round(max_drawdown, 4),
        "sample_sufficient": total >= int(MIN_HISTORICAL_SAMPLE),
    }


def empirical_probability(trades, group_name="all"):
    resolved = [t for t in trades if t.get("result") in ("WIN", "LOSS", "BREAKEVEN")]
    wins = sum(1 for t in resolved if t.get("result") == "WIN")
    n = len(resolved)
    return {
        "group": group_name,
        "wins": wins,
        "resolved": n,
        "probability_percent": round(wins / n * 100, 2) if n else None,
        "sample_size": n,
        "sample_sufficient": n >= int(MIN_HISTORICAL_SAMPLE),
        "minimum_sample_required": int(MIN_HISTORICAL_SAMPLE),
        "note": "Resolved-trade win rate only; TIMEOUT is excluded from this resolved metric and is always included in primary expectancy/outcome counts.",
    }


def evaluate_live_risk_guard(spread=None, max_spread=None, data_age_seconds=0, price_jump_atr=0, daily_loss_r=0, consecutive_losses=0, trades_today=0, slippage=None):
    max_spread = _f(MAX_LIVE_SPREAD if max_spread is None else max_spread)
    reasons = []
    if spread is None:
        reasons.append("SPREAD_UNAVAILABLE")
    elif _f(spread) > max_spread:
        reasons.append("SPREAD_TOO_HIGH")
    if data_age_seconds is None or _f(data_age_seconds) > MAX_DATA_AGE_SECONDS:
        reasons.append("STALE_DATA")
    if _f(price_jump_atr) > MAX_PRICE_JUMP_ATR:
        reasons.append("PRICE_JUMP_TOO_HIGH")
    if _f(daily_loss_r) <= DAILY_LOSS_LIMIT_R:
        reasons.append("DAILY_LOSS_LIMIT")
    if int(consecutive_losses) >= MAX_CONSECUTIVE_LOSSES:
        reasons.append("CONSECUTIVE_LOSS_LIMIT")
    if int(trades_today) >= MAX_TRADES_PER_DAY:
        reasons.append("MAX_TRADES_PER_DAY")
    if slippage is not None and _f(slippage) > MAX_LIVE_SLIPPAGE:
        reasons.append("SLIPPAGE_TOO_HIGH")
    return {
        "allowed": not reasons,
        "reasons": reasons,
        "measurements": {
            "spread": spread,
            "data_age_seconds": data_age_seconds,
            "price_jump_atr": price_jump_atr,
            "daily_loss_r": daily_loss_r,
            "consecutive_losses": consecutive_losses,
            "trades_today": trades_today,
            "slippage": slippage,
        },
    }


def build_walk_forward_windows(n, train_bars=400, test_bars=200, step_bars=200):
    windows = []
    start = 0
    while start + train_bars + test_bars <= n:
        windows.append({
            "train_start": start,
            "train_end": start + train_bars,
            "test_start": start + train_bars,
            "test_end": start + train_bars + test_bars,
        })
        start += step_bars
    return windows


def run_walk_forward_backtest(df, train_bars=400, test_bars=200, step_bars=200):
    windows = build_walk_forward_windows(len(df), train_bars, test_bars, step_bars)
    results = []
    for window in windows:
        test = df.iloc[window["test_start"]:window["test_end"]].copy()
        test = base.calculate_indicators(test)
        trades = []
        for i in range(55, len(test) - 1):
            result = base.analyze_candle(test, i, include_trade_levels=True)
            if result.get("signal") in ("BUY", "SELL"):
                trade = simulate_trade(test, i, result["signal"], result.get("trade_levels"))
                if trade:
                    trades.append(trade)
        results.append({**window, "stats": calculate_trade_statistics(trades)})
    return {"windows": results, "windows_count": len(results), "sample_sufficient": len(results) >= 2}


def run_backtest(df, test_points=200):
    df = base.remove_incomplete_last_candle(df.copy())
    if len(df) <= 60:
        raise RuntimeError("Not enough closed candles for backtest")
    df = base.calculate_indicators(df)
    test_points = min(int(test_points), len(df) - 60)
    start = max(55, len(df) - test_points)
    trades = []
    next_available = start

    for i in range(start, len(df) - 1):
        result = base.analyze_candle(df, i, include_trade_levels=True)
        if not result.get("hard_filter", {}).get("passed", False):
            continue
        direction = result.get("signal")
        levels = result.get("trade_levels")
        if direction not in ("BUY", "SELL") or not levels:
            continue
        if not ALLOW_OVERLAPPING_TRADES and i < next_available:
            continue
        trade = simulate_trade(df, i, direction, levels)
        if not trade:
            continue
        trade["score"] = result.get("score")
        trade["patterns"] = result.get("patterns", [])
        trade["primary_pattern"] = (result.get("patterns") or [None])[0]
        trade["regime"] = result.get("market_regime", {}).get("regime")
        trade["location_zone"] = result.get("location", {}).get("zone")
        trades.append(trade)
        if not ALLOW_OVERLAPPING_TRADES:
            next_available = trade["exit_index"] + 1

    stats = calculate_trade_statistics(trades)
    return {
        "status": "completed",
        "engine_version": ENGINE_VERSION,
        "system": "XAU/USD Real-Money Validation Engine v5",
        "symbol": SYMBOL,
        "timeframe": "M5",
        "candles_available": len(df),
        "closed_candles_used": len(df),
        "test_points": test_points,
        "test_start": str(df.iloc[start]["datetime"]),
        "test_end": str(df.iloc[-1]["datetime"]),
        "signals": {
            "buy": sum(t["direction"] == "BUY" for t in trades),
            "sell": sum(t["direction"] == "SELL" for t in trades),
            "total": len(trades),
        },
        "results": stats["outcome_counts"],
        "performance": stats,
        "historical_probability": empirical_probability(trades),
        "recent_trades": trades[-20:],
        "rules": {
            "engine_version": ENGINE_VERSION,
            "entry": "NEXT CANDLE OPEN (THEORETICAL)",
            "spread": SPREAD,
            "slippage": SLIPPAGE,
            "maximum_live_spread": MAX_LIVE_SPREAD,
            "maximum_live_slippage": MAX_LIVE_SLIPPAGE,
            "intrabar_ambiguity_policy": INTRABAR_AMBIGUITY_POLICY,
            "timeout_in_primary_expectancy": True,
            "historical_probability_excludes_timeout": True,
        },
        "warning": "V5 validation model only. OHLC data has no intrabar tick sequence. Ambiguous candles use STOP_FIRST. Execution is modeled, not broker-confirmed. Do not treat historical win rate as probability of the next trade.",
    }


get_market_data = base.get_market_data
remove_incomplete_last_candle = base.remove_incomplete_last_candle
calculate_indicators = base.calculate_indicators
analyze_candle = base.analyze_candle
score_bucket = getattr(base, "score_bucket", lambda value: str(value))
send_telegram = base.send_telegram
now_local = base.now_local
is_last_candle_closed = base.is_last_candle_closed


@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "version": ENGINE_VERSION,
        "service": "XAU/USD M5 Real-Money Validation Engine",
        "symbol": SYMBOL,
        "timeframe": "M5",
        "safety_policy": "PAPER_VALIDATION_ONLY",
        "intrabar_policy": INTRABAR_AMBIGUITY_POLICY,
    })


@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "engine_version": ENGINE_VERSION,
        "symbol": SYMBOL,
        "timeframe": "M5",
        "twelve_data": bool(TWELVE_DATA_API_KEY),
        "telegram": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        "safety_policy": "PAPER_VALIDATION_ONLY",
        "timestamp": now_local(),
    })


@app.route("/backtest")
@app.route("/backtest/<int:points>")
def backtest_route(points=200):
    try:
        return jsonify(run_backtest(get_market_data(max(points + 200, 400)), points))
    except Exception:
        logger.exception("Backtest failed")
        return jsonify({"status": "error", "engine_version": ENGINE_VERSION, "symbol": SYMBOL, "message": "Internal server error"}), 500


@app.route("/signal")
def signal_route():
    try:
        df = get_market_data(1000)
        closed = remove_incomplete_last_candle(df)
        if closed.empty:
            return jsonify({"status": "waiting", "signal": "NO_TRADE", "reason": "NO_CLOSED_CANDLE"})
        timestamp = pd.Timestamp(closed.iloc[-1]["datetime"])
        timestamp = timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
        age = (datetime.now(timezone.utc) - timestamp.to_pydatetime()).total_seconds()
        guard = evaluate_live_risk_guard(spread=SPREAD, data_age_seconds=age)
        if not guard["allowed"]:
            return jsonify({"status": "blocked", "signal": "NO_TRADE", "risk_guard": guard, "candle_closed": True})
        closed = calculate_indicators(closed)
        result = analyze_candle(closed, len(closed) - 1, True)
        result["engine_version"] = ENGINE_VERSION
        result["risk_guard"] = guard
        result["safety_policy"] = "PAPER_VALIDATION_ONLY"
        if result.get("valid"):
            result["entry_rule"] = "NEXT CANDLE OPEN (THEORETICAL)"
            result["live_execution_warning"] = "Telegram arrival is not a broker-confirmed next-open fill."
        return jsonify(result)
    except Exception:
        logger.exception("Signal failed")
        return jsonify({"status": "error", "engine_version": ENGINE_VERSION, "symbol": SYMBOL, "message": "Internal server error"}), 500


@app.route("/diagnostics")
def diagnostics():
    try:
        df = get_market_data(1000)
        closed = remove_incomplete_last_candle(df)
        return jsonify({"status": "ok", "engine_version": ENGINE_VERSION, "symbol": SYMBOL, "closed_candles": len(closed), "safety_policy": "PAPER_VALIDATION_ONLY"})
    except Exception:
        logger.exception("Diagnostics failed")
        return jsonify({"status": "error", "engine_version": ENGINE_VERSION, "symbol": SYMBOL, "message": "Internal server error"}), 500
