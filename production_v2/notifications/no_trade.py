from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .telegram import ENGINE_THAI_NAMES, send

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")

REASON_TH = {
    "E1_DIRECTION_NOT_DOMINANT": "ตลาดยังไม่มีทิศทางที่ชัดเจนมากพอ ราคายังสามารถเคลื่อนไหวได้ทั้งขึ้นและลง ระบบจึงยังไม่เลือก BUY หรือ SELL",
    "E1_NOT_VALID": "สภาพตลาดยังไม่ชัดเจนเพียงพอที่จะเลือกทิศทางการเทรด",
    "E2_REGIME_NOT_SUITABLE": "รูปแบบการเคลื่อนไหวของตลาดยังไม่เหมาะกับการเข้าเทรดในตอนนี้",
    "E2_TRANSITION": "ตลาดกำลังเปลี่ยนสภาพ ระบบจึงรอให้ทิศทางชัดเจนก่อน",
    "E3_NO_BOS": "โครงสร้างราคายังไม่ยืนยันการเดินหน้าต่อ จึงยังไม่มีหลักฐานเพียงพอสำหรับการเข้าเทรด",
    "E3_STRUCTURE_NOT_CONFIRMED": "โครงสร้างราคายังไม่ยืนยันอย่างชัดเจน จึงยังไม่เข้าเทรด",
    "E4_NO_LIQUIDITY_EVENT": "ยังไม่พบจังหวะสภาพคล่องที่เหมาะสำหรับเริ่มการเทรด",
    "E4_LIQUIDITY_NOT_CONFIRMED": "ยังไม่พบสัญญาณสภาพคล่องที่ชัดเจนพอสำหรับการเข้าเทรด",
    "E5_LIMITED_SPACE": "ราคาปัจจุบันอยู่ใกล้บริเวณสำคัญเกินไป ทำให้พื้นที่สำหรับทำกำไรมีจำกัดเมื่อเทียบกับความเสี่ยง",
    "E5_EXTENDED": "ราคาวิ่งมาไกลเกินไปแล้ว การเข้าในตอนนี้มีความเสี่ยงสูงขึ้น",
    "E5_LOCATION_NOT_VALID": "ตำแหน่งราคาปัจจุบันยังไม่เหมาะสำหรับการเปิดออเดอร์",
    "E6_NO_SETUP": "ยังไม่พบรูปแบบการเข้าเทรดที่ตรงตามเงื่อนไขของระบบ",
    "E6_SETUP_NOT_CONFIRMED": "มีแนวโน้มบางส่วน แต่ยังไม่มีรูปแบบการเข้าเทรดที่ชัดเจน",
    "E7_NO_STRONG_TRIGGER": "ยังไม่มีสัญญาณยืนยันที่แข็งแรงพอสำหรับการส่งคำสั่งซื้อขาย",
    "E7_CONFIRMATION_WEAK": "มีสัญญาณเริ่มต้นแล้ว แต่การยืนยันยังไม่เพียงพอ จึงต้องรอต่อ",
    "E8_RISK_TOO_HIGH": "จุดเข้าและจุดป้องกันการขาดทุนทำให้ความเสี่ยงสูงเกินไปเมื่อเทียบกับโอกาสทำกำไร",
    "E8_RR_TOO_LOW": "อัตราส่วนกำไรที่คาดหวังต่อความเสี่ยงยังไม่คุ้มค่าพอสำหรับการเปิดออเดอร์",
    "E8_INVALID_TRADE_PLAN": "ยังวางแผนจุดเข้า จุดตัดขาดทุน และเป้าหมายกำไรได้ไม่เหมาะสม",
    "E9_WAITING_FOR_CONFIRMATION": "ภาพรวมยังไม่ดีพอสำหรับการอนุมัติคำสั่ง ระบบจึงรอการยืนยันเพิ่มเติม",
    "E9_NOT_APPROVED": "ภาพรวมยังไม่เหมาะสมพอที่จะส่งคำสั่งซื้อขาย",
}

