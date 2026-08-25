"""V12.11 live scanner: MTF H1/M15 filters with M5 setup/trigger and native-first cross-asset fallback."""
from __future__ import annotations
import os,threading,json
from datetime import datetime,timezone,timedelta
import pandas as pd
from lse import LSE
from signal_history import history
from v11 import engine
from v11.setup_state import state_from_history
from v11.telegram import send_telegram
from v11.data_quality import require_closed,validate_frame
SUPPORTED_SYMBOLS=("BTC","GOLD");_SCAN_LOCK=threading.Lock()

def _normalize(raw,symbol,timeframe="5m"):
    rows=raw.get("data") if isinstance(raw,dict) else raw
    if isinstance(rows,dict):rows=rows.get("data") or rows.get("rows")
    if not isinstance(rows,(list,tuple)):raise RuntimeError(f"LSE_INVALID_RESPONSE:{symbol}:{timeframe}")
    candle_rows=[];metadata_rows=0
    for row in rows:
        if not isinstance(row,dict):continue
        keys=set(row);has_ohlc={"open","high","low","close"}.issubset(keys);has_time=bool(keys.intersection({"datetime","timestamp","time","date"}))
        if has_ohlc and has_time:candle_rows.append(row)
        else:metadata_rows+=1
    if not candle_rows:raise RuntimeError(f"LSE_INVALID_RESPONSE:{symbol}:{timeframe}:no_candle_rows:metadata_rows={metadata_rows}")
    frame=pd.DataFrame(candle_rows)
    for candidate in ("timestamp","time","date"):
        if "datetime" not in frame.columns and candidate in frame.columns:frame=frame.rename(columns={candidate:"datetime"})
    missing=[c for c in ("datetime","open","high","low","close") if c not in frame.columns]
    if missing:raise RuntimeError(f"LSE_INVALID_RESPONSE:{symbol}:{timeframe}:missing={missing}")
    frame["datetime"]=pd.to_datetime(frame["datetime"],utc=True,errors="coerce")
    for c in ("open","high","low","close"):frame[c]=pd.to_numeric(frame[c],errors="coerce")
    frame=frame.dropna(subset=["datetime","open","high","low","close"]).sort_values("datetime").drop_duplicates("datetime",keep="last").reset_index(drop=True)
    minutes={"5m":5,"15m":15,"1h":60}[timeframe];frame=require_closed(frame,timeframe_minutes=minutes);errors=validate_frame(frame,minimum=60,timeframe_minutes=minutes,market=symbol)
    if errors:raise RuntimeError(f"LSE_DATA_QUALITY:{symbol}:{timeframe}:{errors}")
    return frame

def _lse_frame(symbol,timeframe="5m",points=200):
    if timeframe not in ("5m","15m","1h"):raise ValueError(f"Unsupported V12 timeframe={timeframe}")
    market={"BTC":"BTC/USD","GOLD":"XAU/USD"}[symbol];minutes={"5m":5,"15m":15,"1h":60}[timeframe];now=datetime.now(timezone.utc);days=max(3,int(points*minutes/1440)+3);client=LSE(api_key=os.environ["LSE_API_KEY"]);raw=client.candles(market,timeframe,start=(now-timedelta(days=days)).date().isoformat(),end=(now+timedelta(days=1)).date().isoformat(),limit=points,order="desc");frame=_normalize(raw,symbol,timeframe)
    if frame.empty:raise RuntimeError(f"NO_CLOSED_CANDLES:{symbol}")
    age=(pd.Timestamp.now(tz="UTC")-frame.iloc[-1].datetime).total_seconds()/60;max_age={"5m":20,"15m":45,"1h":180}[timeframe]
    if age>max_age:raise RuntimeError(f"STALE_MARKET_DATA:{symbol}:{timeframe}:age={age:.1f}m")
    return frame

def _load_frames(symbol):
    points=max(100,int(os.getenv("LIVE_SIGNAL_HISTORY","200")));return {"1h":_lse_frame(symbol,"1h",points),"15m":_lse_frame(symbol,"15m",points),"5m":_lse_frame(symbol,"5m",points)}

def _levels_ready(levels,direction,strategy):
    try:
        from v11.risk import min_rr_for_strategy
        e,s,t=map(float,(levels["entry"],levels["sl"],levels["tp"]));rr=float(levels["risk_reward"]);minimum=float(min_rr_for_strategy(strategy));return bool(levels.get("valid")) and rr>=minimum and ((direction=="BUY" and s<e<t) or (direction=="SELL" and s>e>t)) and min(e,s,t)>0
    except (KeyError,TypeError,ValueError):return False

def _fmt(v):
    try:return f"{float(v):,.2f}"
    except (TypeError,ValueError):return "N/A"
