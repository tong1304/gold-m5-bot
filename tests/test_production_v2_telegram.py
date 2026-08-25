from production_v2.contracts import DecisionResult, EngineResult
from production_v2.notifications import telegram
from production_v2.notifications.telegram import format_critical, format_decision, format_startup, format_status


def decision(decision="BUY", gate=True):
    plan = {
        "valid": gate,
        "direction": decision,
        "entry": 100.0,
        "stop_loss": 99.0,
        "take_profit_1": 101.0,
        "take_profit_2": 102.0,
        "rr_tp2": 2.0,
    }
    return DecisionResult("GOLD", "M5", decision, gate, 82.0, (
        EngineResult("E9", "Execution Decision Engine", gate, 82.0, {"decision": decision, "trade_plan": plan}),
    ), {"risk_gate": gate, "trade_plan": plan})


def test_telegram_uses_only_nine_engine_architecture():
    text = format_decision(decision())
    assert "E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9" in text
    assert "E9" in text
    for forbidden in ("V11", "V12", "12.11", "CROSS-ASSET-FALLBACK", "H1 → M15 → M5", "B1-B3", "G1-G3"):
        assert forbidden not in text


def test_startup_is_thai_first_and_declares_legacy_disabled():
    text = format_startup(["GOLD", "BTC"])
    assert "🟢 ระบบ 9-Engine เริ่มทำงาน" in text
    assert "PRODUCTION-V2" in text
    assert "Legacy Runtime" not in text
    assert "E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9" in text
    assert "GOLD" in text and "BTC" in text


def test_status_is_thai_first():
    text = format_status({"symbols": {"GOLD": "เชื่อมต่อแล้ว", "BTC": "เชื่อมต่อแล้ว"}, "timeframe": "M5"})
    assert "🟢 สถานะระบบ" in text
    assert "เชื่อมต่อแล้ว" in text
    assert "M5" in text


def test_critical_is_thai_first():
    text = format_critical("การเชื่อมต่อขัดข้อง", "LSE")
    assert "🔴 ระบบผิดปกติ" in text
    assert "LSE" in text
    assert "การเชื่อมต่อขัดข้อง" in text


def test_no_trade_is_not_sent(monkeypatch):
    sent = []
    monkeypatch.setattr(telegram, "send", lambda text: sent.append(text) or True)
    assert telegram.send_decision(decision("NO_TRADE", False)) is False
    assert sent == []


def test_trade_is_sent_only_when_e9_actionable(monkeypatch):
    sent = []
    monkeypatch.setattr(telegram, "send", lambda text: sent.append(text) or True)
    assert telegram.send_decision(decision("BUY", True)) is True
    assert len(sent) == 1
    assert "BUY" in sent[0]
