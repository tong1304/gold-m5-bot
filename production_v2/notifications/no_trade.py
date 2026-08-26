from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .telegram import ENGINE_THAI_NAMES, send

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")
STATE_TH = {"UP":"ขาขึ้น","DOWN":"ขาลง","BULLISH":"ขาขึ้น","BEARISH":"ขาลง","NEUTRAL":"เป็นกลาง","TREND":"Trend","RANGE":"Range","TRANSITION":"Transition","EXPANSION":"Expansion","COMPRESSION":"Compression","VALID":"ข้อมูลใช้ได้","MATURE":"สมบูรณ์","INVALIDATED":"ถูกยกเลิก","TRIGGER_OBSERVED":"พบ Trigger","QUALITY_PASS":"คุณภาพผ่าน","FOLLOW_THROUGH_OBSERVED":"มี Follow-through","CONFIRMATION_PASS":"ยืนยันผ่าน","FAILURE":"Failure","UNKNOWN":"ยังไม่ชัดเจน"}
REASON_TH = {
    "E1_DATA_INVALID":"ข้อมูลตลาดไม่สมบูรณ์",
    "E3_STRUCTURE_INVALIDATED":"โครงสร้างราคาที่ใช้เป็น Thesis ถูกทำลาย",
    "E5_LOCATION_DISADVANTAGED":"ราคาปัจจุบันไม่อยู่ใน Location ที่ได้เปรียบ",
    "E5_SPACE_INSUFFICIENT":"พื้นที่ไปยังเป้าหมายไม่เพียงพอเมื่อเทียบกับความเสี่ยง",
    "E6_SETUP_INVALIDATED":"Trade Setup ถูกทำลาย",
    "E6_NO_VALID_SETUP":"E6 ยังไม่พบ Trade Setup ที่มีโครงสร้างเพียงพอ",
    "E7_CONFIRMATION_INVALIDATED":"Confirmation เกิด Failure หรือถูกยกเลิก",
    "ENTRY_CONFIRMATION_NOT_PROVEN":"Setup มีอยู่ แต่ Trigger/Follow-through ยังไม่พิสูจน์ Entry",
    "TRADE_ECONOMICS_NOT_READY":"Trade Economics ยังไม่พร้อมสำหรับการเสี่ยงเงิน",
    "E8_RR_BELOW_MINIMUM":"RR ยังไม่คุ้มกับความเสี่ยง",
    "E8_STOP_TOO_WIDE":"Stop Loss กว้างเกินไปสำหรับ M5",
    "STOP_TOO_WIDE_FOR_SHORT_TERM":"Stop Loss กว้างเกินไปสำหรับการเทรดระยะสั้น",
    "INSUFFICIENT_RISK_DATA":"ข้อมูลสำหรับสร้าง Trade Plan ยังไม่เพียงพอ",
}


def _th(value: Any) -> str:
    if value is None: return "ไม่พบข้อมูล"
    if isinstance(value, bool): return "ใช่" if value else "ไม่"
    if isinstance(value, float): return f"{value:.4f}".rstrip("0").rstrip(".")
    return STATE_TH.get(str(value), str(value))


def _status(engine: Any) -> str:
    status = engine.output.get("analysis_status", "")
    return {"STRONG_EVIDENCE":"🟢 หลักฐานแข็งแรง","PARTIAL_EVIDENCE":"🟡 หลักฐานบางส่วน","WEAK_EVIDENCE":"🟠 หลักฐานอ่อน","NOT_CONFIRMED":"🟡 ยังไม่ยืนยัน","CONFIRMED":"🟢 ยืนยันแล้ว","ECONOMICS_READY":"🟢 Economics พร้อมประเมิน","ECONOMICS_UNAVAILABLE":"🟡 Economics ยังประเมินไม่ได้","CONFLICT_OR_INVALID":"🔴 พบ Conflict/Invalidation"}.get(status, "🟡 วิเคราะห์แล้ว")