def _live_price(symbol):
    try:
        import live_price;tick=live_price.get(symbol);return _fmt(tick.get("price")) if isinstance(tick,dict) and tick else "N/A"
    except Exception:return "N/A"

def _strategy_origin(setup,symbol):
    mode=str(setup.get("strategy_mode") or "NATIVE").upper();source=str(setup.get("source_asset") or symbol).upper();strategy=setup.get("strategy") or setup.get("engine") or "NONE";regime=setup.get("m5_regime") or setup.get("regime") or "UNKNOWN"
    if isinstance(regime,dict):regime=regime.get("regime") or regime.get("m5_regime") or "UNKNOWN"
    if mode=="CROSS_ASSET":return f"CROSS_ASSET source={source} target={symbol} strategy={strategy} regime={regime}"
    return f"NATIVE asset={symbol} strategy={strategy} regime={regime}"

def _telegram_text(symbol,setup):
    d=setup["signal"];l=setup["trade_levels"];side="🟢 BUY — ซื้อ" if d=="BUY" else "🔴 SELL — ขาย";regime=setup.get("regime") or {};regime_name=regime.get("regime") if isinstance(regime,dict) else regime;score=setup.get("setup_score") or {};score_value=score.get("score") if isinstance(score,dict) else "N/A";asset_icon="🪙" if symbol=="BTC" else "🟠";mode=str(setup.get("strategy_mode") or "NATIVE").upper();source=str(setup.get("source_asset") or symbol).upper();origin=(f"🔄 <b>Cross-Asset:</b> {source} → {symbol}" if mode=="CROSS_ASSET" else "🟢 <b>Strategy Mode:</b> NATIVE");compat=(f"🔗 <b>Source Strategy:</b> {setup.get('strategy','NONE')}" if mode=="CROSS_ASSET" else "")
    return f"🚨 <b>พบสัญญาณเข้าออเดอร์ V12.11 MTF</b>\n\n{side}\n\n📊 <b>สินทรัพย์:</b> {asset_icon} {symbol}\n💵 <b>ราคาปัจจุบัน:</b> {_live_price(symbol)}\n⏱ <b>Filter:</b> H1 → M15 → M5\n🧭 <b>H1 Bias:</b> {setup.get('h1_bias','N/A')}\n🧠 <b>M5 Regime:</b> {regime_name}\n{origin}\n{compat}\n🎯 <b>Engine:</b> {setup.get('engine','NONE')} — {setup.get('strategy')}\n🔁 <b>Entry Type:</b> {setup.get('entry_type','INITIAL')}\n🆔 <b>Setup ID:</b> {setup.get('setup_id')}\n\n💰 <b>จุดเข้า:</b> {_fmt(l['entry'])}\n🛑 <b>SL:</b> {_fmt(l['sl'])}\n🎯 <b>TP:</b> {_fmt(l['tp'])}\n📐 <b>Risk/Reward:</b> {l['risk_reward']}R\n📊 <b>Setup Score:</b> {score_value}/100\n\n⚠️ ระบบแจ้งเตือนเท่านั้น ไม่มีการเปิดออเดอร์อัตโนมัติ"

def _decision_summary(setup):
    trace=setup.get("decision_trace") or []
    if not isinstance(trace,(list,tuple)):return f"trace=INVALID_TYPE:{type(trace).__name__}"
    if not trace:return "trace=NONE"
    parts=[]
    target=str(setup.get("symbol") or "UNKNOWN").upper();default_source=str(setup.get("source_asset") or target).upper();regime=setup.get("m5_regime") or setup.get("regime") or "UNKNOWN";regime=regime.get("regime") if isinstance(regime,dict) else regime
    for r in trace:
        if not isinstance(r,dict):
            text=str(r)
            if "CROSS_ASSET_FALLBACK" in text:parts.append(f"CROSS_ASSET:{default_source}->{target}:regime={regime}:ATTEMPTED")
            else:parts.append(f"trace_item={text[:200]}")
            continue
        if r.get("status")=="CROSS_ASSET_FALLBACK":
            src=str(r.get("source_asset") or default_source).upper();compatible=','.join(r.get("compatible_engines") or []) or "NONE";parts.append(f"CROSS_ASSET:{src}->{target}:regime={r.get('regime',regime)}:COMPATIBLE={compatible}");continue
        if r.get("strategy_mode")=="CROSS_ASSET" or r.get("source_asset"):
            src=str(r.get("source_asset") or default_source).upper();strat=r.get("strategy") or r.get("engine") or "UNKNOWN";status="PASS" if r.get("status")=="PASS" else "FAIL";direction=r.get("direction") or "-";parts.append(f"CROSS_ASSET:{src}->{target}:{strat}:{direction}:{status}");continue
        if r.get("reason")=="CROSS_ASSET_FALLBACK":parts.append(f"CROSS_ASSET:{default_source}->{target}:regime={regime}:ATTEMPTED");continue
        status="PASS" if r.get("status")=="PASS" else "FAIL";reasons=r.get("rejection_reasons") or [];reason=",".join(str(x) for x in reasons) if isinstance(reasons,(list,tuple)) else str(reasons);score_detail=r.get("score_detail") or {};score=score_detail.get("score") if isinstance(score_detail,dict) else None;suffix=f" score={score}" if score is not None else f" reason={reason or '-'}";parts.append(f"{r.get('engine','UNKNOWN')}:{r.get('direction','UNKNOWN')}:{status}{suffix}")
    return " | ".join(parts)

