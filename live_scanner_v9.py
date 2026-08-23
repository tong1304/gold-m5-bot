"""Live M5 scanner V9 for BTC + GOLD using LSE Data."""
from __future__ import annotations
import os
import threading
from datetime import datetime, timezone, timedelta
import pandas as pd
import engine_v9_core as engine
from signal_history import history
from lse import LSE

SUPPORTED_SYMBOLS=("BTC","GOLD")
_SCAN_LOCK=threading.Lock()
_ALERTED_SIGNAL_KEYS=set()


def _normalize_lse_rows(raw, symbol, timeframe):
    """Normalize lse-data 0.14 candle responses to a list of OHLCV rows.

    lse-data returns an envelope such as {"rows": N, "data": [...], ...}.
    Older code assumed the response itself was the row list, which produced
    DataFrames with columns like `rows`, `plan`, and `data` and then failed on
    the missing `datetime` column.
    """
    if isinstance(raw, dict):
        rows=raw.get("data")
        if rows is None:
            rows=raw.get("rows_data")
        if rows is None and isinstance(raw.get("data"), dict):
            rows=raw["data"].get("data")
        if rows is None:
            raise RuntimeError(f"LSE_INVALID_RESPONSE: {symbol} {timeframe} missing data rows; keys={list(raw.keys())[:20]}")
    elif isinstance(raw, (list, tuple)):
        rows=raw
    else:
        raise RuntimeError(f"LSE_INVALID_RESPONSE: {symbol} {timeframe} unexpected type={type(raw).__name__}")

    if not isinstance(rows, list):
        rows=list(rows) if rows is not None else []
    if not rows:
        raise RuntimeError(f"LSE returned no candles for {symbol} {timeframe}")

    frame=pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError(f"LSE returned empty candle frame for {symbol} {timeframe}")

    # lse-data uses `timestamp`; accept `datetime` too for compatibility.
    if "datetime" not in frame.columns:
        for candidate in ("timestamp","time","date"):
            if candidate in frame.columns:
                frame=frame.rename(columns={candidate:"datetime"})
                break
    if "datetime" not in frame.columns:
        raise RuntimeError(f"LSE_INVALID_RESPONSE: {symbol} {timeframe} missing timestamp column; columns={list(frame.columns)}")

    required=("open","high","low","close")
    missing=[c for c in required if c not in frame.columns]
    if missing:
        raise RuntimeError(f"LSE_INVALID_RESPONSE: {symbol} {timeframe} missing OHLC columns={missing}; columns={list(frame.columns)}")
    return frame


def _lse_frame(symbol, timeframe, history_points=200):
    market={"BTC":"BTC/USD","GOLD":"XAU/USD"}[symbol]
    dataset="crypto" if symbol=="BTC" else "forex"
    now=datetime.now(timezone.utc)
    days=max(2, int(history_points*5/1440)+2)
    start=(now-timedelta(days=days)).date().isoformat()
    end=(now+timedelta(days=1)).date().isoformat()
    client=LSE(api_key=os.environ["LSE_API_KEY"])
    print(f"[{symbol}] LSE QUERY: market={market} dataset={dataset} timeframe={timeframe} start={start} end={end} limit={history_points} order=desc",flush=True)
    raw=client.candles(market,timeframe,start=start,end=end,limit=history_points,order="desc")
    frame=_normalize_lse_rows(raw,symbol,timeframe)
    print(f"[{symbol}] LSE RAW DATA: rows={len(frame)} dataset={dataset}",flush=True)
    frame["datetime"]=pd.to_datetime(frame["datetime"],utc=True,errors="coerce")
    for col in ("open","high","low","close"):
        frame[col]=pd.to_numeric(frame[col],errors="coerce")
    frame=frame.dropna(subset=["datetime","open","high","low","close"]).sort_values("datetime").reset_index(drop=True)
    if frame.empty:
        raise RuntimeError(f"LSE returned no valid OHLC candles for {symbol} {timeframe}")
    print(f"[{symbol}] LSE NORMALIZED: rows={len(frame)} oldest={frame.iloc[0]['datetime'].isoformat()} newest={frame.iloc[-1]['datetime'].isoformat()} dataset={dataset}",flush=True)
    frame=engine.remove_incomplete_last_candle(frame,timeframe)
    _validate_freshness(frame,symbol,timeframe)
    print(f"[{symbol}] Latest closed {timeframe} candle: {frame.iloc[-1]['datetime']}",flush=True)
    return frame


