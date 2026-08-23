"""Multi-Strategy live scanner adapter using only M15 and M5."""
import os, logging
from datetime import datetime, timezone
import live_scanner_v9 as _base
import engine_v9_2 as engine
logger=logging.getLogger("signal_scheduler")
SUPPORTED_SYMBOLS=_base.SUPPORTED_SYMBOLS
_SCAN_LOCK=_base._SCAN_LOCK
_ALERTED_SIGNAL_KEYS=_base._ALERTED_SIGNAL_KEYS
_fmt_time=_base._fmt_time
_fmt_price=_base._fmt_price


def _lse_frame(symbol,timeframe="5m",history_points=200):
    if timeframe not in ("5m","15m"): raise ValueError(f"Unsupported timeframe for M15/M5 engine: {timeframe}")
    return _base._lse_frame(symbol,timeframe,history_points)


def _load_frames(symbol):
    history_points=max(100,int(os.getenv("LIVE_SIGNAL_HISTORY","200"))); frames={}
    for tf,minimum in (("15m",100),("5m",100)):
        df=_lse_frame(symbol,tf,history_points)
        if len(df)<minimum: raise RuntimeError(f"Insufficient closed LSE data for {symbol} {tf}: {len(df)}")
        frames[tf]=df.reset_index(drop=True)
    latest=frames["5m"].iloc[-1]["datetime"]
    if frames["15m"].iloc[-1]["datetime"]>latest: frames["15m"]=frames["15m"].iloc[:-1].reset_index(drop=True)
    return frames


def _levels_ready(levels,direction=None):
    if not isinstance(levels,dict) or not levels.get("valid",False): return False
    try:
        entry,sl,tp=map(float,(levels["entry"],levels["sl"],levels["tp"])); rr=float(levels.get("effective_rr",levels.get("risk_reward",0)))
        if direction=="BUY" and not sl<entry<tp:return False
        if direction=="SELL" and not sl>entry>tp:return False
        return entry>0 and sl>0 and tp>0 and rr>=1.0
    except (TypeError,ValueError,KeyError): return False


def _format_telegram(symbol,setup,signal_id):
    direction=setup["signal"]; levels=setup["trade_levels"]; regime=setup.get("regime","-"); strategy=setup.get("strategy","-"); loc=setup.get("location") or {}; ind=setup.get("indicator_context") or {}
    side="🟢 BUY — ซื้อ" if direction=="BUY" else "🔴 SELL — ขาย"
    return ("🚨 <b>Multi-Strategy Signal</b>\n\n" f"{side}\n\n📊 <b>สินทรัพย์:</b> {symbol}\n⏱ <b>Entry TF:</b> M5\n🧭 <b>Context TF:</b> M15\n🧠 <b>Market Regime:</b> {regime}\n🎯 <b>Strategy:</b> {strategy}\n🕯 <b>Trigger:</b> {setup.get('analysis_window',{}).get('m5_trigger_bars',3)} closed candles\n🔐 <b>Signal ID:</b> {signal_id}\n\n📍 <b>M15 Location:</b> {loc.get('zone','-')}\n📐 <b>RR:</b> {levels['risk_reward']}R\n🛑 <b>SL:</b> {_fmt_price(levels['sl'])}\n🎯 <b>TP:</b> {_fmt_price(levels['tp'])}\n\n📊 <b>M5 Context:</b> EMA={'PASS' if ind.get('ema20_ok') else 'context'} | MACD={'PASS' if ind.get('macd_ok') else 'context'} | RSI={ind.get('rsi14','-')}\n\n⚠️ ระบบไม่เปิดออเดอร์อัตโนมัติ")


