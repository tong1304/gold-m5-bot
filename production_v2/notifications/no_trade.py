from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .telegram import ENGINE_THAI_NAMES, _e9_control_lines, _engine_answer, send

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")
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


def _main_reason(result: Any) -> str:
    reasons = list(result.risk.get("decision_reasons") or result.reason_codes or ())
    e9 = next((e for e in getattr(result, "engines", ()) if e.engine_id == "E9"), None)
    if e9 is not None:
        reasons.extend(e9.output.get("decision_reasons") or e9.reason_codes or ())
    for code in reasons:
        if code in REASON_TH: return REASON_TH[code]
    return str(reasons[0]) if reasons else "หลักฐานยังไม่เพียงพอสำหรับเปิด Position"


def format_no_trade(results: dict[str, Any], notified_at: datetime | None = None) -> str:
    now = notified_at or datetime.now(BANGKOK_TZ)
    lines = [
        "🚫 ยังไม่มีการออกออเดอร์", "", "⚙️ ระบบ PRODUCTION-V2",
        "🧠 E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9",
        "⏱ Timeframe: M5", f"🚨 เวลาแจ้งเตือน: {now:%d/%m/%Y %H:%M} (ประเทศไทย)",
    ]
    for symbol, result in results.items():
        lines += ["", "━━━━━━━━━━━━━━━━━━", f"📊 {symbol}", "━━━━━━━━━━━━━━━━━━"]
        engines = getattr(result, "engines", ())
        for engine in engines:
            lines += ["", _engine_answer(engine)]
        lines += _e9_control_lines(result)
        lines += [
            "", "━━━━━━━━━━━━━━━━━━", "🎯 FINAL DECISION",
            "━━━━━━━━━━━━━━━━━━", "⛔ NO_TRADE",
            f"เหตุผลหลัก: {_main_reason(result)}",
        ]
    lines += [
        "", "🔄 แท่ง M5 ปิดถัดไปจะวิเคราะห์ใหม่ตั้งแต่ E1",
        "📌 ไม่มี WAIT และผลรอบก่อนไม่ถูกนำมาบังคับรอบใหม่",
        "📌 E9 เท่านั้นเป็น Final Decision Authority",
    ]
    return "\n".join(lines)


def send_no_trade(results: dict[str, Any], notified_at: datetime | None = None) -> bool:
    return send(format_no_trade(results, notified_at))
