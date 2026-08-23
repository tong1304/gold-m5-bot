"""V11 scheduler for BTC + GOLD using the V11 M5/M15 strategy-split scanner."""
import logging, os, threading, time
from datetime import datetime, timezone, time as dt_time
from zoneinfo import ZoneInfo

logger=logging.getLogger("signal_scheduler")
ENGINE_VERSION="11.0-M5-M15-STRATEGY-SPLIT"
_RUNNING=False; _THREAD=None; _LAST_CLOSED_CANDLE={}; _LAST_TEST_SLOT=None
BANGKOK=ZoneInfo("Asia/Bangkok"); UTC=timezone.utc; DISPLAY_SYMBOLS=("BTC","GOLD")
GOLD_OPEN_SUNDAY_UTC=os.getenv("GOLD_OPEN_SUNDAY_UTC","23:00"); GOLD_CLOSE_FRIDAY_UTC=os.getenv("GOLD_CLOSE_FRIDAY_UTC","22:00"); GOLD_DAILY_BREAK_START_UTC=os.getenv("GOLD_DAILY_BREAK_START_UTC","22:00"); GOLD_DAILY_BREAK_END_UTC=os.getenv("GOLD_DAILY_BREAK_END_UTC","23:00")

def _interval_seconds():
    try: configured=int(os.getenv("SIGNAL_SCAN_INTERVAL_SECONDS","300"))
    except ValueError: configured=300
    return max(300,configured)

def _symbols():
    out=[]
    for value in os.getenv("LIVE_SIGNAL_SYMBOLS","BTC,GOLD").split(","):
        symbol=value.strip().upper()
        if symbol in DISPLAY_SYMBOLS and symbol not in out: out.append(symbol)
    return out

def _parse_time(value,fallback):
    try: h,m=str(value).split(":",1); return dt_time(int(h),int(m))
    except (TypeError,ValueError): return fallback

def _asset_market_status(symbol,now_utc=None):
    now_utc=now_utc or datetime.now(UTC)
    if symbol=="BTC": return True,"OPEN_24_7"
    if symbol!="GOLD": return False,"UNKNOWN_MARKET_SESSION"
    current,weekday=now_utc.time(),now_utc.weekday(); sunday=_parse_time(GOLD_OPEN_SUNDAY_UTC,dt_time(23,0)); friday=_parse_time(GOLD_CLOSE_FRIDAY_UTC,dt_time(22,0)); br_start=_parse_time(GOLD_DAILY_BREAK_START_UTC,dt_time(22,0)); br_end=_parse_time(GOLD_DAILY_BREAK_END_UTC,dt_time(23,0))
    if weekday==5: return False,"WEEKEND_CLOSED"
    if weekday==6: return (current>=sunday,"OPEN" if current>=sunday else "SUNDAY_CLOSED")
    if weekday==4: return (current<friday,"OPEN" if current<friday else "FRIDAY_CLOSED")
    if br_start<br_end and br_start<=current<br_end: return False,"DAILY_BREAK"
    return True,"OPEN"

def _scanner():
    """Always return the actual V11 scanner; never fall back to V9/V10 adapters."""
    import live_scanner_v11
    return live_scanner_v11

def _notify_error(exc,context):
    text=(f"❌ <b>ระบบ {ENGINE_VERSION} Scheduler ขัดข้อง</b>\n\n" f"🕐 {datetime.now(UTC).astimezone(BANGKOK).strftime('%d/%m/%Y %H:%M:%S')} (กรุงเทพฯ)\n📍 {context}\n🔴 {type(exc).__name__}\n📝 {exc}\n\n🛑 ไม่มีการเปิดออเดอร์อัตโนมัติ")
    try: return _scanner().send_telegram(text)
    except Exception: return None

def _record_data_no_trade(symbol,reason):
    try:
        from signal_history import history
        now=datetime.now(UTC).replace(second=0,microsecond=0); candle_time=now.isoformat(); signal_id=f"{symbol}-{now.strftime('%Y%m%d-%H%M')}-NO_TRADE-DATA"
        payload={"signal_id":signal_id,"symbol":symbol,"signal":"NO_TRADE","result":"NO_TRADE","closed_candle":candle_time,"candle_time":candle_time,"created_at":datetime.now(UTC).isoformat(),"engine_version":ENGINE_VERSION,"rejection_reasons":[str(reason)],"no_trade_reasons":[str(reason)],"data_valid":False}
        recorded=history.record_no_trade(payload); logger.warning("[%s] DATA NO_TRADE recorded=%s reason=%s",symbol,recorded,reason); return recorded
    except Exception as exc: logger.exception("[%s] Failed to record DATA NO_TRADE: %s",symbol,exc); return False

