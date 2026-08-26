from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .telegram import ENGINE_THAI_NAMES, send

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")
STATE_TH = {"UP":"ขาขึ้น","DOWN":"ขาลง","BULLISH":"ขาขึ้น","BEARISH":"ขาลง","NEUTRAL":"เป็นกลาง","TREND":"Trend","RANGE":"Range","TRANSITION":"Transition","EXPANSION":"Expansion","COMPRESSION":"Compression","VALID":"ผ่าน","MATURE":"สมบูรณ์","INVALIDATED":"ถูกยกเลิก","TRIGGER_OBSERVED":"พบ Trigger","QUALITY_PASS":"คุณภาพผ่าน","FOLLOW_THROUGH_OBSERVED":"มี Follow-through","CONFIRMATION_PASS":"ยืนยันผ่าน","FAILURE":"ล้มเหลว"}
REASON_TH = {
    "E1_DATA_INVALID":"ข้อมูลตลาดไม่สมบูรณ์ จึงไม่สามารถวิเคราะห์ต่อได้",
    "E3_STRUCTURE_INVALIDATED":"โครงสร้างราคาที่ใช้เป็น Thesis ถูกทำลาย",
    "E5_LOCATION_DISADVANTAGED":"ราคาวิ่งออกจากตำแหน่งที่ได้เปรียบสำหรับการเข้าเทรด",
    "E5_SPACE_INSUFFICIENT":"พื้นที่ไปยังเป้าหมายมีจำกัดเมื่อเทียบกับความเสี่ยง",
    "E6_SETUP_INVALIDATED":"Trade Setup ถูกทำลายแล้ว",
    "E6_NO_VALID_SETUP":"จากข้อมูล E1–E5 ยังไม่พบ Trade Setup ที่มีเหตุผลเพียงพอ",
    "E7_CONFIRMATION_INVALIDATED":"Trigger ที่เกิดขึ้นถูกยกเลิกหรือเกิด Failure",
    "E7_CONFIRMATION_INSUFFICIENT":"Trade Setup มีอยู่ แต่ Trigger และ Follow-through ยังไม่ยืนยันเพียงพอ",
    "E8_RR_BELOW_MINIMUM":"RR ของแผนนี้ยังไม่คุ้มกับความเสี่ยง",
    "E8_STOP_TOO_WIDE":"จุด Invalidation อยู่ไกลเกินไปสำหรับการเทรด M5",
    "STOP_TOO_WIDE_FOR_SHORT_TERM":"ระยะ Stop Loss กว้างเกินไปสำหรับการเทรดระยะสั้น",
    "INSUFFICIENT_RISK_DATA":"ข้อมูลสำหรับสร้าง Trade Plan ยังไม่เพียงพอ",
}


def _th(value: Any) -> str:
    if value is None: return "ไม่พบข้อมูล"
    if isinstance(value, bool): return "ใช่" if value else "ไม่"
    if isinstance(value, float): return f"{value:.4f}".rstrip("0").rstrip(".")
    return STATE_TH.get(str(value), str(value))


def _reason(engine: Any) -> str:
    for code in getattr(engine, "reason_codes", ()) or ():
        if code in REASON_TH: return REASON_TH[code]
    return "ผลวิเคราะห์ของ Engine นี้ยังไม่เพียงพอที่จะสนับสนุนการส่งคำสั่ง"


def _engine_line(engine: Any) -> list[str]:
    eid = engine.engine_id; r = engine.output.get("professional_reasoning", {}) or {}; lines=[f"{eid} — {ENGINE_THAI_NAMES.get(eid, eid)}", f"{'✅' if engine.gate_passed else '❌'} {'ผ่านการวิเคราะห์' if engine.gate_passed else 'ไม่ผ่านสำหรับการส่งต่อ'}"]
    if eid=="E1": lines += [f"• Market State: {_th(r.get('market_state'))}", f"• Bias: {_th(r.get('direction_bias'))}"]
    elif eid=="E2": lines += [f"• Regime: {_th(r.get('regime'))}", f"• Playbook: {_th(r.get('regime'))}", f"• Bias: {_th(r.get('preferred_direction'))}"]
    elif eid=="E3": lines += [f"• Structure: {_th(r.get('structure'))}", f"• Direction: {_th(r.get('structure_direction'))}", f"• Alignment: {_th(r.get('alignment'))}"]
    elif eid=="E4": lines += [f"• Liquidity Quality: {_th(r.get('liquidity_quality'))}", f"• Sweep: {_th(r.get('sweep'))}", f"• Reclaim: {_th(r.get('reclaim'))}"]
    elif eid=="E5": lines += [f"• Location Quality: {_th(r.get('location_quality'))}", f"• Extension: {_th(r.get('extension'))}", f"• Space: {_th(r.get('space'))}"]
    elif eid=="E6": lines += [f"• Setup: {_th(r.get('setup_type'))}", f"• Direction: {_th(r.get('direction'))}", f"• Formation: {_th(r.get('formation'))}", f"• Quality: {_th(r.get('setup_quality'))}"]
    elif eid=="E7": lines += [f"• Trigger: {_th(r.get('trigger'))}", f"• Trigger Quality: {_th(r.get('trigger_quality'))}", f"• Follow-through: {_th(r.get('follow_through'))}", f"• Confirmation: {_th(r.get('confirmation'))}"]
    elif eid=="E8":
        p=r.get("trade_plan") or {}; lines += [f"• Risk Gate: {_th(r.get('risk_gate'))}"]
        if p.get("valid"): lines += [f"• Entry: {p.get('entry')}", f"• Stop Loss: {p.get('stop_loss')}", f"• Take Profit 2: {p.get('take_profit_2')}", f"• RR: 1:{float(p.get('rr_tp2',0)):.1f}"]
    elif eid=="E9": lines += [f"• Decision: {_th(engine.output.get('decision'))}", f"• Edge Score: {float(engine.output.get('edge_score',0)):.1f}"]
    return lines


def format_no_trade(results: dict[str, Any], notified_at: datetime | None = None) -> str:
    now=notified_at or datetime.now(BANGKOK_TZ)
    lines=["🟡 รอบนี้ยังไม่มีการออกออเดอร์","","⚙️ ระบบ: PRODUCTION-V2","🧠 โครงสร้าง: E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9","⏱ Timeframe: M5",f"🚨 เวลาแจ้งเตือน: {now:%d/%m/%Y %H:%M}:00 (ประเทศไทย)"]
    for symbol,result in results.items():
        lines += ["","━━━━━━━━━━━━━━━━━━",f"📊 {symbol}","━━━━━━━━━━━━━━━━━━"]
        for engine in getattr(result,"engines",()) : lines += [""] + _engine_line(engine)
        blocked=result.risk.get("blocked_by")
        lines += ["","🎯 ผลรอบนี้:","⛔ ไม่ส่งคำสั่งซื้อขาย",f"เหตุผลหลัก: {_reason(next((e for e in result.engines if e.engine_id==blocked), result.engines[-1])) if result.engines else 'ไม่พบผลวิเคราะห์'}"]
        lines += ["🔄 แท่ง M5 ปิดถัดไปจะเริ่ม E1 ใหม่ทั้งชุด"]
    lines += ["","━━━━━━━━━━━━━━━━━━","✅ ระบบยังทำงานตามปกติ","📌 ไม่มี WAIT และไม่มีการนำผลจากรอบก่อนมาบังคับรอบใหม่"]
    return "\n".join(lines)


def send_no_trade(results: dict[str, Any], notified_at: datetime | None = None) -> bool:
    return send(format_no_trade(results, notified_at))
