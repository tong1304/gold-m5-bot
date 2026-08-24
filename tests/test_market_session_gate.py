from datetime import datetime, timezone

import scheduler_v11


def test_gold_closed_session_is_marked_closed():
    opened, session = scheduler_v11._asset_market_status(
        "GOLD", datetime(2026, 8, 24, 22, 30, tzinfo=timezone.utc)
    )
    assert opened is False
    assert session == "DAILY_BREAK"


def test_gold_open_session_is_marked_open():
    opened, session = scheduler_v11._asset_market_status(
        "GOLD", datetime(2026, 8, 24, 21, 30, tzinfo=timezone.utc)
    )
    assert opened is True
    assert session == "OPEN"


def test_btc_is_open_24_7():
    opened, session = scheduler_v11._asset_market_status(
        "BTC", datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
    )
    assert opened is True
    assert session == "OPEN_24_7"