def _evaluate_signal_history():
    from signal_history import history
    pending=history.pending(limit=200)
    if not pending: return 0
    scanner=_scanner(); resolved=0
    for row in pending:
        try:
            symbol=str(row.get("symbol","")).upper()
            if symbol not in DISPLAY_SYMBOLS: continue
            frame=scanner._lse_frame(symbol,"5m",max(200,int(os.getenv("LIVE_SIGNAL_HISTORY","200")))); before=row["result"]
            updated=history.evaluate_candles(row["signal_id"],frame.to_dict("records"))
            if updated and updated.get("result")!=before: resolved+=1; logger.warning("[SIGNAL HISTORY] %s -> %s r=%s source=LSE",row["signal_id"],updated.get("result"),updated.get("r_multiple"))
        except Exception as exc: logger.warning("[SIGNAL HISTORY] evaluate failed for %s: %s",row.get("signal_id"),exc)
    return resolved

def _system_test(now_bkk):
    global _LAST_TEST_SLOT
    if now_bkk.minute%15!=0: return None
    slot=now_bkk.strftime("%Y-%m-%d %H:%M")
    if slot==_LAST_TEST_SLOT: return None
    lines=[f"🧪 <b>ทดสอบระบบ {ENGINE_VERSION} ทุก 15 นาที</b>","",f"🕐 เวลา: {now_bkk.strftime('%d/%m/%Y %H:%M')} (กรุงเทพฯ)",""]; live_ok=True
    try:
        import live_price; status=live_price.status()
        for symbol in _symbols():
            open_,session=_asset_market_status(symbol,now_bkk.astimezone(UTC))
            if not open_: lines.append(f"⏸ {symbol}: ตลาดปิด ({session})"); continue
            live=live_price.get(symbol)
            if not live or live.get("age_seconds") is None or float(live.get("age_seconds",999999))>float(os.getenv("MAX_LIVE_PRICE_AGE_SECONDS","30")):
                live_ok=False; lines.append(f"⚠️ {symbol}: ยังไม่มี Live Tick ที่สดพอ"); continue
            lines.append(f"💹 {symbol}: <b>{float(live['price']):,.8f}</b> | Live age: {float(live['age_seconds']):.1f}s")
        if not status.get("running"): live_ok=False
    except Exception as exc: live_ok=False; lines.append(f"❌ LSE Live Price: {type(exc).__name__}: {exc}")
    lines += ["",f"✅ {ENGINE_VERSION} Scheduler ทำงาน","✅ LSE WebSocket Live Price" if live_ok else "⚠️ LSE WebSocket Live Price มีปัญหา","✅ Telegram Monitor","",f"ℹ️ การทดสอบนี้ไม่ใช่สัญญาณ BUY/SELL ของ {ENGINE_VERSION}"]
    try:
        result=_scanner().send_telegram("\n".join(lines)); sent=bool(isinstance(result,dict) and result.get("success"))
        if sent: _LAST_TEST_SLOT=slot
        return {"sent":sent,"slot":slot,"telegram_result":result,"timezone":"Asia/Bangkok","live_price_ok":live_ok,"engine_version":ENGINE_VERSION}
    except Exception as exc: return {"sent":False,"slot":slot,"error_type":type(exc).__name__,"error":str(exc),"live_price_ok":live_ok,"engine_version":ENGINE_VERSION}

