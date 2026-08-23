import os
import threading
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

import engine_v8 as engine
base = engine
from signal_history import history

_SCAN_LOCK = threading.RLock()
_ALERTED_SIGNAL_KEYS = set()
BANGKOK = ZoneInfo("Asia/Bangkok")
SUPPORTED_SYMBOLS = {"BTC", "GOLD"}
SYMBOL_MAP = {"BTC": "BTC/USD", "GOLD": "XAU/USD"}
DATASET_MAP = {"BTC": "crypto", "GOLD": "commodity"}
TF_MINUTES = {"1h": 60, "15m": 15, "5m": 5}


def _market_symbol(symbol):
    return SYMBOL_MAP[(symbol or "").strip().upper()]


def _dataset(symbol):
    return DATASET_MAP[(symbol or "").strip().upper()]


def _fmt_price(value):
    try: return f"{float(value):,.8f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError): return str(value)


def _fmt_time(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(BANGKOK).strftime("%d/%m/%Y %H:%M:%S") + " (กรุงเทพฯ)"
    except (TypeError, ValueError): return str(value)


def _data_max_age_minutes(timeframe):
    defaults = {"5m": 20.0, "15m": 45.0, "1h": 150.0}
    return float(os.getenv(f"LIVE_MAX_AGE_{timeframe.upper()}_MINUTES", defaults[timeframe]))


def _validate_freshness(frame, symbol, timeframe):
    if frame.empty:
        raise RuntimeError(f"DATA_INVALID: LSE ไม่มีข้อมูล {timeframe} สำหรับ {symbol}")
    latest = frame.iloc[-1]["datetime"]
    if pd.isna(latest):
        raise RuntimeError(f"DATA_INVALID: {symbol} {timeframe} latest timestamp เป็นค่าว่าง")
    latest = pd.Timestamp(latest)
    if latest.tzinfo is None: latest = latest.tz_localize("UTC")
    latest = latest.tz_convert("UTC")
    now = pd.Timestamp.now(tz="UTC")
    age_minutes = (now - latest).total_seconds() / 60.0
    max_age = _data_max_age_minutes(timeframe)
    print(f"[{symbol}] DATA CHECK {timeframe}: latest={latest.isoformat()} age={age_minutes:.1f}m max={max_age:.1f}m", flush=True)
    if age_minutes < -2.0:
        raise RuntimeError(f"DATA_INVALID: {symbol} {timeframe} timestamp is in the future latest={latest.isoformat()}")
    if age_minutes > max_age:
        raise RuntimeError(f"STALE_MARKET_DATA: {symbol} {timeframe} latest={latest.isoformat()} age={age_minutes:.1f}m max={max_age:.1f}m")


def _lse_frame(symbol, timeframe, limit):
    from lse import LSE
    symbol = (symbol or "").strip().upper()
    market = _market_symbol(symbol)
    dataset = _dataset(symbol)
    key = os.getenv("LSE_API_KEY", "").strip() or os.getenv("LSE_KEY", "").strip()
    if not key: raise RuntimeError("LSE_API_KEY/LSE_KEY is not configured")

    # Do not ask the historical vault for an unbounded slice. Pin the asset
    # class and query a recent time window so BTC cannot fall back to 2017 data.
    tf_minutes = TF_MINUTES[timeframe]
    rows_needed = max(int(limit), 100)
    window_minutes = max(rows_needed * tf_minutes * 2, 24 * 60)
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=window_minutes)
    print(f"[{symbol}] LSE QUERY: market={market} dataset={dataset} timeframe={timeframe} start={start.isoformat()} end={end.isoformat()} limit={rows_needed} order=desc", flush=True)

    client = LSE(api_key=key)
    raw = client.candles(
        market,
        timeframe,
        start=start.isoformat(),
        end=end.isoformat(),
        limit=rows_needed,
        order="desc",
        dataset=dataset,
    )
    if isinstance(raw, dict): rows = raw.get("data") or raw.get("candles") or raw.get("rows") or []
    else: rows = raw or []
    frame = pd.DataFrame(rows)
    if frame.empty: raise RuntimeError(f"LSE_RECENT_DATA_UNAVAILABLE: ไม่มีข้อมูลล่าสุด {timeframe} สำหรับ {market} dataset={dataset}")
    frame = frame.rename(columns={k:v for k,v in {"timestamp":"datetime","time":"datetime","ts":"datetime","o":"open","h":"high","l":"low","c":"close","v":"volume"}.items() if k in frame.columns})
    if "datetime" not in frame.columns or not {"high","low","close"}.issubset(frame.columns):
        raise RuntimeError(f"DATA_INVALID: LSE {market} {timeframe} response missing OHLC columns")
    frame["datetime"] = pd.to_datetime(frame["datetime"], utc=True, errors="coerce")
    for col in ("open","high","low","close","volume"):
        if col in frame.columns: frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["datetime","high","low","close"]).sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)
    if frame.empty: raise RuntimeError(f"DATA_INVALID: LSE {market} {timeframe} ไม่มีแท่ง OHLC ที่ใช้ได้")
    raw_latest = frame.iloc[-1]["datetime"]
    print(f"[{symbol}] LSE RAW DATA: rows={len(frame)} oldest={frame.iloc[0]['datetime'].isoformat()} newest={raw_latest.isoformat()} dataset={dataset}", flush=True)
    frame = engine.remove_incomplete_last_candle(frame, timeframe_minutes=tf_minutes)
    _validate_freshness(frame, symbol, timeframe)
    return frame


