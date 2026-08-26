from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import requests

from ..contracts import DecisionResult

FORBIDDEN_LEGACY_TERMS = ("V11", "V12", "12.11", "CROSS-ASSET-FALLBACK", "H1 → M15 → M5", "B1-B3", "G1-G3")
TELEGRAM_MAX_TEXT = 4096
ENGINE_THAI_NAMES = {"E1":"สภาวะตลาด","E2":"Regime / Playbook","E3":"โครงสร้างตลาด","E4":"สภาพคล่อง","E5":"ตำแหน่งราคา","E6":"Trade Setup","E7":"Confirmation","E8":"Risk / Trade Economics","E9":"การตัดสินใจ"}
STATE_TH = {"VALID":"ข้อมูลใช้ได้","UP":"ขาขึ้น","DOWN":"ขาลง","BULLISH":"ขาขึ้น","BEARISH":"ขาลง","NEUTRAL":"เป็นกลาง","TREND_UP":"แนวโน้มขาขึ้น","TREND_DOWN":"แนวโน้มขาลง","TREND":"Trend","RANGE":"Range","COMPRESSION":"Compression","EXPANSION":"Expansion","TRANSITION":"Transition","MATURE":"สมบูรณ์","TRIGGER_OBSERVED":"พบ Trigger","QUALITY_PASS":"คุณภาพผ่าน","FOLLOW_THROUGH_OBSERVED":"มี Follow-through","CONFIRMATION_PASS":"ยืนยันผ่าน","FAILURE":"Failure","LOCATION_QUALITY_PASS":"PASS","LOCATION_QUALITY_FAIL":"FAIL","UNKNOWN":"ยังไม่ชัดเจน","NON_DOMINANT":"NON_DOMINANT","QUALITY_MEASURABLE":"QUALITY_MEASURABLE","NO_SWEEP":"ไม่มี Sweep","NO_RECLAIM":"ไม่มี Reclaim","NOT_EXTENDED":"NOT_EXTENDED","EXTENDED":"EXTENDED","SPACE_AVAILABLE":"SPACE_AVAILABLE","LIMITED_SPACE":"SPACE_LIMITED","SETUP_FORMING":"FORMING","QUALITY_WEAK":"WEAK","NO_TRIGGER":"NO_TRIGGER","NO_FOLLOW_THROUGH":"NO_FOLLOW_THROUGH","CONFIRMATION_WAIT":"ยังไม่ยืนยัน"}


def _validate(text: str) -> str:
    assert not any(term in text for term in FORBIDDEN_LEGACY_TERMS)
    return text


def _fmt(value: Any) -> str:
    if value is None: return "ไม่พบข้อมูล"
    if isinstance(value, bool): return "ใช่" if value else "ไม่"
    if isinstance(value, float): return f"{value:.4f}".rstrip("0").rstrip(".")
    return STATE_TH.get(str(value), str(value))


def _analysis_status(engine: Any) -> str:
    eid = engine.engine_id
    r = engine.output.get("professional_reasoning", {}) or {}
    status = engine.output.get("analysis_status", "")
    reasons = set(engine.output.get("analysis_reason_codes", ()) or engine.reason_codes or ())
    if eid == "E9":
        return "🟢" if engine.output.get("decision") in {"BUY", "SELL"} else "🔴"
    if eid == "E1":
        market_state = r.get("market_state") or engine.output.get("market_state")
        return "🟢" if market_state and market_state != "UNCLEAR" else "🟡"
    if eid == "E5" and (r.get("location_quality") == "LOCATION_QUALITY_FAIL" or r.get("space") == "LIMITED_SPACE"): return "🔴"
    if eid == "E7" and r.get("confirmation") != "CONFIRMATION_PASS": return "🔴"
    if eid == "E8" and not (r.get("trade_plan") or {}).get("valid"): return "🔴"
    if reasons & {"E1_DATA_INVALID", "E3_STRUCTURE_INVALIDATED", "E6_SETUP_INVALIDATED"}: return "🔴"
    return {"STRONG_EVIDENCE":"🟢","PARTIAL_EVIDENCE":"🟡","WEAK_EVIDENCE":"🟠","NOT_CONFIRMED":"🟡","CONFIRMED":"🟢","ECONOMICS_READY":"🟢","ECONOMICS_UNAVAILABLE":"🟡","CONFLICT_OR_INVALID":"🔴"}.get(status, "🟡")


def _engine_answer(engine: Any) -> str:
    e = engine.engine_id; r = engine.output.get("professional_reasoning", {}) or {}
    if e == "E1":
        market_state = r.get("market_state") or engine.output.get("market_state")
        volatility = r.get("volatility_state") or engine.output.get("volatility_state")
        structure = r.get("structure_state") or engine.output.get("structure_state")
        transition = r.get("transition") or engine.output.get("transition")
        answer = f"State={_fmt(market_state)} / Volatility={_fmt(volatility)} / Structure={_fmt(structure)} / Transition={_fmt(transition)}"
    elif e == "E2": answer = f"{_fmt(r.get('regime'))} / {_fmt(r.get('preferred_direction'))}"
    elif e == "E3": answer = f"{_fmt(r.get('structure'))} / {_fmt(r.get('alignment'))}"
    elif e == "E4": answer = f"{_fmt(r.get('liquidity_quality'))} / Sweep {_fmt(r.get('sweep'))}"
    elif e == "E5": answer = f"{_fmt(r.get('location_quality'))} / {_fmt(r.get('space'))}"
    elif e == "E6": answer = f"{_fmt(r.get('setup_type'))} / {_fmt(r.get('formation'))}"
    elif e == "E7": answer = f"{_fmt(r.get('trigger'))} / {_fmt(r.get('confirmation'))}"
    elif e == "E8":
        p = r.get("trade_plan") or {}
        answer = f"RR 1:{float(p.get('rr_tp2',0)):.1f}" if p.get("valid") else _fmt(p.get("reason"))
    elif e == "E9":
        decision = engine.output.get("decision")
        answer = "BUY" if decision == "BUY" else "SELL" if decision == "SELL" else "NO_TRADE"
    else: answer = "ไม่พบข้อมูล"
    return f"{_analysis_status(engine)} {e} — {ENGINE_THAI_NAMES.get(e, e)}\nคำตอบ: {answer}"


