from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .telegram import ENGINE_THAI_NAMES, send

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")
STATE_TH = {"UP":"ขาขึ้น","DOWN":"ขาลง","BULLISH":"ขาขึ้น","BEARISH":"ขาลง","NEUTRAL":"เป็นกลาง","TREND":"Trend","RANGE":"Range","TRANSITION":"Transition","EXPANSION":"Expansion","COMPRESSION":"Compression","VALID":"ข้อมูลใช้ได้","MATURE":"สมบูรณ์","INVALIDATED":"ถูกยกเลิก","TRIGGER_OBSERVED":"พบ Trigger","QUALITY_PASS":"คุณภาพผ่าน","FOLLOW_THROUGH_OBSERVED":"มี Follow-through","CONFIRMATION_PASS":"ยืนยันผ่าน","FAILURE":"Failure","UNKNOWN":"ยังไม่ชัดเจน","NON_DOMINANT":"NON_DOMINANT","QUALITY_MEASURABLE":"QUALITY_MEASURABLE","NO_SWEEP":"ไม่มี Sweep","NO_RECLAIM":"ไม่มี Reclaim","LOCATION_QUALITY_PASS":"PASS","LOCATION_QUALITY_FAIL":"FAIL","NOT_EXTENDED":"NOT_EXTENDED","EXTENDED":"EXTENDED","SPACE_AVAILABLE":"SPACE_AVAILABLE","LIMITED_SPACE":"SPACE_LIMITED","SETUP_FORMING":"FORMING","QUALITY_WEAK":"WEAK","NO_TRIGGER":"NO_TRIGGER","NO_FOLLOW_THROUGH":"NO_FOLLOW_THROUGH","CONFIRMATION_WAIT":"ยังไม่ยืนยัน"}
REASON_TH = {
    "E1_DATA_INVALID":"ข้อมูลตลาดไม่สมบูรณ์",
    "E3_STRUCTURE_INVALIDATED":"โครงสร้างราคาถูกทำลาย",
    "E5_LOCATION_DISADVANTAGED":"Location ไม่ได้เปรียบ",
    "E5_SPACE_INSUFFICIENT":"พื้นที่เป้าหมายไม่เพียงพอ",
    "E6_SETUP_INVALIDATED":"Trade Setup ถูกทำลาย",
    "E6_NO_VALID_SETUP":"ยังไม่พบ Trade Setup ที่ชัดเจน",
    "E7_CONFIRMATION_INVALIDATED":"Confirmation ไม่ผ่าน",
    "ENTRY_CONFIRMATION_NOT_PROVEN":"Trigger/Follow-through ยังไม่ยืนยัน Entry",
    "TRADE_ECONOMICS_NOT_READY":"Trade Economics ยังไม่พร้อม",
    "E8_RR_BELOW_MINIMUM":"RR ไม่คุ้มความเสี่ยง",
    "E8_STOP_TOO_WIDE":"Stop Loss กว้างเกินไป",
    "STOP_TOO_WIDE_FOR_SHORT_TERM":"Stop Loss กว้างเกินไปสำหรับ M5",
    "INSUFFICIENT_RISK_DATA":"ข้อมูล Risk ยังไม่เพียงพอ",
}


def _th(value: Any) -> str:
    if value is None:
        return "ไม่พบข้อมูล"
    if isinstance(value, bool):
        return "ใช่" if value else "ไม่"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return STATE_TH.get(str(value), str(value))


