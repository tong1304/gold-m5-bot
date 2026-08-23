"""V10.3 historical replay: M15 context + M5 setup/trigger, no H1.
Uses the same live ``analyze_structure_setup`` path and persists historical outcomes.
Replay is dry with respect to Telegram/orders.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone, timedelta

import pandas as pd
from zoneinfo import ZoneInfo
from lse import LSE
import engine_v9_2 as engine
from signal_history import history

BANGKOK = ZoneInfo("Asia/Bangkok")
SYMBOLS = {"BTC": "BTC/USD", "GOLD": "XAU/USD"}


def _bounds(a, b):
    s = datetime.fromisoformat(a)
    e = datetime.fromisoformat(b)
    if s.tzinfo is None:
        s = s.replace(tzinfo=BANGKOK)
    if e.tzinfo is None:
        e = e.replace(tzinfo=BANGKOK)
    e = e + timedelta(days=1) if e.time() == datetime.min.time() else e
    return s.astimezone(timezone.utc), e.astimezone(timezone.utc)


def _normalize(raw):
    rows = raw.get("data") if isinstance(raw, dict) else raw
    if isinstance(rows, dict):
        rows = rows.get("data") or rows.get("rows") or rows.get("candles")
    df = pd.DataFrame(rows or [])
    if df.empty:
        return df
    if "datetime" not in df.columns:
        for c in ("timestamp", "time", "date", "ts"):
            if c in df.columns:
                df = df.rename(columns={c: "datetime"})
                break
    df = df.rename(columns={k: v for k, v in {
        "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"
    }.items() if k in df.columns})
    required = ["datetime", "open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError(f"LSE response missing columns: {missing}")
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return (
        df.dropna(subset=required)
        .sort_values("datetime")
        .drop_duplicates("datetime")
        .reset_index(drop=True)
    )


def _fetch(symbol, start, end, timeframe="5m", chunk_days=6):
    key = os.getenv("LSE_API_KEY", "").strip() or os.getenv("LSE_KEY", "").strip()
    if not key:
        raise RuntimeError("LSE_API_KEY/LSE_KEY is not configured")
    client = LSE(api_key=key)
    parts = []
    cursor = start
    while cursor < end:
        ce = min(cursor + timedelta(days=chunk_days), end)
        raw = client.candles(
            SYMBOLS[symbol], timeframe,
            start=cursor.date().isoformat(), end=ce.date().isoformat(),
            limit=200, order="desc"
        )
        frame = _normalize(raw)
        if not frame.empty:
            parts.append(frame)
        cursor = ce
    if not parts:
        raise RuntimeError(f"LSE returned no {timeframe} candles for {symbol}")
    return (
        pd.concat(parts, ignore_index=True)
        .sort_values("datetime")
        .drop_duplicates("datetime")
        .reset_index(drop=True)
    )


def _resample(m5, minutes):
    return (
        m5.set_index("datetime")[["open", "high", "low", "close", "volume"]]
        .resample(f"{minutes}min", label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index()
    )


def _context(frame, ts):
    return frame[frame.datetime <= pd.Timestamp(ts)].reset_index(drop=True)


def _resolve(direction, entry, sl, tp, future):
    risk = abs(entry - sl)
    rr = abs(tp - entry) / risk if risk else 0.0
    for _, c in future.iterrows():
        hi, lo = float(c.high), float(c.low)
        hit_sl = lo <= sl if direction == "BUY" else hi >= sl
        hit_tp = hi >= tp if direction == "BUY" else lo <= tp
        if hit_sl and hit_tp:
            return "AMBIGUOUS", 0.0, str(c.datetime)
        if hit_tp:
            return "WIN", rr, str(c.datetime)
        if hit_sl:
            return "LOSS", -1.0, str(c.datetime)
    return "OPEN", None, None


def _empty_strategy_stats():
    return {
        "evaluated": 0, "pass": 0, "fail": 0, "not_applicable": 0,
        "wins": 0, "losses": 0, "open": 0, "ambiguous": 0, "no_trade": 0,
        "reasons": {},
    }


def aggregate_strategy_stats(candidates, result_by_strategy=None):
    """Aggregate exactly the candidate records emitted by the live V10.3 engine."""
    result_by_strategy = result_by_strategy or {}
    stats = {}
    for candidate in candidates or []:
        name = str(candidate.get("strategy") or "UNKNOWN")
        st = stats.setdefault(name, _empty_strategy_stats())
        st["evaluated"] += 1
        status = str(candidate.get("status") or "FAIL").lower()
        if status in ("pass", "fail", "not_applicable"):
            st[status] += 1
        else:
            st["fail"] += 1
        for reason in candidate.get("reason") or []:
            key = str(reason)
            st["reasons"][key] = st["reasons"].get(key, 0) + 1
    for name, result in result_by_strategy.items():
        st = stats.setdefault(name, _empty_strategy_stats())
        key = {"WIN": "wins", "LOSS": "losses", "OPEN": "open", "AMBIGUOUS": "ambiguous"}.get(result, "no_trade")
        st[key] += 1
    return stats


def replay_overall_status(results):
    """Return completed/partial/failed without hiding per-symbol failures."""
    statuses = [str(r.get("status")) for r in results]
    if statuses and all(s == "completed" for s in statuses):
        return "completed"
    if statuses and any(s == "completed" for s in statuses):
        return "partial"
    return "failed"


def replay_symbol(symbol, start, end, dry_run=False):
    m5 = _fetch(symbol, start - timedelta(days=14), end, "5m", 6)
    m15 = _resample(m5, 15)
    if len(m5) < 150 or len(m15) < 100:
        raise RuntimeError(f"Not enough history for {symbol}: M5={len(m5)} M15={len(m15)}")

    outcomes = {"WIN": 0, "LOSS": 0, "AMBIGUOUS": 0, "OPEN": 0, "NO_TRADE": 0}
    rejected = Counter()
    generated = inserted = 0
    result_by_strategy = {}
    candidate_seen = Counter()
    strategy_stats = {}
    forward = int(getattr(engine, "FORWARD_BARS", 12))
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    engine.MIN_RISK_REWARD = 1.0
    engine.RISK_REWARD = max(float(os.getenv("RISK_REWARD", "1.0")), 1.0)

    for i in range(100, len(m5) - 1):
        ts = pd.Timestamp(m5.iloc[i].datetime)
        if ts < start_ts or ts >= end_ts:
            continue
        m5c = m5.iloc[:i + 1].reset_index(drop=True)
        m15c = _context(m15, ts)
        if len(m15c) < 100:
            continue

        # IMPORTANT: this is the same live setup path used by live_scanner_v9_2.
        setup = engine.analyze_structure_setup(m5c, m15c, len(m5c) - 1)
        candidates = setup.get("strategy_candidates") or []
        strategy_stats = aggregate_strategy_stats(candidates)
        for candidate in candidates:
            candidate_seen[str(candidate.get("strategy") or "UNKNOWN")] += 1

        setup.update({
            "candle_time": ts.isoformat(),
            "closed_candle": ts.isoformat(),
            "symbol": symbol,
            "engine_version": engine.ENGINE_VERSION,
            "strategy_candidates": candidates,
            "replay": True,
            "replay_source": "LSE_HISTORICAL_OHLCV_V10.3",
        })

        signal = setup.get("signal")
        levels = setup.get("trade_levels") or {}
        try:
            rr = float(levels.get("effective_rr", levels.get("risk_reward", 0)) or 0)
            entry, sl, tp = map(float, (levels.get("entry"), levels.get("sl"), levels.get("tp")))
            levels_ready = bool(levels.get("valid")) and rr >= 1.0 and entry > 0 and sl > 0 and tp > 0
            levels_ready = levels_ready and ((signal == "BUY" and sl < entry < tp) or (signal == "SELL" and sl > entry > tp))
        except (TypeError, ValueError):
            levels_ready = False

        valid = signal in ("BUY", "SELL") and levels_ready
        setup["valid"] = valid
        strategy_name = str(setup.get("strategy") or "NONE")

        if not valid:
            reasons = setup.get("rejection_reasons") or ["NO_TRADE_REASON_UNSPECIFIED"]
            for reason in reasons:
                rejected[str(reason)] += 1
            outcomes["NO_TRADE"] += 1
            generated += 1
            sid = f"REPLAY-V103-{symbol}-{ts.strftime('%Y%m%dT%H%MZ')}-NO_TRADE"
            payload = {
                **setup, "signal_id": sid, "signal": "NO_TRADE", "result": "NO_TRADE",
                "created_at": ts.isoformat(), "no_trade_reasons": reasons,
            }
            if not dry_run and history.record_no_trade(payload):
                inserted += 1
            result_by_strategy[strategy_name] = "NO_TRADE"
            continue

        generated += 1
        sid = f"REPLAY-V103-{symbol}-{ts.strftime('%Y%m%dT%H%MZ')}-{signal}"
        payload = {
            **setup, "signal_id": sid, "signal": signal, "created_at": ts.isoformat(),
            "pattern_signal": signal, "m5_direction": signal, "strategy": strategy_name,
        }
        result, r, when = _resolve(
            signal, float(levels["entry"]), float(levels["sl"]), float(levels["tp"]),
            m5.iloc[i + 1:i + 1 + forward + 1]
        )
        outcomes[result] += 1
        result_by_strategy[strategy_name] = result
        if not dry_run:
            if history.record_signal(payload):
                inserted += 1
            if result != "OPEN":
                history.set_result(sid, result, r, when)

    # Keep all strategy names encountered in the configured engine, including strategies
    # that had zero candidates in the selected replay period.
    for name in candidate_seen:
        strategy_stats.setdefault(name, _empty_strategy_stats())
    for name, result in result_by_strategy.items():
        st = strategy_stats.setdefault(name, _empty_strategy_stats())
        key = {"WIN": "wins", "LOSS": "losses", "OPEN": "open", "AMBIGUOUS": "ambiguous"}.get(result, "no_trade")
        st[key] += 1

    return {
        "status": "completed",
        "symbol": symbol,
        "engine_version": engine.ENGINE_VERSION,
        "provider": "LSE",
        "generated": generated,
        "inserted": inserted,
        "outcomes": outcomes,
        "rejected": dict(rejected.most_common(30)),
        "strategy_stats": strategy_stats,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--symbol", choices=["BTC", "GOLD", "ALL"], default="ALL")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    start, end = _bounds(a.start, a.end)
    results = []
    symbols = ["BTC", "GOLD"] if a.symbol == "ALL" else [a.symbol]
    for s in symbols:
        try:
            results.append(replay_symbol(s, start, end, a.dry_run))
        except Exception as exc:
            results.append({
                "symbol": s,
                "engine_version": engine.ENGINE_VERSION,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            })
    status = replay_overall_status(results)
    print(json.dumps({
        "status": "dry-run" if a.dry_run and status == "completed" else status,
        "engine_version": engine.ENGINE_VERSION,
        "provider": "LSE",
        "start": a.start,
        "end": a.end,
        "results": results,
    }, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