def _max_age(timeframe): return {"5m":20.0,"15m":45.0,"1h":150.0}.get(timeframe,60.0)

def _validate_freshness(frame,symbol,timeframe):
    if frame.empty: raise RuntimeError(f"NO_CLOSED_CANDLES: {symbol} {timeframe}")
    latest=pd.Timestamp(frame.iloc[-1]["datetime"]); now=pd.Timestamp(datetime.now(timezone.utc)); age_minutes=(now-latest).total_seconds()/60.0; max_age=_max_age(timeframe)
    print(f"[{symbol}] DATA CHECK {timeframe}: latest={latest.isoformat()} age={age_minutes:.1f}m max={max_age:.1f}m",flush=True)
    if age_minutes>max_age: raise RuntimeError(f"STALE_MARKET_DATA: {symbol} {timeframe} latest={latest.isoformat()} age={age_minutes:.1f}m max={max_age:.1f}m")

def _load_frames(symbol):
    history_points=max(100,int(os.getenv("LIVE_SIGNAL_HISTORY","200"))); frames={}
    for tf,minimum in (("1h",60),("15m",60),("5m",100)):
        df=_lse_frame(symbol,tf,history_points)
        if len(df)<minimum: raise RuntimeError(f"Insufficient closed LSE data for {symbol} {tf}: {len(df)}")
        frames[tf]=df.reset_index(drop=True)
    latest=frames["5m"].iloc[-1]["datetime"]
    for tf in ("1h","15m"):
        if frames[tf].iloc[-1]["datetime"]>latest: frames[tf]=frames[tf].iloc[:-1].reset_index(drop=True)
    return frames

def _levels_ready(levels,direction=None):
    if not isinstance(levels,dict) or not levels.get("valid",False): return False
    try:
        entry,sl,tp=map(float,(levels["entry"],levels["sl"],levels["tp"])); rr=float(levels.get("effective_rr",levels.get("risk_reward",0)))
        if direction=="BUY" and not sl<entry<tp: return False
        if direction=="SELL" and not sl>entry>tp: return False
        return entry>0 and sl>0 and tp>0 and rr>=2.0
    except (TypeError,ValueError,KeyError): return False

def _format_telegram(symbol,setup,signal_id):
    direction=setup["signal"]; levels=setup["trade_levels"]; sweep=setup.get("liquidity_event") or {}; mss=setup.get("m5_trigger") or {}; loc=setup.get("location") or {}; h1=setup.get("structure_bias",{}).get("bias","NEUTRAL"); m15=setup.get("m15_structure",{}).get("bias","NEUTRAL")
    side="🟢 BUY — ซื้อ" if direction=="BUY" else "🔴 SELL — ขาย"
    return ("🚨 <b>พบสัญญาณ Structure V9</b>\n\n" f"{side}\n\n📊 <b>สินทรัพย์:</b> {symbol}\n⏱ <b>Entry TF:</b> M5\n🕯 <b>แท่ง:</b> {_fmt_time(setup.get('candle_time'))}\n" f"🔐 <b>Signal ID:</b> {signal_id}\n\n" f"🧭 <b>Structure:</b> H1={h1} | M15={m15} | M5={direction}\n" f"📍 <b>Location:</b> {loc.get('zone','-')}\n💧 <b>Liquidity:</b> {sweep.get('type','-')}\n⚡ <b>MSS/BOS:</b> {mss.get('type','-')}\n🔄 <b>Pullback:</b> CONFIRMED\n\n" f"💰 <b>Entry:</b> {_fmt_price(levels['entry'])}\n🛑 <b>SL:</b> {_fmt_price(levels['sl'])}\n🎯 <b>TP:</b> {_fmt_price(levels['tp'])}\n📐 <b>RR:</b> {levels['risk_reward']}R\n\n🧠 <b>เหตุผลเข้า:</b> Structure → Location → Liquidity Sweep → MSS/BOS → Pullback\n⚠️ ระบบไม่เปิดออเดอร์อัตโนมัติ")