def _status(engine: Any) -> str:
    eid = engine.engine_id
    r = engine.output.get("professional_reasoning", {}) or {}
    status = engine.output.get("analysis_status", "")
    reasons = set(engine.output.get("analysis_reason_codes", ()) or engine.reason_codes or ())
    if eid == "E9":
        return "🟢" if engine.output.get("decision") in {"BUY", "SELL"} else "🔴"
    if eid == "E5" and (r.get("location_quality") == "LOCATION_QUALITY_FAIL" or r.get("space") == "LIMITED_SPACE"):
        return "🔴"
    if eid == "E7" and r.get("confirmation") != "CONFIRMATION_PASS":
        return "🔴"
    if eid == "E8" and not (r.get("trade_plan") or {}).get("valid"):
        return "🔴"
    if reasons & {"E1_DATA_INVALID", "E3_STRUCTURE_INVALIDATED", "E6_SETUP_INVALIDATED"}:
        return "🔴"
    return {"STRONG_EVIDENCE":"🟢","PARTIAL_EVIDENCE":"🟡","WEAK_EVIDENCE":"🟠","NOT_CONFIRMED":"🟡","CONFIRMED":"🟢","ECONOMICS_READY":"🟢","ECONOMICS_UNAVAILABLE":"🟡","CONFLICT_OR_INVALID":"🔴"}.get(status, "🟡")


def _engine_answer(engine: Any) -> str:
    eid = engine.engine_id
    r = engine.output.get("professional_reasoning", {}) or {}
    if eid == "E1": answer = f"{_th(r.get('direction_bias'))} / {_th(r.get('market_state'))}"
    elif eid == "E2": answer = f"{_th(r.get('regime'))} / {_th(r.get('preferred_direction'))}"
    elif eid == "E3": answer = f"{_th(r.get('structure'))} / {_th(r.get('alignment'))}"
    elif eid == "E4": answer = f"{_th(r.get('liquidity_quality'))} / Sweep {_th(r.get('sweep'))}"
    elif eid == "E5": answer = f"{_th(r.get('location_quality'))} / {_th(r.get('space'))}"
    elif eid == "E6": answer = f"{_th(r.get('setup_type'))} / {_th(r.get('formation'))}"
    elif eid == "E7": answer = f"{_th(r.get('trigger'))} / {_th(r.get('confirmation'))}"
    elif eid == "E8":
        p = r.get("trade_plan") or {}
        answer = f"RR 1:{float(p.get('rr_tp2', 0)):.1f}" if p.get("valid") else _th(p.get("reason"))
    elif eid == "E9": answer = str(engine.output.get("decision", "NO_TRADE"))
    else: answer = "ไม่พบข้อมูล"
    return f"{_status(engine)} {eid} — {ENGINE_THAI_NAMES.get(eid, eid)}\nคำตอบ: {answer}"


def _main_reason(result: Any) -> str:
    reasons = result.risk.get("decision_reasons") or result.reason_codes or ()
    for code in reasons:
        if code in REASON_TH:
            return REASON_TH[code]
    return "หลักฐานยังไม่เพียงพอสำหรับเปิด Position"


def format_no_trade(results: dict[str, Any], notified_at: datetime | None = None) -> str:
    now = notified_at or datetime.now(BANGKOK_TZ)
    lines = [
        "🟡 รอบนี้ยังไม่มีการออกออเดอร์", "", "⚙️ PRODUCTION-V2",
        "🧠 E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9", "⏱ M5",
        f"🚨 {now:%d/%m/%Y %H:%M} ประเทศไทย",
    ]
    for symbol, result in results.items():
        lines += ["", "━━━━━━━━━━━━━━━━━━", f"📊 {symbol}", "━━━━━━━━━━━━━━━━━━"]
        for engine in getattr(result, "engines", ()):
            lines += ["", _engine_answer(engine)]
        lines += ["", "⛔ ผลลัพธ์: ไม่ออกออเดอร์", f"เหตุผล: {_main_reason(result)}"]
    lines += ["", "━━━━━━━━━━━━━━━━━━", "🔄 แท่ง M5 ปิดถัดไปวิเคราะห์ใหม่ตั้งแต่ E1", "📌 ไม่มี WAIT และไม่ใช้ผลรอบก่อนบังคับรอบใหม่"]
    return "\n".join(lines)


def send_no_trade(results: dict[str, Any], notified_at: datetime | None = None) -> bool:
    return send(format_no_trade(results, notified_at))
