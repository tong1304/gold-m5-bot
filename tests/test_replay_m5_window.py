import unittest
from v11.replay_m5 import normalize_replay_window


class ReplayM5WindowTests(unittest.TestCase):
    def test_thai_requested_window_is_inclusive_by_end_date(self):
        start, end = normalize_replay_window("2026-08-21", "2026-08-24")
        self.assertEqual(str(start), "2026-08-21 00:00:00+00:00")
        self.assertEqual(str(end), "2026-08-25 00:00:00+00:00")

    def test_end_must_be_after_start(self):
        with self.assertRaises(ValueError):
            normalize_replay_window("2026-08-24", "2026-08-21")


if __name__ == "__main__":
    unittest.main()
