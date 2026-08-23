"""V10.3 historical replay: date-range simulation using real LSE OHLCV.

The requested dates are the simulation window. Internally the engine scans every
closed M5 candle in that window, using only candles available up to that point.
A 14-day warm-up is loaded before the requested start so indicators have context.
M15 is fetched from LSE directly (not rebuilt from future M5 candles).
Replay is dry with respect to Telegram/orders.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

import pandas as pd
from zoneinfo import ZoneInfo
from lse import LSE
import engine_v9_2 as engine
from signal_history import history

BANGKOK = ZoneInfo("Asia/Bangkok")
SYMBOLS = {"BTC": "BTC/USD", "GOLD": "XAU/USD"}


def _bounds(a, b):
    """Interpret date-only input as an inclusive Bangkok calendar-date range."""
    s = datetime.fromisoformat(a)
    e = datetime.fromisoformat(b)
    if s.tzinfo is None:
        s = s.replace(tzinfo=BANGKOK)
    if e.tzinfo is None:
        e = e.replace(tzinfo=BANGKOK)
    # UI sends dates, so 2026-08-24 means the whole Bangkok day.
    if e.time() == datetime.min.time():
        e += timedelta(days=1)
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
    return (df.dropna(subset=required)
              .sort_values("datetime")
              .drop_duplicates("datetime")
              .reset_index(drop=True))


def _fetch(symbol, start, end, timeframe="5m"):
    """Fetch all historical bars without silently losing data to LSE limit=200.

    The previous implementation advanced by several days while requesting only
    200 rows, which can discard a large part of M5 history.  Here each request is
    smaller than the 200-row provider cap and uses timestamps, so the requested
    date range is actually covered.
    """
    key = os.getenv("LSE_API_KEY", "").strip() or os.getenv("LSE_KEY", "").strip()
    if not key:
        raise RuntimeError("LSE_API_KEY/LSE_KEY is not configured")
    client = LSE(api_key=key)

    # Keep every request below the provider's 200-row limit, with a small safety
    # margin. M5: <= 16h40m; M15: <= 50h. Use shorter windows to avoid edge loss.
    chunk = timedelta(hours=12) if timeframe == "5m" else timedelta(hours=36)
    parts = []
    cursor = start
    while cursor < end:
        ce = min(cursor + chunk, end)
        raw = client.candles(
            SYMBOLS[symbol], timeframe,
            start=cursor.isoformat(),
            end=ce.isoformat(),
            limit=200,
            order="asc",
        )
        frame = _normalize(raw)
        if not frame.empty:
            parts.append(frame)
        # Always advance by our requested window; overlap is removed after merge.
        cursor = ce

    if not parts:
        raise RuntimeError(f"LSE returned no {timeframe} candles for {symbol}")
    return (pd.concat(parts, ignore_index=True)
              .sort_values("datetime")
              .drop_duplicates("datetime")
              .reset_index(drop=True))


def _context(frame, ts):
    return frame[frame.datetime <= pd.Timestamp(ts)].reset_index(drop=True)


def _resolve(direction, entry, sl, tp, future):
    risk = abs(entry - sl)
    rr = abs(tp - entry) / risk if risk else 0.0
    for _, c in future.iterrows():
        hi, lo = float(c.high), float(c.low)
        hit_sl = lo <= sl if direction == "BUY" else hi >= sl
        hit_tp = hi >= tp if direction == "BUY" else lo <= tp
        # Intrabar OHLC cannot tell which level was hit first.
        if hit_sl and hit_tp:
            return "AMBIGUOUS", 0.0, str(c.datetime)
        if hit_tp:
            return "WIN", rr, str(c.datetime)
        if hit_sl:
            return "LOSS", -1.0, str(c.datetime)
    return "OPEN", None, None


def _empty_strategy_stats():
    return {"evaluated":0,"pass":0,"fail":0,"not_applicable":0,"wins":0,"losses":0,"open":0,"ambiguous":0,"no_trade":0,"reasons":{}}


def aggregate_strategy_stats(candidates, results_by_strategy=None):
    results_by_strategy = results_by_strategy or {}
    stats = {}
    for candidate in candidates or []:
        name = str(candidate.get("strategy") or "UNKNOWN")
        st = stats.setdefault(name, _empty_strategy_stats())
        st["evaluated"] += 1
        status = str(candidate.get("status") or "FAIL").lower()
        st[status if status in ("pass","fail","not_applicable") else "fail"] += 1
        for reason in candidate.get("reason") or []:
            reason = str(reason)
            st["reasons"][reason] = st["reasons"].get(reason, 0) + 1
    for name, results in (results_by_strategy or {}).items():
        st = stats.setdefault(name, _empty_strategy_stats())
        for result in results if isinstance(results, list) else [results]:
            key = {"WIN":"wins","LOSS":"losses","OPEN":"open","AMBIGUOUS":"ambiguous"}.get(result, "no_trade")
            st[key] += 1
    return stats


def replay_overall_status(results):
    statuses = [str(r.get("status")) for r in results]
    if statuses and all(s == "completed" for s in statuses):
        return "completed"
    if any(s == "completed" for s in statuses):
        return "partial"
    return "failed"


def replay_symbol(symbol, start, end, dry_run=False):
    warmup = timedelta(days=14)
    history_start = start - warmup
    m5 = _fetch(symbol, history_start, end, "5m")
    m15 = _fetch(symbol, history_start, end, "15m")
    if len(m5) < 150 or len(m15) < 100:
        raise RuntimeError(f"Not enough history for {symbol}: M5={len(m5)} M15={len(m15)}")

    outcomes = {"WIN":0,"LOSS":0,"AMBIGUOUS":0,"OPEN":0,"NO_TRADE":0}
    rejected = Counter()
    generated = inserted = 0
    all_candidates = []
    results_by_strategy = defaultdict(list)
    forward = int(getattr(engine, "FORWARD_BARS", 12))
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    engine.MIN_RISK_REWARD = 1.0
    engine.RISK_REWARD = max(float(os.getenv("RISK_REWARD", "1.0")), 1.0)

    # One complete day can contain hundreds of evaluations. This is intentional:
    # the user selects a DAY; the engine internally evaluates each closed M5 bar.
    for i in range(100, len(m5) - 1):
        ts = pd.Timestamp(m5.iloc[i].datetime)
        if ts < start_ts or ts >= end_ts:
            continue
        m5c = m5.iloc[:i+1].reset_index(drop=True)
        m15c = _context(m15, ts)
        if len(m15c) < 100:
            continue

        setup = engine.analyze_structure_setup(m5c, m15c, len(m5c)-1)
        candidates = setup.get("strategy_candidates") or []
        all_candidates.extend(candidates)
        setup.update({
            "candle_time": ts.isoformat(), "closed_candle": ts.isoformat(), "symbol": symbol,
            "engine_version": engine.ENGINE_VERSION, "strategy_candidates": candidates,
            "replay": True, "replay_source": "LSE_HISTORICAL_OHLCV_V10.3",
            "replay_start": start_ts.isoformat(), "replay_end": end_ts.isoformat(),
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
            rejected.update(map(str, reasons))
            outcomes["NO_TRADE"] += 1
            generated += 1
            sid = f"REPLAY-V103-{symbol}-{ts.strftime('%Y%m%dT%H%MZ')}-NO_TRADE"
            payload = {**setup,"signal_id":sid,"signal":"NO_TRADE","result":"NO_TRADE","created_at":ts.isoformat(),"no_trade_reasons":reasons}
            if not dry_run and history.record_no_trade(payload):
                inserted += 1
            results_by_strategy[strategy_name].append("NO_TRADE")
            continue

        generated += 1
        sid = f"REPLAY-V103-{symbol}-{ts.strftime('%Y%m%dT%H%MZ')}-{signal}"
        payload = {**setup,"signal_id":sid,"signal":signal,"created_at":ts.isoformat(),"pattern_signal":signal,"m5_direction":signal,"strategy":strategy_name}
        result, r, when = _resolve(signal,float(levels["entry"]),float(levels["sl"]),float(levels["tp"]),m5.iloc[i+1:i+1+forward+1])
        outcomes[result] += 1
        results_by_strategy[strategy_name].append(result)
        if not dry_run:
            if history.record_signal(payload):
                inserted += 1
            if result != "OPEN":
                history.set_result(sid,result,r,when)

    # Daily summary is deliberately independent of candle-level output.
    day_rows = defaultdict(lambda: {"evaluated":0,"signals":0,"WIN":0,"LOSS":0,"OPEN":0,"AMBIGUOUS":0,"NO_TRADE":0})
    for i in range(100, len(m5) - 1):
        ts = pd.Timestamp(m5.iloc[i].datetime)
        if start_ts <= ts < end_ts:
            day_rows[ts.tz_convert(BANGKOK).date().isoformat()]["evaluated"] += 1
    # Signal counts above are global; per-day signal rows are available from DB.
    # Keep a compact deterministic date list for the UI even when there are no signals.
    requested_days=[]
    d=start_ts.tz_convert(BANGKOK).date()
    last=(end_ts-timedelta(microseconds=1)).tz_convert(BANGKOK).date()
    while d <= last:
        requested_days.append(d.isoformat()); d += timedelta(days=1)

    return {
        "status":"completed", "symbol":symbol, "engine_version":engine.ENGINE_VERSION, "provider":"LSE",
        "replay_mode":"DATE_RANGE", "start":start_ts.isoformat(), "end":end_ts.isoformat(),
        "warmup_days":14, "m5_bars":len(m5), "m15_bars":len(m15),
        "requested_days":requested_days, "evaluated_closed_m5_candles":sum(x["evaluated"] for x in day_rows.values()),
        "generated":generated, "inserted":inserted, "outcomes":outcomes,
        "rejected":dict(rejected.most_common(30)),
        "strategy_stats":aggregate_strategy_stats(all_candidates, results_by_strategy),
    }


def main():
    p=argparse.ArgumentParser(); p.add_argument("--start",required=True); p.add_argument("--end",required=True); p.add_argument("--symbol",choices=["BTC","GOLD","ALL"],default="ALL"); p.add_argument("--dry-run",action="store_true"); a=p.parse_args()
    start,end=_bounds(a.start,a.end); results=[]
    for s in (["BTC","GOLD"] if a.symbol=="ALL" else [a.symbol]):
        try: results.append(replay_symbol(s,start,end,a.dry_run))
        except Exception as exc: results.append({"symbol":s,"engine_version":engine.ENGINE_VERSION,"status":"failed","error":f"{type(exc).__name__}: {exc}"})
    status=replay_overall_status(results)
    print(json.dumps({"status":"dry-run" if a.dry_run and status=="completed" else status,"engine_version":engine.ENGINE_VERSION,"provider":"LSE","replay_mode":"DATE_RANGE","start":start.isoformat(),"end":end.isoformat(),"results":results},ensure_ascii=False,separators=(",",":")))


if __name__=="__main__":
    main()
