from types import SimpleNamespace

from production_v2.service import LiveService


def test_e8_runtime_reasoning_uses_trade_economics_role():
    engine = SimpleNamespace(
        engine_id="E8",
        output={},
        reason_codes=[],
    )

    reasoning = LiveService._reasoning(engine)

    assert reasoning["role"] == "TRADE_ECONOMICS_RISK"
