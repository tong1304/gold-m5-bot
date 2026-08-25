from production_v2.contracts import DecisionResult, EngineResult
from production_v2.notifications.telegram import format_decision, format_startup


def test_telegram_uses_only_nine_engine_architecture():
    result = DecisionResult("GOLD", "M5", "BUY", True, 82.0, (
        EngineResult("E9", "Execution Decision Engine", True, 82.0, {"decision": "BUY"}),
    ), {"risk_gate": True})
    text = format_decision(result)
    assert "E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9" in text
    assert "Decision Authority: E9" in text
    for forbidden in ("V11", "V12", "12.11", "CROSS-ASSET-FALLBACK", "H1 → M15 → M5", "B1-B3", "G1-G3"):
        assert forbidden not in text


def test_startup_declares_legacy_runtime_disabled():
    text = format_startup(["GOLD", "BTC"])
    assert "Legacy Runtime: DISABLED" in text
    assert "E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9" in text