def scan_once(symbol="BTC"):
    symbol=(symbol or "BTC").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS: raise ValueError(f"ไม่รองรับสินทรัพย์: {symbol}; รองรับ: BTC, GOLD")
    with _SCAN_LOCK:
        cfg={"BTC":{"MINIMUM_ATR":0.0,"MIN_STOP_ATR":0.0,"MAX_STOP_ATR":4.0,"SPREAD":5.0,"SLIPPAGE":2.0},"GOLD":{"MINIMUM_ATR":0.0,"MIN_STOP_ATR":0.0,"MAX_STOP_ATR":4.0,"SPREAD":0.50,"SLIPPAGE":0.20}}[symbol]
        for key,value in cfg.items():setattr(engine,key,value)
        engine.MIN_RISK_REWARD=1.0; engine.RISK_REWARD=max(float(os.getenv("RISK_REWARD","1.0")),1.0)
        frames=_load_frames(symbol); m5=frames["5m"]; index=len(m5)-1
        setup=engine.analyze_structure_setup(m5,frames["15m"],index)
        candle_time=str(m5.iloc[index].get("datetime","")); setup.update({"candle_time":candle_time,"closed_candle":candle_time,"symbol":symbol,"previous_close":float(m5.iloc[index]["close"]),"engine_version":engine.ENGINE_VERSION})
        signal=setup.get("signal"); valid=signal in ("BUY","SELL") and _levels_ready(setup.get("trade_levels"),signal); setup["valid"]=valid
        setup_key=setup.get("setup_key") or f"{symbol}|{candle_time}|{signal}"; suffix=signal if valid else "NO_TRADE"; signal_id=f"{symbol}-{str(candle_time).replace(':','').replace('-','').replace(' ','-')}-{suffix}"; setup["signal_id"]=signal_id
        if not valid:
            reasons=setup.get("rejection_reasons") or ["NO_TRADE_REASON_UNSPECIFIED"]; payload={**setup,"signal":"NO_TRADE","result":"NO_TRADE","created_at":datetime.now(timezone.utc).isoformat(),"no_trade_reasons":reasons,"rejection_reasons":reasons}; recorded=_base.history.record_no_trade(payload)
            logger.warning("[%s] %s NO_TRADE strategy=%s regime=%s recorded=%s reasons=%s",symbol,engine.ENGINE_VERSION,setup.get("strategy"),setup.get("regime"),recorded,reasons)
            return {"status":"no_trade","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"signal":"NO_TRADE","strategy":setup.get("strategy","NONE"),"regime":setup.get("regime","NEUTRAL"),"recorded":recorded,"rejection_reasons":reasons,"no_trade_reasons":reasons,**setup}
        if setup_key in _ALERTED_SIGNAL_KEYS or _base.history.get(signal_id): return {"status":"duplicate_suppressed","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"signal":signal,"strategy":setup.get("strategy"),"regime":setup.get("regime"),"signal_id":signal_id,"setup_key":setup_key}
        payload={"signal_id":signal_id,"symbol":symbol,"signal":signal,"closed_candle":candle_time,"created_at":datetime.now(timezone.utc).isoformat(),"engine_version":engine.ENGINE_VERSION,"replay":False,"strategy":setup.get("strategy"),"regime":setup.get("regime"),"strategy_candidates":setup.get("strategy_candidates"),"pattern_signal":signal,"m5_direction":signal,"v10_setup":setup,"structure_bias":setup.get("structure_bias"),"location":setup.get("location"),"liquidity_event":setup.get("liquidity_event"),"m5_trigger":setup.get("m5_trigger"),"pullback":setup.get("pullback"),"target_liquidity":setup.get("target_liquidity"),"rejection_reasons":setup.get("rejection_reasons"),"trade_levels":setup["trade_levels"],"mtf":{"M15":{"bias":setup.get("m15_structure",{}).get("bias")},"M5":signal}}
        recorded=_base.history.record_signal(payload); telegram_result=engine.send_telegram(_format_telegram(symbol,setup,signal_id)); _ALERTED_SIGNAL_KEYS.add(setup_key)
        logger.warning("[%s] %s SIGNAL=%s strategy=%s regime=%s recorded=%s telegram=%s RR=%s",symbol,engine.ENGINE_VERSION,signal,setup.get("strategy"),setup.get("regime"),recorded,bool(telegram_result.get("success")),setup.get("trade_levels",{}).get("risk_reward"))
        return {"status":"signal_sent" if telegram_result.get("success") else "signal_recorded_telegram_failed","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"signal":signal,"strategy":setup.get("strategy"),"regime":setup.get("regime"),"signal_id":signal_id,"recorded":recorded,"telegram":telegram_result,"telegram_alert_sent":bool(telegram_result.get("success")),"setup":setup}