def _engine_line(engine: Any) -> list[str]:
    eid = engine.engine_id; r = engine.output.get("professional_reasoning", {}) or {}
    lines = [f"{eid} — {ENGINE_THAI_NAMES.get(eid, eid)}", _status(engine)]
    if eid == "E1":
        lines += [f"• คำตอบ: Market State = {_th(r.get('market_state'))}", f"• Bias: {_th(r.get('direction_bias'))}"]
    elif eid == "E2":
        lines += [f"• คำตอบ: Regime = {_th(r.get('regime'))}", f"• Playbook: {_th(r.get('regime'))}", f"• Bias ที่ใช้วางบริบท: {_th(r.get('preferred_direction'))}"]
    elif eid == "E3":
        lines += [f"• คำตอบ: Structure = {_th(r.get('structure'))}", f"• Structure Bias: {_th(r.get('structure_direction'))}", f"• Alignment: {_th(r.get('alignment'))}"]
    elif eid == "E4":
        lines += [f"• คำตอบ: Liquidity Quality = {_th(r.get('liquidity_quality'))}", f"• Sweep: {_th(r.get('sweep'))}", f"• Reclaim: {_th(r.get('reclaim'))}"]
    elif eid == "E5":
        lines += [f"• คำตอบ: Location Quality = {_th(r.get('location_quality'))}", f"• Extension: {_th(r.get('extension'))}", f"• Space: {_th(r.get('space'))}"]
    elif eid == "E6":
        lines += [f"• คำตอบ: Setup = {_th(r.get('setup_type'))}", f"• Setup Bias: {_th(r.get('direction'))}", f"• Formation: {_th(r.get('formation'))}", f"• Quality: {_th(r.get('setup_quality'))}"]
    elif eid == "E7":
        lines += [f"• คำตอบ: Trigger = {_th(r.get('trigger'))}", f"• Trigger Quality: {_th(r.get('trigger_quality'))}", f"• Follow-through: {_th(r.get('follow_through'))}", f"• Confirmation: {_th(r.get('confirmation'))}"]
    elif eid == "E8":
        p = r.get("trade_plan") or {}; lines += [f"• คำตอบ: Risk Gate = {_th(r.get('risk_gate'))}"]
        if p.get("valid"): lines += [f"• Entry: {p.get('entry')}", f"• Stop Loss: {p.get('stop_loss')}", f"• Take Profit 2: {p.get('take_profit_2')}", f"• RR: 1:{float(p.get('rr_tp2',0)):.1f}"]
        else: lines.append(f"• Trade Plan: {_th(p.get('reason'))}")
    elif eid == "E9":
        lines += ["• คำตอบ: NO_TRADE", f"• Evidence Score: {float(engine.output.get('evidence_score', engine.score)):.1f}"]
    conclusion = r.get("specialist_conclusion")
    if conclusion: lines.append(f"• สรุปของ Engine: {conclusion}")
    return lines


def _main_reason(result: Any) -> str:
    reasons = result.risk.get("decision_reasons") or result.reason_codes or ()
    for code in reasons:
        if code in REASON_TH: return REASON_TH[code]
    return "จากหลักฐานทั้งหมด E9 ยังไม่พบจังหวะที่มี Edge เพียงพอสำหรับเปิด Position"


def format_no_trade(results: dict[str, Any], notified_at: datetime | None = None) -> str:
    now = notified_at or datetime.now(BANGKOK_TZ)
    lines = ["🟡 รอบนี้ยังไม่มีการออกออเดอร์", "", "⚙️ ระบบ: PRODUCTION-V2", "🧠 โครงสร้าง: E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9", "⏱ Timeframe: M5", f"🚨 เวลาแจ้งเตือน: {now:%d/%m/%Y %H:%M}:00 (ประเทศไทย)"]
    for symbol, result in results.items():
        lines += ["", "━━━━━━━━━━━━━━━━━━", f"📊 {symbol}", "━━━━━━━━━━━━━━━━━━"]
        for engine in getattr(result, "engines", ()):
            lines += [""] + _engine_line(engine)
        lines += ["", "🎯 ผลการตัดสินใจของ E9:", "⛔ NO_TRADE", f"เหตุผลหลัก: {_main_reason(result)}", "🔄 แท่ง M5 ปิดถัดไปจะเริ่มวิเคราะห์ E1 ใหม่ทั้งชุด"]
    lines += ["", "━━━━━━━━━━━━━━━━━━", "✅ ระบบยังทำงานตามปกติ", "📌 ทุก Engine วิเคราะห์ใหม่ทุกแท่ง M5 ที่ปิด และไม่มีการนำผลรอบก่อนมาบังคับรอบใหม่"]
    return "\n".join(lines)


def send_no_trade(results: dict[str, Any], notified_at: datetime | None = None) -> bool:
    return send(format_no_trade(results, notified_at))
