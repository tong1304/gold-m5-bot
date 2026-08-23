"""V9.1 live scanner adapter."""
import os
from datetime import datetime, timezone
import live_scanner_v9 as _base
import engine_v9_1 as engine
SUPPORTED_SYMBOLS=_base.SUPPORTED_SYMBOLS
_SCAN_LOCK=_base._SCAN_LOCK
_ALERTED_SIGNAL_KEYS=_base._ALERTED_SIGNAL_KEYS
_lse_frame=_base._lse_frame
_load_frames=_base._load_frames
_fmt_time=_base._fmt_time
_fmt_price=_base._fmt_price

def _levels_ready(levels,direction=None):
    if not isinstance(levels,dict) or not levels.get("valid",False): return False
    try:
        entry,sl,tp=map(float,(levels["entry"],levels["sl"],levels["tp"])); rr=float(levels.get("effective_rr",levels.get("risk_reward",0)))
        if direction=="BUY" and not sl<entry<tp:return False
        if direction=="SELL" and not sl>entry>tp:return False
        return entry>0 and sl>0 and tp>0 and rr>=1.0
    except (TypeError,ValueError,KeyError): return False

def _format_telegram(symbol,setup,signal_id):
    direction=setup["signal"]; levels=setup["trade_levels"]; loc=setup.get("location") or {}; h1=setup.get("structure_bias",{}).get("bias","NEUTRAL"); pattern=(setup.get("pattern") or {}).get("name","-"); ind=setup.get("indicator_context") or {}; side="🟢 BUY — ซื้อ" if direction=="BUY" else "🔴 SELL — ขาย"
    return ("🚨 <b>V9.1 Pattern Signal</b>\n\n" f"{side}\n\n📊 <b>สินทรัพย์:</b> {symbol}\n⏱ <b>Entry TF:</b> M5\n🕯 <b>แท่ง:</b> {_fmt_time(setup.get('candle_time'))}\n🔐 <b>Signal ID:</b> {signal_id}\n\n" f"🧭 <b>H1 Structure:</b> {h1}\n📍 <b>M15 Location:</b> {loc.get('zone','-')}\n🕯 <b>M5 Pattern:</b> {pattern}\n📐 <b>RR:</b> {levels['risk_reward']}R\n🛑 <b>SL:</b> {_fmt_price(levels['sl'])}\n🎯 <b>TP:</b> {_fmt_price(levels['tp'])}\n\n" f"📊 <b>Indicators:</b> EMA={'PASS' if ind.get('ema20_ok') else 'context'} | MACD={'PASS' if ind.get('macd_ok') else 'context'} | RSI={ind.get('rsi14','-')}\n\n⚠️ ระบบไม่เปิดออเดอร์อัตโนมัติ")

def scan_once(symbol="BTC"):
    symbol=(symbol or "BTC").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS: raise ValueError(f"ไม่รองรับสินทรัพย์: {symbol}; รองรับ: BTC, GOLD")
    with _SCAN_LOCK:
        cfg={"BTC":{"MINIMUM_ATR":0.0,"MIN_STOP_ATR":0.0,"MAX_STOP_ATR":4.0,"SPREAD":5.0,"SLIPPAGE":2.0},"GOLD":{"MINIMUM_ATR":0.0,"MIN_STOP_ATR":0.0,"MAX_STOP_ATR":4.0,"SPREAD":0.50,"SLIPPAGE":0.20}}[symbol]
        for key,value in cfg.items(): setattr(engine,key,value)
        engine.MIN_RISK_REWARD=1.0; engine.RISK_REWARD=max(float(os.getenv("RISK_REWARD","1.0")),1.0)
        frames=_load_frames(symbol); m5=frames["5m"]; index=len(m5)-1; setup=engine.analyze_structure_setup(m5,frames["15m"],frames["1h"],index)
        candle_time=str(m5.iloc[index].get("datetime","")); setup.update({"candle_time":candle_time,"closed_candle":candle_time,"symbol":symbol,"previous_close":float(m5.iloc[index]["close"]),"engine_version":engine.ENGINE_VERSION})
        signal=setup.get("signal"); valid=signal in ("BUY","SELL") and _levels_ready(setup.get("trade_levels"),signal); setup["valid"]=valid
        setup_key=setup.get("setup_key") or f"{symbol}|{candle_time}|{signal}"; suffix=signal if valid else "NO_TRADE"; signal_id=f"{symbol}-{str(candle_time).replace(':','').replace('-','').replace(' ','-')}-{suffix}"; setup["signal_id"]=signal_id
        if not valid:
            payload={**setup,"signal":"NO_TRADE","result":"NO_TRADE","created_at":datetime.now(timezone.utc).isoformat(),"no_trade_reasons":setup.get("rejection_reasons") or []}; recorded=_base.history.record_no_trade(payload); print(f"[{symbol}] V9.1 NO_TRADE recorded={recorded} reasons={setup.get('rejection_reasons')}",flush=True); return {"status":"no_trade","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"signal":"NO_TRADE","recorded":recorded,**setup}
        if setup_key in _ALERTED_SIGNAL_KEYS or _base.history.get(signal_id): return {"status":"duplicate_suppressed","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"signal":signal,"signal_id":signal_id,"setup_key":setup_key}
        payload={"signal_id":signal_id,"symbol":symbol,"signal":signal,"closed_candle":candle_time,"created_at":datetime.now(timezone.utc).isoformat(),"engine_version":engine.ENGINE_VERSION,"replay":False,"pattern_signal":signal,"m5_direction":signal,"v9_setup":setup,"structure_bias":setup.get("structure_bias"),"location":setup.get("location"),"liquidity_event":setup.get("liquidity_event"),"m5_trigger":setup.get("m5_trigger"),"pullback":setup.get("pullback"),"target_liquidity":setup.get("target_liquidity"),"rejection_reasons":setup.get("rejection_reasons"),"trade_levels":setup["trade_levels"],"mtf":{"H1":{"bias":setup.get("structure_bias",{}).get("bias")},"M15":{"bias":setup.get("m15_structure",{}).get("bias")},"M5":signal}}
        recorded=_base.history.record_signal(payload); telegram_result=engine.send_telegram(_format_telegram(symbol,setup,signal_id)); _ALERTED_SIGNAL_KEYS.add(setup_key)
        return {"status":"signal_sent" if telegram_result.get("success") else "signal_recorded_telegram_failed","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"signal":signal,"signal_id":signal_id,"recorded":recorded,"telegram":telegram_result,"telegram_alert_sent":bool(telegram_result.get("success")),"setup":setup}
