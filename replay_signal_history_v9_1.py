"""V9.1 historical replay using the same H1/M15/M5 engine as live scanning."""
from __future__ import annotations
import argparse, json, os
from datetime import datetime, timezone, timedelta
import pandas as pd
from zoneinfo import ZoneInfo
import engine_v9_1 as engine
from signal_history import history
from lse import LSE

BANGKOK = ZoneInfo("Asia/Bangkok")
SYMBOLS = {"BTC": "BTC/USD", "GOLD": "XAU/USD"}


def _bounds(start_text, end_text):
    start = datetime.fromisoformat(start_text).replace(tzinfo=BANGKOK)
    end = datetime.fromisoformat(end_text).replace(tzinfo=BANGKOK) + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _normalize(raw):
    rows = raw.get("data") if isinstance(raw, dict) else raw
    if isinstance(rows, dict):
        rows = rows.get("data") or rows.get("rows") or rows.get("candles")
    if rows is None:
        rows = []
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    if "datetime" not in df.columns:
        for c in ("timestamp", "time", "date", "ts"):
            if c in df.columns:
                df = df.rename(columns={c: "datetime"})
                break
    rename = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
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
        chunk_end = min(cursor + timedelta(days=chunk_days), end)
        raw = client.candles(
            SYMBOLS[symbol],
            timeframe,
            start=cursor.date().isoformat(),
            end=chunk_end.date().isoformat(),
            limit=200,
            order="desc",
        )
        frame = _normalize(raw)
        if not frame.empty:
            parts.append(frame)
        cursor = chunk_end
    if not parts:
        raise RuntimeError(f"LSE returned no {timeframe} candles for {symbol}")
    return (
        pd.concat(parts, ignore_index=True)
        .sort_values("datetime")
        .drop_duplicates("datetime")
        .reset_index(drop=True)
    )


def _context(frame, ts):
    return frame[frame["datetime"] <= pd.Timestamp(ts)].reset_index(drop=True)


def _resample(m5, minutes):
    return (
        m5.set_index("datetime")[["open", "high", "low", "close", "volume"]]
        .resample(f"{minutes}min", label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index()
    )


def _resolve(direction, entry, sl, tp, future):
    risk = abs(entry - sl)
    rr = abs(tp - entry) / risk if risk else 0.0
    for _, c in future.iterrows():
        high, low = float(c.high), float(c.low)
        hit_sl = low <= sl if direction == "BUY" else high >= sl
        hit_tp = high >= tp if direction == "BUY" else low <= tp
        when = str(c.datetime)
        if hit_sl and hit_tp:
            return "AMBIGUOUS", 0.0, when
        if hit_tp:
            return "WIN", rr, when
        if hit_sl:
            return "LOSS", -1.0, when
    return "OPEN", None, None


def replay_symbol(symbol, start, end, dry_run=False):
    m5 = _fetch(symbol, start - timedelta(days=14), end, "5m", 6)
    if len(m5) < 150:
        raise RuntimeError(f"Not enough LSE M5 history for {symbol}: {len(m5)}")
    m15, h1 = _resample(m5, 15), _resample(m5, 60)
    generated = inserted = 0
    outcomes = {"WIN": 0, "LOSS": 0, "AMBIGUOUS": 0, "OPEN": 0, "NO_TRADE": 0}
    rejected = {}
    used = set()
    engine.MIN_RISK_REWARD = 1.0
    engine.RISK_REWARD = max(float(os.getenv("RISK_REWARD", "1.0")), 1.0)
    forward = int(getattr(engine, "FORWARD_BARS", 12))
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)

    for i in range(100, len(m5) - 1):
        ts = pd.Timestamp(m5.iloc[i].datetime)
        if ts < start_ts or ts >= end_ts:
            continue
        m5c = m5.iloc[: i + 1].reset_index(drop=True)
        m15c = _context(m15, ts)
        h1c = _context(h1, ts)
        if len(m15c) < 60 or len(h1c) < 60:
            continue

        setup = engine.analyze_structure_setup(m5c, m15c, h1c, len(m5c) - 1)
        setup["candle_time"] = ts.isoformat()
        setup["closed_candle"] = ts.isoformat()
        setup["symbol"] = symbol
        setup["engine_version"] = engine.ENGINE_VERSION
        signal = setup.get("signal")
        levels = setup.get("trade_levels") or {}
        rr = float(levels.get("effective_rr", levels.get("risk_reward", 0)) or 0)
        valid = signal in ("BUY", "SELL") and bool(levels.get("valid")) and rr >= 1.0
        setup["valid"] = valid
        key = setup.get("setup_key") or f"{symbol}|{ts.isoformat()}|{signal}"

        if not valid or key in used:
            reason = setup.get("rejection_reasons") or ([] if valid else ["NO_TRADE_REASON_UNSPECIFIED"])
            if key in used:
                reason = ["DUPLICATE_SETUP"]
            for r in reason:
                rejected[r] = rejected.get(r, 0) + 1
            outcomes["NO_TRADE"] += 1
            generated += 1

            # IMPORTANT: NO_TRADE must have a stable primary key or it is silently
            # rejected by SignalHistory.record_no_trade(). This also makes replay
            # idempotent when the same historical range is run again.
            no_trade_id = f"REPLAY-V91-{symbol}-{ts.strftime('%Y%m%dT%H%MZ')}-NO_TRADE"
            payload = {
                **setup,
                "signal_id": no_trade_id,
                "signal": "NO_TRADE",
                "result": "NO_TRADE",
                "replay": True,
                "replay_source": "LSE_HISTORICAL_OHLCV",
                "created_at": ts.isoformat(),
                "no_trade_reasons": reason,
                "rejection_reasons": reason,
            }
            if not dry_run and history.record_no_trade(payload):
                inserted += 1
            continue

        used.add(key)
        generated += 1
        sid = f"REPLAY-V91-{symbol}-{ts.strftime('%Y%m%dT%H%MZ')}-{signal}"
        payload = {
            **setup,
            "signal_id": sid,
            "signal": signal,
            "replay": True,
            "replay_source": "LSE_HISTORICAL_OHLCV",
            "created_at": ts.isoformat(),
            "pattern_signal": signal,
            "m5_direction": signal,
            "v9_1_setup": setup,
            "trade_levels": levels,
        }
        result, r, when = _resolve(
            signal,
            float(levels["entry"]),
            float(levels["sl"]),
            float(levels["tp"]),
            m5.iloc[i + 1 : i + 1 + forward + 1],
        )
        outcomes[result] += 1
        if not dry_run:
            if history.record_signal(payload):
                inserted += 1
            if result != "OPEN":
                history.set_result(sid, result, r, when)

    return {
        "symbol": symbol,
        "engine_version": engine.ENGINE_VERSION,
        "provider": "LSE",
        "generated": generated,
        "inserted": inserted,
        "outcomes": outcomes,
        "rejected": dict(sorted(rejected.items(), key=lambda x: x[1], reverse=True)[:20]),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--symbol", choices=["BTC", "GOLD", "ALL"], default="ALL")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    start, end = _bounds(a.start, a.end)
    symbols = ["BTC", "GOLD"] if a.symbol == "ALL" else [a.symbol]
    results = []
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
    status = "completed" if all(r.get("status") != "failed" for r in results) else "failed"
    # Keep the final result on ONE line so replay_web can reliably parse it.
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
