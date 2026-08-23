"""V10.3 historical replay using real LSE OHLCV.

The user selects calendar dates (Bangkok time). Replay internally evaluates every
closed M5 candle in that date range, with a 14-day warm-up. LSE requests use the
provider's required YYYY-MM-DD date format; timestamps are used only locally for
filtering and look-ahead-safe simulation.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta, date

import pandas as pd
from zoneinfo import ZoneInfo
from lse import LSE
import engine_v9_2 as engine
from signal_history import history

BANGKOK = ZoneInfo("Asia/Bangkok")
SYMBOLS = {"BTC": "BTC/USD", "GOLD": "XAU/USD"}


def _bounds(a, b):
    """Interpret date-only input as an inclusive Bangkok calendar-date range."""
    def parse(value):
        text = str(value).strip()
        # Date-only is the canonical Replay UI format.
        if len(text) == 10:
            d = date.fromisoformat(text)
            return datetime(d.year, d.month, d.day, tzinfo=BANGKOK)
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=BANGKOK)
        return dt.astimezone(BANGKOK)

    s_local = parse(a)
    e_local = parse(b)
    # End date is inclusive for the UI/API. A date-only end means the whole day.
    if len(str(b).strip()) == 10:
        e_local += timedelta(days=1)
    elif e_local <= s_local:
        raise ValueError("end must be after start")
    return s_local.astimezone(timezone.utc), e_local.astimezone(timezone.utc)


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
    """Fetch historical data using only LSE's accepted YYYY-MM-DD parameters.

    LSE rejects ISO timestamps in start/end. We therefore request one calendar
    day at a time. A full day contains 288 M5 bars / 96 M15 bars, so the replay
    request uses a configurable limit (default 1000) rather than the old 200-bar
    cap. If the provider returns fewer rows, the result is still merged safely.
    """
    key = os.getenv("LSE_API_KEY", "").strip() or os.getenv("LSE_KEY", "").strip()
    if not key:
        raise RuntimeError("LSE_API_KEY/LSE_KEY is not configured")
    client = LSE(api_key=key)
    request_limit = max(200, min(int(os.getenv("LSE_REPLAY_LIMIT", "1000")), 5000))

    # Convert UTC bounds to Bangkok calendar dates because the provider accepts
    # dates, while Replay's public contract is Bangkok calendar days.
    local_start = pd.Timestamp(start).tz_convert(BANGKOK).date()
    local_end_exclusive = pd.Timestamp(end).tz_convert(BANGKOK).date()
    days = []
    d = local_start
    while d <= local_end_exclusive:
        days.append(d)
        d += timedelta(days=1)

    parts = []
    for d in days:
        # Never send datetime strings to LSE. This is the critical fix.
        day_text = d.isoformat()
        raw = client.candles(
            SYMBOLS[symbol], timeframe,
            start=day_text,
            end=day_text,
            limit=request_limit,
            order="asc",
        )
        frame = _normalize(raw)
        if not frame.empty:
            parts.append(frame)

    if not parts:
        raise RuntimeError(f"LSE returned no {timeframe} candles for {symbol}")
    merged = (pd.concat(parts, ignore_index=True)
              .sort_values("datetime")
              .drop_duplicates("datetime")
              .reset_index(drop=True))
    # Keep only the actual warm-up + requested window. The provider may interpret
    # an end date inclusively, so local filtering is mandatory.
    return merged[(merged.datetime >= pd.Timestamp(start)) &
                  (merged.datetime < pd.Timestamp(end))].reset_index(drop=True)


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

    # User selects the DATE. The engine evaluates every closed M5 candle in it.
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

    evaluated = int(((m5.datetime >= start_ts) & (m5.datetime < end_ts)).sum())
    requested_days=[]
    d=start_ts.tz_convert(BANGKOK).date()
    last=(end_ts-timedelta(microseconds=1)).tz_convert(BANGKOK).date()
    while d <= last:
        requested_days.append(d.isoformat()); d += timedelta(days=1)

    return {
        "status":"completed", "symbol":symbol, "engine_version":engine.ENGINE_VERSION, "provider":"LSE",
        "replay_mode":"DATE_RANGE", "start":start_ts.isoformat(), "end":end_ts.isoformat(),
        "warmup_days":14, "m5_bars":len(m5), "m15_bars":len(m15),
        "requested_days":requested_days, "evaluated_closed_m5_candles":evaluated,
        "generated":generated, "inserted":inserted, "outcomes":outcomes,
        "rejected":dict(rejected.most_common(30)),
        "strategy_stats":aggregate_strategy_stats(all_candidates, results_by_strategy),
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--start",required=True)
    p.add_argument("--end",required=True)
    p.add_argument("--symbol",choices=["BTC","GOLD","ALL"],default="ALL")
    p.add_argument("--dry-run",action="store_true")
    a=p.parse_args()
    start,end=_bounds(a.start,a.end)
    results=[]
    for s in (["BTC","GOLD"] if a.symbol=="ALL" else [a.symbol]):
        try:
            results.append(replay_symbol(s,start,end,a.dry_run))
        except Exception as exc:
            results.append({"symbol":s,"engine_version":engine.ENGINE_VERSION,"status":"failed","error":f"{type(exc).__name__}: {exc}"})
    status=replay_overall_status(results)
    print(json.dumps({"status":"dry-run" if a.dry_run and status=="completed" else status,"engine_version":engine.ENGINE_VERSION,"provider":"LSE","replay_mode":"DATE_RANGE","start":start.isoformat(),"end":end.isoformat(),"results":results},ensure_ascii=False,separators=(",",":")))


if __name__=="__main__":
    main()
