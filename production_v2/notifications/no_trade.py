from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .telegram import ENGINE_THAI_NAMES, _e9_control_lines, _engine_answer, send

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")
REASON_TH = {
    "E1_DATA_INVALID": "ข้อมูลตลาดไม่สมบูรณ์",
    "E3_STRUCTURE_INVALIDATED": "โครงสร้างราคาถูกทำลาย",
    "E5_LOCATION_DISADVANTAGED": "Location ไม่ได้เปรียบ",
    "E5_SPACE_INSUFFICIENT": "พื้นที่เป้าหมายไม่เพียงพอ",
    "E6_SETUP_INVALIDATED": "Trade Setup ถูกทำลาย",
    "E6_NO_VALID_SETUP": "ยังไม่พบ Trade Setup ที่ชัดเจน",
    "E7_CONFIRMATION_INVALIDATED": "Confirmation ไม่ผ่าน",
    "ENTRY_CONFIRMATION_NOT_PROVEN": "Trigger/Follow-through ยังไม่ยืนยัน Entry",
    "TRADE_ECONOMICS_NOT_READY": "Trade Economics ยังไม่พร้อม",
    "E8_RR_BELOW_MINIMUM": "RR ไม่คุ้มความเสี่ยง",
    "E8_STOP_TOO_WIDE": "Stop Loss กว้างเกินไป",
    "STOP_TOO_WIDE_FOR_SHORT_TERM": "Stop Loss กว้างเกินไปสำหรับ M5",
    "INSUFFICIENT_RISK_DATA": "ข้อมูล Risk ยังไม่เพียงพอ",
}


def _main_reason(result: Any) -> str:
    reasons = list(getattr(result, "risk", {}).get("decision_reasons") or getattr(result, "reason_codes", ()) or ())
    e9 = next((e for e in _engines(result) if getattr(e, "engine_id", None) == "E9"), None)
    if e9 is not None:
        output = getattr(e9, "output", {}) or {}
        reasons.extend(output.get("decision_reasons") or getattr(e9, "reason_codes", ()) or ())
    for code in reasons:
        if code in REASON_TH:
            return REASON_TH[code]
    return str(reasons[0]) if reasons else "หลักฐานยังไม่เพียงพอสำหรับเปิด Position"


def _engines(result: Any) -> list[Any]:
    """Return the complete E1-E9 engine set without losing data during serialization."""
    engines = getattr(result, "engines", None)
    if engines:
        return list(engines)

    # Defensive fallback for callers that pass an as_dict()/JSON-shaped result.
    if isinstance(result, dict):
        raw = result.get("engines") or result.get("engine_results") or []
        return list(raw) if isinstance(raw, (list, tuple)) else []

    try:
        payload = result.as_dict()
        raw = payload.get("engines") or []
        return list(raw) if isinstance(raw, (list, tuple)) else []
    except Exception:
        return []


def _engine_answer_safe(engine: Any, expected_id: str) -> str:
    """Render one engine even if a connector/serialization layer changed its type."""
    if hasattr(engine, "engine_id"):
        return _engine_answer(engine)

    if isinstance(engine, dict):
        # Reconstruct only the small EngineResult-like surface consumed by the
        # existing formatter. This preserves the actual engine payload instead
        # of replacing it with 'ไม่พบข้อมูล'.
        class _EngineView:
            pass
        view = _EngineView()
        view.engine_id = str(engine.get("engine_id") or engine.get("id") or expected_id)
        view.output = engine.get("output") if isinstance(engine.get("output"), dict) else engine
        view.reason_codes = tuple(engine.get("reason_codes") or engine.get("reasons") or ())
        view.gate_passed = engine.get("gate_passed")
        return _engine_answer(view)

    class _EmptyEngineView:
        pass
    view = _EmptyEngineView()
    view.engine_id = expected_id
    view.output = {}
    view.reason_codes = ()
    view.gate_passed = False
    return _engine_answer(view)


def format_no_trade(results: dict[str, Any], notified_at: datetime | None = None) -> str:
    now = notified_at or datetime.now(BANGKOK_TZ)
    lines = [
        "🚫 ยังไม่มีการออกออเดอร์",
        "",
        "⚙️ ระบบ PRODUCTION-V2",
        "🧠 E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9",
        "⏱ Timeframe: M5",
        f"🚨 เวลาแจ้งเตือน: {now:%d/%m/%Y %H:%M} (ประเทศไทย)",
    ]

    for symbol, result in results.items():
        lines += ["", "━━━━━━━━━━━━━━━━━━", f"📊 {symbol}", "━━━━━━━━━━━━━━━━━━"]
        engines_by_id = {getattr(e, "engine_id", None): e for e in _engines(result)}
        if not engines_by_id and isinstance(result, dict):
            raw = result.get("engines") or result.get("engine_results") or []
            engines_by_id = {
                str(e.get("engine_id") or e.get("id")): e
                for e in raw
                if isinstance(e, dict)
            }

        # Telegram must always expose all nine brains in canonical order.
        # Missing data is reported explicitly, but a real engine payload is
        # never discarded merely because its container type changed.
        for engine_id in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"):
            engine = engines_by_id.get(engine_id)
            if engine is None:
                lines += [
                    "",
                    f"🟡 {engine_id} — {ENGINE_THAI_NAMES[engine_id]}",
                    "คำตอบ: ANALYSIS_DATA_MISSING",
                    "เหตุผล: ENGINE_RESULT_NOT_AVAILABLE_IN_NOTIFICATION_PAYLOAD",
                ]
            else:
                lines += ["", _engine_answer_safe(engine, engine_id)]

        # E9 remains the sole final authority; its market-control synthesis is
        # part of the same notification, not a separate/legacy alert.
        lines += _e9_control_lines(result)
        lines += [
            "",
            "━━━━━━━━━━━━━━━━━━",
            "🎯 FINAL DECISION",
            "━━━━━━━━━━━━━━━━━━",
            "⛔ NO_TRADE",
            f"เหตุผลหลัก: {_main_reason(result)}",
        ]

    lines += [
        "",
        "🔄 แท่ง M5 ปิดถัดไปจะวิเคราะห์ใหม่ตั้งแต่ E1",
        "📌 ไม่มี WAIT และผลรอบก่อนไม่ถูกนำมาบังคับรอบใหม่",
        "📌 E9 เท่านั้นเป็น Final Decision Authority",
    ]
    return "\n".join(lines)


def send_no_trade(results: dict[str, Any], notified_at: datetime | None = None) -> bool:
    return send(format_no_trade(results, notified_at))