def _load_frames(symbol):
    history_points = max(100, int(os.getenv("LIVE_SIGNAL_HISTORY", str(engine.SIGNAL_HISTORY_POINTS))))
    frames = {}
    for tf, minimum in (("1h",60),("15m",60),("5m",80)):
        df = _lse_frame(symbol, tf, history_points)
        if len(df) < minimum: raise RuntimeError(f"ข้อมูล LSE {tf} ของ {symbol} ที่ปิดแล้วไม่เพียงพอ: {len(df)} แท่ง")
        frames[tf] = df.reset_index(drop=True)
    latest = frames["5m"].iloc[-1]["datetime"]
    for tf in ("1h","15m"):
        if frames[tf].iloc[-1]["datetime"] > latest: frames[tf] = frames[tf].iloc[:-1].reset_index(drop=True)
    return frames


def _levels_ready(levels, direction=None):
    if not isinstance(levels, dict) or not levels.get("valid", False): return False
    try:
        entry, sl, tp = map(float, (levels["entry"], levels["sl"], levels["tp"]))
        rr = float(levels.get("effective_rr", levels.get("risk_reward", 0)))
        if direction == "BUY" and not sl < entry < tp: return False
        if direction == "SELL" and not sl > entry > tp: return False
        return entry > 0 and sl > 0 and tp > 0 and rr >= 2.0
    except (TypeError, ValueError, KeyError): return False


def _format_telegram(symbol, setup, signal_id):
    direction=setup["signal"]; levels=setup["trade_levels"]; sweep=setup.get("liquidity_event") or {}; mss=setup.get("m5_trigger") or {}; loc=setup.get("location") or {}
    h1=setup.get("structure_bias",{}).get("bias","NEUTRAL"); m15=setup.get("m15_structure",{}).get("bias","NEUTRAL")
    side="🟢 BUY — ซื้อ" if direction=="BUY" else "🔴 SELL — ขาย"
    return ("🚨 <b>พบสัญญาณ Structure V8</b>\n\n" f"{side}\n\n📊 <b>สินทรัพย์:</b> {symbol}\n⏱ <b>Entry TF:</b> M5\n🕯 <b>แท่ง:</b> {_fmt_time(setup.get('candle_time'))}\n" f"🔐 <b>Signal ID:</b> {signal_id}\n\n" f"🧭 <b>Structure:</b> H1={h1} | M15={m15} | M5={direction}\n" f"📍 <b>Location:</b> {loc.get('zone','-')}\n" f"💧 <b>Liquidity:</b> {sweep.get('type','-')}\n" f"⚡ <b>MSS/BOS:</b> {mss.get('type','-')}\n🔄 <b>Pullback:</b> CONFIRMED\n\n" f"💰 <b>Entry:</b> {_fmt_price(levels['entry'])}\n🛑 <b>SL:</b> {_fmt_price(levels['sl'])}\n🎯 <b>TP:</b> {_fmt_price(levels['tp'])}\n📐 <b>RR:</b> {levels['risk_reward']}R\n\n" "🧠 <b>เหตุผลเข้า:</b> Structure → Location → Liquidity Sweep → MSS/BOS → Pullback\n⚠️ ระบบไม่เปิดออเดอร์อัตโนมัติ")


