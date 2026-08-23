import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import replay_signal_history as replay


class ReplayLSERequestTests(unittest.TestCase):
    def test_lse_candles_request_uses_date_only_and_supported_signature(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def candles(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                return [{
                    "datetime": "2026-08-01T00:00:00Z",
                    "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 1,
                }]

        fake = FakeClient()
        with patch.dict("os.environ", {"LSE_API_KEY": "test-key"}), patch("lse.LSE", return_value=fake):
            frame = replay._fetch_lse(
                "BTC/USD",
                datetime(2026, 7, 31, 17, tzinfo=timezone.utc),
                datetime(2026, 8, 2, 17, tzinfo=timezone.utc),
                "5m",
                7,
            )

        self.assertFalse(frame.empty)
        self.assertEqual(len(fake.calls), 1)
        args, kwargs = fake.calls[0]
        self.assertEqual(args, ("BTC/USD", "5m"))
        self.assertEqual(kwargs["start"], "2026-07-31")
        self.assertEqual(kwargs["end"], "2026-08-02")
        self.assertNotIn("as_dataframe", kwargs)


if __name__ == "__main__":
    unittest.main()
