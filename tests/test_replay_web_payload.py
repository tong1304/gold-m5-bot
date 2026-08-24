from replay_web import _public_state


def test_replay_status_payload_does_not_return_all_replay_rows():
    state = {
        "running": False,
        "status": "completed",
        "result": {
            "status": "completed",
            "reports": [
                {"symbol": "BTC", "performance": {"wins": 3}, "rows": [{"candle_time": "x"}] * 5000}
            ],
        },
    }

    public = _public_state(state)

    assert public["result"]["reports"][0]["performance"]["wins"] == 3
    assert "rows" not in public["result"]["reports"][0]