def scan_once(symbol="BTC"):
    symbol=(symbol or "BTC").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS: raise ValueError(f"ไม่รองรับสินทรัพย์: {symbol}; รองรับ: BTC, GOLD")
    with _SCAN_LOCK:
        cfg={"BTC":{"MINIMUM_ATR":0.0,"MIN_STOP_ATR":0.0,"MAX_STOP_ATR":4.0,"SPREAD":5.0,"SLIPPAGE":2.0},"GOLD":{"MINIMUM_ATR":0.0,"MIN_STOP_ATR":0.0,"MAX_STOP_ATR":4.0,"SPREAD":0.50,"SLIPPAGE":0.20}}[symbol]
        for key,value in cfg.items(): setattr(engine,key,value)
        engine.MIN_RISK_REWARD=max(float(os.getenv("MIN_RISK_REWARD","2.0")),2.0); engine.RISK_REWARD=max(float(os.getenv("RISK_REWARD","2.0")),2.0)
        frames=_load_frames(symbol); m5=frames["5m"]; index=len(m5)-1
        setup=engine.analyze_structure_setup(m5,frames["15m"],frames["1h"],index)
        candle_time=str(m5.iloc[index].get("datetime",""))
        setup.update({"candle_time":candle_time,"closed_candle":candle_time,"symbol":symbol,"previous_close":float(m5.iloc[index]["close"]),"engine_version":engine.ENGINE_VERSION})
        signal=setup.get("signal"); valid=signal in ("BUY","SELL") and _levels_ready(setup.get("trade_levels"),signal); setup["valid"]=valid
        setup_key=setup.get("setup_key") or f"{symbol}|{candle_time}|{signal}"; suffix=signal if valid else "NO_TRADE"; signal_id=f"{symbol}-{str(candle_time).replace(':','').replace('-','').replace(' ','-')}-{suffix}"; setup["signal_id"]=signal_id
        if not valid:
            payload={**setup,"signal":"NO_TRADE","result":"NO_TRADE","created_at":datetime.now(timezone.utc).isoformat(),"no_trade_reasons":setup.get("rejection_reasons") or []}
            recorded=history.record_no_trade(payload)
            print(f"[{symbol}] V8 NO_TRADE recorded={recorded} reasons={setup.get('rejection_reasons')}",flush=True)
            return {"status":"no_trade","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"signal":"NO_TRADE","recorded":recorded,**setup}
        if setup_key in _ALERTED_SIGNAL_KEYS or history.get(signal_id):
            return {"status":"duplicate_suppressed","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"signal":signal,"signal_id":signal_id,"setup_key":setup_key}
        payload={"signal_id":signal_id,"symbol":symbol,"signal":signal,"closed_candle":candle_time,"created_at":datetime.now(timezone.utc).isoformat(),"engine_version":engine.ENGINE_VERSION,"replay":False,"pattern_signal":signal,"m5_direction":signal,"v8_setup":setup,"structure_bias":setup.get("structure_bias"),"location":setup.get("location"),"liquidity_event":setup.get("liquidity_event"),"m5_trigger":setup.get("m5_trigger"),"pullback":setup.get("pullback"),"target_liquidity":setup.get("target_liquidity"),"rejection_reasons":setup.get("rejection_reasons"),"trade_levels":setup["trade_levels"],"mtf":{"H1":{"bias":setup.get("structure_bias",{}).get("bias")},"M15":{"bias":setup.get("m15_structure",{}).get("bias")},"M5":signal}}
        recorded=history.record_signal(payload); telegram_result=engine.send_telegram(_format_telegram(symbol,setup,signal_id)); _ALERTED_SIGNAL_KEYS.add(setup_key)
        return {"status":"signal_sent" if telegram_result.get("success") else "signal_recorded_telegram_failed","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"signal":signal,"signal_id":signal_id,"recorded":recorded,"telegram":telegram_result,"telegram_alert_sent":bool(telegram_result.get("success")),"setup":setup}
