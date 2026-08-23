"""Replay Structure V6 against real LSE historical OHLCV.

Usage:
    python replay_signal_history.py --start 2026-08-01 --end 2026-08-23 --symbol BTC --dry-run
    python replay_signal_history.py --start 2026-08-01 --end 2026-08-23 --symbol ALL

Dry-run never writes signal history and never sends Telegram.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

import engine_v6 as engine
import engine_v42 as base
from signal_history import history

BANGKOK = ZoneInfo("Asia/Bangkok")
SYMBOLS = {"BTC": "BTC/USD", "GOLD": "XAU/USD"}


def _bounds(start_text, end_text):
    start = datetime.fromisoformat(start_text).replace(tzinfo=BANGKOK)
    end = datetime.fromisoformat(end_text).replace(tzinfo=BANGKOK) + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _normalize(result):
    if isinstance(result, pd.DataFrame): df = result.copy()
    elif isinstance(result, dict): df = pd.DataFrame(result.get("data") or result.get("rows") or result.get("candles") or [])
    else: df = pd.DataFrame(result or [])
    if df.empty: return df
    time_col = next((c for c in ("datetime","timestamp","time","ts") if c in df.columns), None)
    if not time_col: raise RuntimeError("LSE response has no timestamp field")
    df["datetime"] = pd.to_datetime(df[time_col], utc=True, errors="coerce")
    rename = {"o":"open","h":"high","l":"low","c":"close","v":"volume"}
    df = df.rename(columns={k:v for k,v in rename.items() if k in df.columns})
    for col in ("open","high","low","close","volume"):
        if col not in df.columns: df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return (df.dropna(subset=["datetime","open","high","low","close"])
              [["datetime","open","high","low","close","volume"]]
              .sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True))


def _fetch_lse(symbol, start, end, timeframe="5m", chunk_days=6):
    key = os.getenv("LSE_API_KEY", "").strip() or os.getenv("LSE_KEY", "").strip()
    if not key: raise RuntimeError("LSE_API_KEY/LSE_KEY is not configured")
    from lse import LSE
    client = LSE(api_key=key)
    parts, cursor = [], start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=chunk_days), end)
        start_date, end_date = cursor.date().isoformat(), chunk_end.date().isoformat()
        print(f"[{symbol}] LSE candles request: {start_date} -> {end_date} ({timeframe})", flush=True)
        raw = client.candles(symbol, timeframe, start=start_date, end=end_date)
        frame = _normalize(raw)
        if not frame.empty: parts.append(frame)
        cursor = chunk_end
    if not parts: raise RuntimeError(f"LSE returned no {timeframe} candles for {symbol}")
    return (pd.concat(parts, ignore_index=True).sort_values("datetime")
              .drop_duplicates("datetime").reset_index(drop=True))


def _configure(symbol):
    cfg = {"BTC": {"MINIMUM_ATR":20.0,"MIN_STOP_ATR":1.0,"MAX_STOP_ATR":3.0,"SPREAD":5.0,"SLIPPAGE":2.0},
           "GOLD": {"MINIMUM_ATR":1.0,"MIN_STOP_ATR":1.0,"MAX_STOP_ATR":3.0,"SPREAD":0.50,"SLIPPAGE":0.20}}[symbol]
    market = SYMBOLS[symbol]
    for target in (engine, base):
        target.SYMBOL = market
        for key, value in cfg.items(): setattr(target, key, value)
        target.MIN_RISK_REWARD = max(float(os.getenv("MIN_RISK_REWARD", "2.0")), 2.0)
        target.RISK_REWARD = max(float(os.getenv("RISK_REWARD", "2.0")), 2.0)
    return market


def _resample(m5, minutes):
    return (m5[["datetime","open","high","low","close","volume"]].set_index("datetime")
            .resample(f"{minutes}min", label="left", closed="left")
            .agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"})
            .dropna(subset=["open","high","low","close"]).reset_index())


def _context(frame, ts):
    return frame[frame["datetime"] <= pd.Timestamp(ts)].reset_index(drop=True)


def _resolve(row, future):
    entry, sl, tp = float(row["entry"]), float(row["sl"]), float(row["tp"])
    direction = row["direction"]
    risk = abs(entry-sl)
    rr = abs(tp-entry)/risk if risk else 0.0
    for _, candle in future.iterrows():
        high, low = float(candle["high"]), float(candle["low"])
        if direction == "BUY": hit_sl, hit_tp = low <= sl, high >= tp
        else: hit_sl, hit_tp = high >= sl, low <= tp
        when = str(candle["datetime"])
        if hit_sl and hit_tp: return "AMBIGUOUS", 0.0, when
        if hit_tp: return "WIN", rr, when
        if hit_sl: return "LOSS", -1.0, when
    return "OPEN", None, None


def replay_symbol(symbol, start, end, dry_run=False):
    market = _configure(symbol)
    warm_start = start - timedelta(days=7)
    print(f"[{symbol}] LSE history: {warm_start.isoformat()} -> {end.isoformat()}", flush=True)
    m5 = _fetch_lse(market, warm_start, end, "5m", 6)
    if len(m5) < 500: raise RuntimeError(f"Not enough LSE M5 history for {symbol}: {len(m5)}")
    m15, h1 = _resample(m5, 15), _resample(m5, 60)
    generated = inserted = 0
    outcomes = {"WIN":0,"LOSS":0,"AMBIGUOUS":0,"OPEN":0}
    rejected = {}
    used_setup_keys = set()

    for i in range(100, len(m5)-1):
        ts = pd.Timestamp(m5.iloc[i]["datetime"])
        if ts < pd.Timestamp(start) or ts >= pd.Timestamp(end): continue
        # Critical: context frames end at the decision candle. Future M15/H1 bars
        # never participate in the V6 decision.
        m15_ctx, h1_ctx = _context(m15, ts), _context(h1, ts)
        if len(m15_ctx) < 30 or len(h1_ctx) < 30: continue
        setup = engine.analyze_structure_setup(m5, m15_ctx, h1_ctx, i)
        if setup.get("signal") not in ("BUY","SELL") or not setup.get("valid"):
            for reason in setup.get("rejection_reasons", []): rejected[reason] = rejected.get(reason, 0) + 1
            continue
        setup_key = setup.get("setup_key")
        if setup_key and setup_key in used_setup_keys:
            rejected["DUPLICATE_SETUP"] = rejected.get("DUPLICATE_SETUP", 0) + 1
            continue
        if setup_key: used_setup_keys.add(setup_key)
        levels = setup["trade_levels"]
        signal = setup["signal"]
        signal_id = f"REPLAY-V6-{symbol}-{ts.strftime('%Y%m%dT%H%MZ')}-{signal}"
        payload = {
            "signal_id":signal_id,"symbol":symbol,"signal":signal,"closed_candle":ts.isoformat(),"created_at":ts.isoformat(),
            "replay":True,"replay_source":"LSE_HISTORICAL_OHLCV","engine_version":engine.ENGINE_VERSION,
            "pattern_signal":signal,"m5_direction":signal,"v6_setup":setup,
            "structure_bias":setup.get("structure_bias"),"location":setup.get("location"),
            "liquidity_event":setup.get("liquidity_event"),"m5_trigger":setup.get("m5_trigger"),
            "pullback":setup.get("pullback"),"target_liquidity":setup.get("target_liquidity"),
            "rejection_reasons":setup.get("rejection_reasons",[]),"trade_levels":levels,
            "mtf":{"H1":{"bias":setup.get("structure_bias",{}).get("bias")},"M15":{"bias":setup.get("m15_structure",{}).get("bias")},"M5":signal},
        }
        generated += 1
        future = m5.iloc[i+1:i+1+int(engine.FORWARD_BARS)+1]
        result, r_multiple, resolved = _resolve({"direction":signal,"entry":levels["entry"],"sl":levels["sl"],"tp":levels["tp"]}, future)
        outcomes[result] += 1
        if not dry_run:
            if history.record_signal(payload): inserted += 1
            if result != "OPEN": history.set_result(signal_id,result,r_multiple,resolved)

    return {"symbol":symbol,"generated":generated,"inserted":inserted,"outcomes":outcomes,"rejected":dict(sorted(rejected.items(), key=lambda x:x[1], reverse=True)[:15])}


def main():
    parser = argparse.ArgumentParser(description="Replay Structure V6 on real LSE historical M5")
    parser.add_argument("--start", required=True); parser.add_argument("--end", required=True)
    parser.add_argument("--symbol", choices=["BTC","GOLD","ALL"], default="ALL")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    start, end = _bounds(args.start, args.end)
    symbols = ["BTC","GOLD"] if args.symbol == "ALL" else [args.symbol]
    results = [replay_symbol(symbol,start,end,args.dry_run) for symbol in symbols]
    print(json.dumps({"status":"dry-run" if args.dry_run else "completed","engine_version":engine.ENGINE_VERSION,"provider":"LSE","start":args.start,"end":args.end,"results":results},ensure_ascii=False,indent=2))


if __name__ == "__main__": main()