def run_scan_cycle():
    now_bkk=datetime.now(UTC).astimezone(BANGKOK); now_utc=now_bkk.astimezone(UTC); symbols=_symbols(); logger.warning("[HEARTBEAT] %s Scheduler cycle START: %s | symbols=%s | interval=%ss | provider=LSE",ENGINE_VERSION,now_bkk.strftime("%d/%m/%Y %H:%M:%S"),symbols,_interval_seconds())
    heartbeat=_system_test(now_bkk); history_resolved=_evaluate_signal_history(); results=[]; scanner=_scanner()
    for symbol in symbols:
        try:
            open_,session=_asset_market_status(symbol,now_utc)
            if not open_: logger.warning("[%s] MARKET CLOSED: %s",symbol,session); results.append({"status":"market_closed","symbol":symbol,"session":session,"live_orders_allowed":False}); continue
            logger.warning("[%s] %s Fetching closed M5 candles from LSE",symbol,ENGINE_VERSION); frame=scanner._lse_frame(symbol,"5m",max(100,int(os.getenv("LIVE_SIGNAL_HISTORY","200"))))
            if frame.empty: raise RuntimeError(f"ไม่มีแท่ง M5 จาก LSE สำหรับ {symbol}")
            closed_key=str(frame.iloc[-1]["datetime"]); logger.warning("[%s] Latest closed M5 candle: %s",symbol,closed_key)
            if _LAST_CLOSED_CANDLE.get(symbol)==closed_key: logger.warning("[%s] WAITING_NEW_CANDLE: %s",symbol,closed_key); results.append({"status":"waiting_new_candle","symbol":symbol,"timeframe":"M5","closed_candle":closed_key,"live_orders_allowed":False,"engine_version":ENGINE_VERSION}); continue
            logger.warning("[%s] Calling %s Multi-Strategy Signal Engine",symbol,ENGINE_VERSION); result=scanner.scan_once(symbol); _LAST_CLOSED_CANDLE[symbol]=closed_key; result["trigger"]="NEW_CLOSED_M5_CANDLE"; result["candle_consumed"]=True; result["market_session"]=session; result["engine_version"]=ENGINE_VERSION
            candidates=(result.get("strategy_candidates") or (result.get("setup") or {}).get("strategy_candidates") or [])
            for candidate in candidates:
                logger.warning("[%s] V11 STRATEGY | %s",symbol,candidate)
            reasons=result.get("rejection_reasons") or result.get("no_trade_reasons") or (result.get("setup") or {}).get("rejection_reasons") or []
            if result.get("signal")=="NO_TRADE": logger.warning("[%s] %s NO_TRADE strategy=%s recorded=%s reasons=%s",symbol,ENGINE_VERSION,result.get("strategy"),result.get("recorded"),reasons)
            else: logger.warning("[%s] %s result: signal=%s strategy=%s status=%s recorded=%s",symbol,ENGINE_VERSION,result.get("signal"),result.get("strategy"),result.get("status"),result.get("recorded"))
            results.append(result)
        except Exception as exc:
            message=str(exc); logger.exception("[%s] %s Scan failed",symbol,ENGINE_VERSION)
            if any(tag in message for tag in ("STALE_MARKET_DATA","DATA_INVALID","LSE_RECENT_DATA_UNAVAILABLE")):
                recorded=_record_data_no_trade(symbol,message); results.append({"status":"data_invalid","symbol":symbol,"signal":"NO_TRADE","recorded":recorded,"reason":message,"data_valid":False,"live_orders_allowed":False,"engine_version":ENGINE_VERSION})
            else: _notify_error(exc,f"การสแกน {ENGINE_VERSION} {symbol}"); results.append({"status":"scan_error","symbol":symbol,"error_type":type(exc).__name__,"message":message,"live_orders_allowed":False,"engine_version":ENGINE_VERSION})
    if heartbeat is not None: results.append({"status":"price_heartbeat","heartbeat":heartbeat,"timezone":"Asia/Bangkok","engine_version":ENGINE_VERSION})
    if history_resolved: results.append({"status":"signal_history_resolved","count":history_resolved,"engine_version":ENGINE_VERSION})
    logger.warning("[HEARTBEAT] %s Scheduler cycle END: processed=%d symbol(s) | provider=LSE",ENGINE_VERSION,len(results)); return results

def _seconds_to_next_five_minute(): return max(1,300-(datetime.now(UTC).timestamp()%300))

def _loop():
    global _RUNNING
    logger.warning("[BOOT TEST] Running immediate %s scan after scheduler startup",ENGINE_VERSION)
    try: run_scan_cycle()
    except Exception as exc: logger.exception("Immediate %s scheduler cycle failed",ENGINE_VERSION); _notify_error(exc,f"รอบทดสอบ {ENGINE_VERSION} ทันทีหลัง Scheduler เริ่ม")
    while _RUNNING:
        wait=_seconds_to_next_five_minute(); logger.warning("[HEARTBEAT] Next scheduled %s cycle in %.1fs",ENGINE_VERSION,wait); time.sleep(wait)
        if not _RUNNING: break
        started=time.monotonic()
        try: run_scan_cycle()
        except Exception as exc: logger.exception("Fatal %s scheduler cycle error",ENGINE_VERSION); _notify_error(exc,f"รอบการทำงานหลักของ {ENGINE_VERSION} Scheduler")
        elapsed=time.monotonic()-started; wait=_seconds_to_next_five_minute(); logger.warning("[HEARTBEAT] %s Scheduler cycle returned; elapsed=%.2fs; next_cycle_in=%.1fs; provider=LSE",ENGINE_VERSION,elapsed,wait)

def start():
    global _RUNNING,_THREAD
    if _RUNNING and _THREAD and _THREAD.is_alive(): return False
    _RUNNING=True; _THREAD=threading.Thread(target=_loop,name="m5-btc-gold-v11-scanner",daemon=True); _THREAD.start(); logger.warning("%s Multi-Strategy Scheduler started successfully; thread=%s",ENGINE_VERSION,ENGINE_VERSION); return True

def stop():
    global _RUNNING; _RUNNING=False

def status():
    now=datetime.now(UTC)
    try: import live_price; live=live_price.status()
    except Exception as exc: live={"running":False,"error":f"{type(exc).__name__}: {exc}"}
    return {"running":bool(_RUNNING and _THREAD and _THREAD.is_alive()),"interval_seconds":_interval_seconds(),"symbols":_symbols(),"test_slots":"00,15,30,45","timezone":"Asia/Bangkok","provider":"LSE","engine_version":ENGINE_VERSION,"live_price":live,"statistics_page":"/statistics","statistics_api":"/api/statistics","market_sessions":{s:{"open":_asset_market_status(s,now)[0],"session":_asset_market_status(s,now)[1]} for s in _symbols()}}
