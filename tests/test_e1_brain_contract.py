from production_v2.e1_brain import analyze_e1
from production_v2.notifications.telegram import _engine_answer
from production_v2.contracts import EngineResult


def _bars(n=80, step=0.5):
    bars = []
    price = 100.0
    for _ in range(n):
        close = price + step
        bars.append({"open": price, "high": close + 0.2, "low": price - 0.1, "close": close})
        price = close
    return bars


def test_e1_answers_market_state_without_trade_direction():
    result = analyze_e1(_bars())
    assert result["question"] == "What is the market doing right now?"
    assert result["market_state"] in {"TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"}
    assert result["trade_decision_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"
    assert "direction" not in result
    assert "BUY" not in str(result["professional_reasoning"])
    assert "SELL" not in str(result["professional_reasoning"])


def test_e1_telegram_answer_reports_state_not_missing_direction():
    result = analyze_e1(_bars())
    engine = EngineResult("E1", "Market State Brain", None, result["confidence"] * 100, result, ())
    answer = _engine_answer(engine)
    assert "E1 — สภาวะตลาด" in answer
    assert "ไม่พบข้อมูล" not in answer
    assert result["market_state"] in answer
    assert "BUY" not in answer
    assert "SELL" not in answer