def scan_once(symbol="BTC"):
    symbol=(symbol or "BTC").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS:raise ValueError(f"Unsupported symbol: {symbol}")
    with _SCAN_LOCK:
        frames=_load_frames(symbol);m5,m15,h1=frames["5m"],frames["15m"],frames["1h"];ts=str(m5.iloc[-1].datetime);resolved=history.resolve_open_for_symbol(symbol,m5.to_dict("records"));history_rows=history.list_signals(days=3650,symbol=symbol,limit=1000);state=state_from_history(history_rows);setup=engine.analyze(m5,m15=m15,h1=h1,symbol=symbol,setup_state=state);setup.update({"candle_time":ts,"closed_candle":ts,"symbol":symbol,"engine_version":engine.ENGINE_VERSION,"live_orders_allowed":False});regime=setup.get("regime") or {};regime_name=regime.get("regime") if isinstance(regime,dict) else regime;mode=str(setup.get("strategy_mode") or "NATIVE").upper();source=str(setup.get("source_asset") or symbol).upper();print(f"[V12 TRACE] {symbol} mode=MTF:H1>M15>M5 h1={setup.get('h1_bias')} m15={setup.get('m15_regime')} regime={regime_name} allowed={','.join(setup.get('allowed_engines') or [])} strategy_mode={mode} source_asset={source} final={setup.get('signal')} reason={','.join(setup.get('rejection_reasons') or [])}");print(f"[V12 TRACE] {symbol} {_decision_summary(setup)}",flush=True);active=history.active_for_symbol(symbol);signal=setup.get("signal");levels=setup.get("trade_levels") or {};valid=signal in ("BUY","SELL") and _levels_ready(levels,signal,setup.get("strategy"));setup["valid"]=valid;signal_id=f"V12-{symbol}-{ts.replace(':','').replace('-','').replace(' ','-')}-{signal if valid else 'NO_TRADE'}-{setup.get('trigger_id','NONE')}";setup["signal_id"]=signal_id
        if not valid:
            recorded=history.record_no_trade({**setup,"signal":"NO_TRADE","result":"NO_TRADE","created_at":datetime.now(timezone.utc).isoformat()});return {"status":"no_trade","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"signal":"NO_TRADE","recorded":recorded,"resolved_this_scan":resolved,**setup}
        same_setup_active=any((json_load(r.get("payload_json"),"setup_id") or r.get("setup_key"))==setup.get("setup_id") for r in active)
        if active and not same_setup_active:
            active_signals=[{"signal_id":r["signal_id"],"direction":r["direction"],"strategy":json_load(r.get("payload_json"),"strategy"),"setup_id":json_load(r.get("payload_json"),"setup_id"),"entry":r["entry"],"sl":r["sl"],"tp":r["tp"]} for r in active];return {"status":"active_signal_locked","reason":"DIFFERENT_SETUP_ALREADY_ACTIVE","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"active_signals":active_signals,"resolved_this_scan":resolved,"setup":setup,"live_orders_allowed":False}
        payload={**setup,"signal_id":signal_id,"setup_key":setup.get("setup_id"),"replay":False,"created_at":datetime.now(timezone.utc).isoformat()};recorded=history.record_signal(payload)
        if not recorded:return {"status":"duplicate_suppressed","reason":"HISTORY_INSERT_REJECTED","engine_version":engine.ENGINE_VERSION,"signal":signal,"signal_id":signal_id}
        telegram=send_telegram(_telegram_text(symbol,setup));return {"status":"signal_sent" if telegram.get("success") else "signal_recorded_telegram_failed","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"signal":signal,"strategy":setup.get("strategy"),"engine":setup.get("engine"),"strategy_mode":setup.get("strategy_mode","NATIVE"),"source_asset":setup.get("source_asset",symbol),"entry_type":setup.get("entry_type"),"setup_id":setup.get("setup_id"),"trigger_id":setup.get("trigger_id"),"signal_id":signal_id,"recorded":True,"telegram":telegram,"telegram_alert_sent":bool(telegram.get("success")),"setup":setup,"live_orders_allowed":False}
def json_load(payload,key):
    try:return json.loads(payload or "{}").get(key)
    except Exception:return None