def format_decision(result: DecisionResult) -> str:
    if result.decision not in {"BUY", "SELL"} or not result.gate_passed: raise ValueError("Only actionable E9 BUY/SELL decisions can be notified")
    plan = result.trade_plan; required = ("entry", "stop_loss", "take_profit_1", "take_profit_2", "rr_tp2")
    if not plan.get("valid") or any(k not in plan for k in required): raise ValueError("Actionable E9 decision requires a complete E8 trade plan")
    direction = "ซื้อ" if result.decision == "BUY" else "ขาย"
    lines = [f"{'🟢 BUY' if result.decision=='BUY' else '🔴 SELL'} — {direction}", "", f"📊 สินทรัพย์: {result.symbol}", f"⏱ Timeframe: {result.timeframe}", "🧠 E1-E8 วิเคราะห์หลักฐานเฉพาะด้าน → E9 เป็นผู้ตัดสินใจเทรดเท่านั้น", "", "━━━━━━━━━━━━━━━━━━", "🧠 คำตอบสั้นจากแต่ละ Engine", "━━━━━━━━━━━━━━━━━━"]
    for engine in result.engines: lines += ["", _engine_answer(engine)]
    lines += ["", "━━━━━━━━━━━━━━━━━━", "🎯 FINAL DECISION", "━━━━━━━━━━━━━━━━━━", f"🟢 E9 อนุมัติการออกออเดอร์: {result.decision}", "", "━━━━━━━━━━━━━━━━━━", "📋 Trade Plan", "━━━━━━━━━━━━━━━━━━", f"📍 Entry: {plan['entry']}", f"🛑 Stop Loss: {plan['stop_loss']}", f"🎯 Take Profit 1: {plan['take_profit_1']}", f"🎯 Take Profit 2: {plan['take_profit_2']}", f"📐 RR: 1:{plan['rr_tp2']:.1f}"]
    return _validate("\n".join(lines))


def format_startup(symbols: list[str]) -> str:
    return _validate("\n".join(["✅ ระบบ 9-Engine เริ่มทำงาน", "", "⚙️ ระบบ: PRODUCTION-V2", "🧠 โครงสร้าง: E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9", f"📊 สินทรัพย์: {', '.join(symbols)}", "⏱ Timeframe: M5", "", "🔄 ทุกแท่ง M5 ที่ปิดจะเริ่มวิเคราะห์ใหม่ตั้งแต่ E1", "🎯 E9 เท่านั้นที่มีสิทธิ์ตัดสิน BUY / SELL / NO_TRADE", "✅ ระบบพร้อมทำงาน"]))


def format_status(status: dict[str, Any]) -> str:
    timestamp = status.get("timestamp"); timestamp_text = timestamp.strftime("%d/%m/%Y %H:%M:00") if isinstance(timestamp, datetime) else str(timestamp or datetime.now().strftime("%d/%m/%Y %H:%M:00")); prices = status.get("prices", {})
    def price_text(symbol: str) -> str:
        value = prices.get(symbol)
        if value is None: return "ไม่พร้อมใช้งาน"
        try: return f"{float(value):,.2f}"
        except (TypeError, ValueError): return str(value)
    return _validate("\n".join(["✅ สถานะระบบ PRODUCTION-V2", "", "🧠 โครงสร้าง: E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9", "⏱ Timeframe: M5", "", f"🚨 เวลาแจ้งเตือน: {timestamp_text} (ประเทศไทย)", "", "📡 ราคาปัจจุบัน:", f"🌕 GOLD: {price_text('GOLD')}", f"🪙 BTC: {price_text('BTC')}", "", "🎯 E9 เท่านั้นเป็น Final Decision Authority", "", "✅ ระบบทำงานปกติ"]))


def format_critical(message: str, component: str) -> str:
    return _validate(f"🔴 ระบบผิดปกติ\n\n⚠️ ส่วนที่มีปัญหา: {component}\n📌 รายละเอียด: {message}\n\n⛔ กรุณาตรวจสอบระบบ")


def _chunk_text(text: str, limit: int = TELEGRAM_MAX_TEXT) -> list[str]:
    if len(text) <= limit: return [text]
    chunks=[]; current=[]; size=0
    for line in text.splitlines(keepends=True):
        if current and size + len(line) > limit: chunks.append("".join(current).rstrip()); current=[]; size=0
        if len(line) > limit:
            chunks.extend(line[i:i+limit].rstrip() for i in range(0, len(line), limit)); continue
        current.append(line); size += len(line)
    if current: chunks.append("".join(current).rstrip())
    return chunks


def send(text: str) -> bool:
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id: return False
    for chunk in _chunk_text(text):
        response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id":chat_id,"text":chunk}, timeout=15)
        if not response.ok:
            try: detail = response.json().get("description", response.text)
            except ValueError: detail = response.text
            raise RuntimeError(f"Telegram sendMessage failed ({response.status_code}): {detail}")
    return True


def send_decision(result: DecisionResult) -> bool:
    if result.decision not in {"BUY", "SELL"} or not result.gate_passed: return False
    return send(format_decision(result))
