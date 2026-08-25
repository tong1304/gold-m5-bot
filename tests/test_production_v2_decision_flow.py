from production_v2.pipeline import ProductionPipeline
from production_v2.notifications.telegram import format_decision


def bars(n=40):
    rows = []
    price = 100.0
    for i in range(n):
        close = price + 0.5
        rows.append({"open": price, "high": close + 0.2, "low": price - 0.2, "close": close})
        price = close
    return rows


def test_e1_to_e9_preserves_trade_plan():
    result = ProductionPipeline().run({
        "symbol": "BTC/USD",
        "timeframe": "M5",
        "bars": bars(),
        "candle_close_timestamp": "2026-08-25T16:00:00+00:00",
    })

    assert [e.engine_id for e in result.engines] == ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"]
    assert result.decision == "BUY"
    assert result.gate_passed is True
    plan = result.trade_plan
    assert plan["valid"] is True
    assert plan["entry"] > plan["stop_loss"]
    assert plan["take_profit_2"] > plan["take_profit_1"] > plan["entry"]
    assert plan["rr_tp2"] == 2.0


def test_telegram_requires_complete_actionable_trade_plan():
    result = ProductionPipeline().run({
        "symbol": "BTC/USD",
        "timeframe": "M5",
        "bars": bars(),
    })
    text = format_decision(result)
    assert "💵 จุดเข้า:" in text
    assert "🛑 Stop Loss:" in text
    assert "🎯 Take Profit 1:" in text
    assert "🎯 Take Profit 2:" in text
    assert "📐 RR: 1:2.0" in text
