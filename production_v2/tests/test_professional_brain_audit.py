from production_v2.professional_brain_audit import audit_all
from production_v2.shared_market_picture import attach_brain_view, build_shared_market_picture


def _closed_bars(count=60):
    return [
        {
            "timestamp": f"2026-09-01T00:{i:02d}:00Z",
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.5 + i,
            "is_closed": True,
        }
        for i in range(count)
    ]


def test_audit_all_uses_shared_audit_violating_brains_field():
    shared = build_shared_market_picture(
        {
            "symbol": "TEST",
            "timeframe": "M5",
            "bars": _closed_bars(),
            "closed_candle_only": True,
            "lookahead_allowed": False,
        }
    )
    outputs = {
        engine_id: attach_brain_view(engine_id, {}, shared)
        for engine_id in (f"E{i}" for i in range(1, 10))
    }

    result = audit_all(outputs)

    assert result["shared_market_picture_contract"]["passed"] is True
    for engine_id in outputs:
        assert result["per_engine"][engine_id]["shared_market_picture_contract"]["passed"] is True