FALLBACK = {
    "E1": "ตลาดยังไม่มีทิศทางที่ชัดเจนมากพอ ระบบจึงยังไม่เลือก BUY หรือ SELL",
    "E2": "สภาพตลาดยังไม่เหมาะสมกับการเข้าเทรดในขณะนี้",
    "E3": "โครงสร้างราคายังไม่ยืนยันเพียงพอสำหรับการเข้าเทรด",
    "E4": "ยังไม่พบจังหวะสภาพคล่องที่เหมาะสมสำหรับการเข้าเทรด",
    "E5": "ตำแหน่งราคาปัจจุบันยังไม่เหมาะสมกับความเสี่ยงและโอกาส",
    "E6": "ยังไม่พบรูปแบบการเข้าเทรดที่ชัดเจนตามเงื่อนไขของระบบ",
    "E7": "ยังไม่มีการยืนยันที่แข็งแรงเพียงพอสำหรับการส่งคำสั่ง",
    "E8": "ความเสี่ยงของแผนการเทรดยังไม่เหมาะสม",
    "E9": "ภาพรวมยังไม่ผ่านเกณฑ์สำหรับการอนุมัติคำสั่ง",
}


def _blocked(result: Any) -> tuple[str, Any | None]:
    risk = getattr(result, "risk", None) or {}
    blocked = risk.get("blocked_by")
    engines = list(getattr(result, "engines", ()) or ())
    if blocked:
        for engine in engines:
            if str(getattr(engine, "engine_id", "")) == str(blocked):
                return str(blocked), engine
        return str(blocked), None
    for engine in engines:
        if not bool(getattr(engine, "gate_passed", False)):
            return str(getattr(engine, "engine_id", "")), engine
    return "E9", engines[-1] if engines else None


def _reason(engine_id: str, engine: Any | None) -> str:
    for code in list(getattr(engine, "reason_codes", ()) or ()):
        if code in REASON_TH:
            return REASON_TH[code]
    return FALLBACK.get(engine_id, "เงื่อนไขของระบบยังไม่ครบสำหรับการออกออเดอร์")


def format_no_trade(results: dict[str, Any], notified_at: datetime | None = None) -> str:
    now = notified_at or datetime.now(BANGKOK_TZ)
    lines = [
        "🟡 ไม่มีการออกออเดอร์", "", "⚙️ ระบบ: PRODUCTION-V2",
        "🧠 โครงสร้าง: E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9",
        "⏳Timeframe: M5", f"⏱ เวลาแจ้งเตือน: {now:%d/%m/%Y %H:%M}:00 (ประเทศไทย)",
    ]
    for symbol, result in results.items():
        upper = symbol.upper()
        icon = "🌕" if upper.startswith("GOLD") else "🪙" if upper.startswith("BTC") else "📊"
        engine_id, engine = _blocked(result)
        engine_name = ENGINE_THAI_NAMES.get(engine_id, engine_id)
        reason = _reason(engine_id, engine)
        lines += [
            "", "━━━━━━━━━━━━━━━━━━", f"{icon} {symbol}", "━━━━━━━━━━━━━━━━━━", "",
            "⛔ ยังไม่สามารถออกออเดอร์ได้", "", "🔒 ติดอยู่ที่:",
            f"{engine_id} — {engine_name}", "", "💡 เหตุผล:", reason, "",
            f"➡️ การทำงานหยุดรอที่ {engine_id}",
            "ไม่ส่งคำสั่งซื้อขายจนกว่าเงื่อนไขจะชัดเจนและผ่านการตรวจสอบ",
        ]
    lines += [
        "", "━━━━━━━━━━━━━━━━━━", "", "⛔ สรุป:",
        "รอบนี้ไม่มีออเดอร์ที่ผ่านการตรวจสอบครบ E1 → E9", "", "✅ ระบบยังทำงานปกติ",
    ]
    return "\n".join(lines)


def send_no_trade(results: dict[str, Any], notified_at: datetime | None = None) -> bool:
    return send(format_no_trade(results, notified_at))
