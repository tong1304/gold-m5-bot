from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .telegram import _engine_finding, send

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
    for code in dict.fromkeys(str(x) for x in reasons if x):
        if code in REASON_TH:
            return REASON_TH[code]
    return "หลักฐานยังไม่เพียงพอสำหรับเปิด Position"


def _engines(result: Any) -> list[Any]:
    engines = getattr(result, "engines", None)
    if engines:
        return list(engines)
    if isinstance(result, dict):
        raw = result.get("engines") or result.get("engine_results") or []
        return list(raw) if isinstance(raw, (list, tuple)) else []
    try:
        raw = result.as_dict().get("engines") or []
        return list(raw) if isinstance(raw, (list, tuple)) else []
    except Exception:
        return []


def _engine_compact(engine: Any, expected_id: str) -> str:
    """Return only a bounded engine conclusion for the single NO_TRADE alert."""
    if hasattr(engine, "engine_id"):
        engine_id = str(engine.engine_id)
        finding = _engine_finding(engine)
    elif isinstance(engine, dict):
        engine_id = str(engine.get("engine_id") or engine.get("id") or expected_id)
        output = engine.get("output") if isinstance(engine.get("output"), dict) else engine

        class _EngineView:
            pass

        view = _EngineView()
        view.engine_id = engine_id
        view.output = output
        view.reason_codes = tuple(engine.get("reason_codes") or engine.get("reasons") or ())
        view.gate_passed = engine.get("gate_passed")
        finding = _engine_finding(view)
    else:
        engine_id = expected_id
        finding = "ANALYSIS_DATA_MISSING"

    finding = " ".join(str(finding).split())
    if len(finding) > 180:
        finding = finding[:177].rstrip() + "..."
    return f"{engine_id}: {finding}"


def format_no_trade(results: dict[str, Any], notified_at: datetime | None = None) -> str:
    """Build one compact NO_TRADE alert; detailed evidence stays in logs/API."""
    now = notified_at or datetime.now(BANGKOK_TZ)
    lines = [
        "🚫 NO_TRADE — ยังไม่มีการออกออเดอร์",
        "",
        "⚙️ PRODUCTION-V2 | E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9",
        "⏱ M5",
        f"🚨 {now:%d/%m/%Y %H:%M} (ประเทศไทย)",
    ]

    for symbol, result in results.items():
        lines += ["", "━━━━━━━━━━━━━━━━━━", f"📊 {symbol}", "━━━━━━━━━━━━━━━━━━"]
        engines_by_id = {getattr(e, "engine_id", None): e for e in _engines(result)}
        for engine_id in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"):
            engine = engines_by_id.get(engine_id)
            lines.append(_engine_compact(engine, engine_id) if engine is not None else f"{engine_id}: ANALYSIS_DATA_MISSING")
        lines += [
            "🎯 FINAL: NO_TRADE",
            f"เหตุผลหลัก: {_main_reason(result)}",
        ]

    lines += [
        "",
        "🔄 วิเคราะห์ใหม่เมื่อแท่ง M5 ปิดถัดไป",
        "📌 E9 เท่านั้นเป็น Final Decision Authority",
    ]
    return "\n".join(lines)


def send_no_trade(results: dict[str, Any], notified_at: datetime | None = None) -> bool:
    return send(format_no_trade(results, notified_at))