def _fmt_time(value):
    try:
        ts=pd.Timestamp(value)
        if ts.tzinfo is None: ts=ts.tz_localize("UTC")
        return ts.tz_convert("Asia/Bangkok").strftime("%d/%m/%Y %H:%M")
    except Exception: return str(value or "-")

def _fmt_price(value):
    try: return f"{float(value):,.8f}".rstrip("0").rstrip(".")
    except Exception: return str(value)

def scan_once(symbol="BTC"):
    symbol=(symbol or "BTC").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS: raise ValueError(f"ไม่รองรับสินทรัพย์: {symbol}; รองรับ: BTC, GOLD")
    with _SCAN_LOCK:
        cfg={"BTC":{"MINIMUM_ATR":0.0,"MIN_STOP_ATR":0.0,"MAX_STOP_ATR":4.0,"SPREAD":5.0,"SLIPPAGE":2.0},"GOLD":{"MINIMUM_ATR":0.0,"MIN_STOP_ATR":0.0,"MAX_STOP_ATR":4.0,"SPREAD":0.50,"SLIPPAGE":0.20}}[symbol]
        for key,value in cfg.items(): setattr(engine,key,value)
        engine.MIN_RISK_REWARD=max(float(os.getenv("MIN_RISK_REWARD","2.0")),2.0); engine.RISK_REWARD=max(float(os.getenv("RISK_REWARD","2.0")),2.0)
        frames=_load_frames(symbol); m5=frames["5m"]; index=len(m5)-1
        setup=engine.analyze_structure_setup(m5,frames["15m"],frames["1h"],index)
        candle_time=str(m5.iloc[index].get("datetime","")); setup.update({"candle_time":candle_time,"closed_candle":candle_time,"symbol":symbol,"previous_close":float(m5.iloc[index]["close"]),"engine_version":engine.ENGINE_VERSION})
        signal=setup.get("signal"); valid=signal in ("BUY","SELL") and _levels_ready(setup.get("trade_levels"),signal); setup["valid"]=valid
        setup_key=setup.get("setup_key") or f"{symbol}|{candle_time}|{signal}"; suffix=signal if valid else "NO_TRADE"; signal_id=f"{symbol}-{str(candle_time).replace(':','').replace('-','').replace(' ','-')}-{suffix}"; setup["signal_id"]=signal_id
        if not valid:
            payload={**setup,"signal":"NO_TRADE","result":"NO_TRADE","created_at":datetime.now(timezone.utc).isoformat(),"no_trade_reasons":setup.get("rejection_reasons") or []}; recorded=history.record_no_trade(payload)
            print(f"[{symbol}] V9 NO_TRADE recorded={recorded} reasons={setup.get('rejection_reasons')}",flush=True)
            return {"status":"no_trade","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"signal":"NO_TRADE","recorded":recorded,**setup}
        if setup_key in _ALERTED_SIGNAL_KEYS or history.get(signal_id): return {"status":"duplicate_suppressed","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"signal":signal,"signal_id":signal_id,"setup_key":setup_key}
        payload={"signal_id":signal_id,"symbol":symbol,"signal":signal,"closed_candle":candle_time,"created_at":datetime.now(timezone.utc).isoformat(),"engine_version":engine.ENGINE_VERSION,"replay":False,"pattern_signal":signal,"m5_direction":signal,"v9_setup":setup,"structure_bias":setup.get("structure_bias"),"location":setup.get("location"),"liquidity_event":setup.get("liquidity_event"),"m5_trigger":setup.get("m5_trigger"),"pullback":setup.get("pullback"),"target_liquidity":setup.get("target_liquidity"),"rejection_reasons":setup.get("rejection_reasons"),"trade_levels":setup["trade_levels"],"mtf":{"H1":{"bias":setup.get("structure_bias",{}).get("bias")},"M15":{"bias":setup.get("m15_structure",{}).get("bias")},"M5":signal}}
        recorded=history.record_signal(payload); telegram_result=engine.send_telegram(_format_telegram(symbol,setup,signal_id)); _ALERTED_SIGNAL_KEYS.add(setup_key)
        return {"status":"signal_sent" if telegram_result.get("success") else "signal_recorded_telegram_failed","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"signal":signal,"signal_id":signal_id,"recorded":recorded,"telegram":telegram_result,"telegram_alert_sent":bool(telegram_result.get("success")),"setup":setup}
