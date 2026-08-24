import unittest

import scheduler_v11


class V121MTFSchedulerTests(unittest.TestCase):
    def test_scheduler_declares_v121_mtf_mode(self):
        self.assertEqual(scheduler_v11.ENGINE_VERSION, "12.1-MTF-H1-M15-M5-REGIME-8-ENGINE-REENTRY")

    def test_scheduler_exposes_h1_m15_m5_timeframes(self):
        status = scheduler_v11.status()
        self.assertEqual(status["timeframes"], ["H1", "M15", "M5"])
        self.assertEqual(status["timeframe_mode"], "MTF:H1→M15→M5")
        self.assertEqual(status["timezone"], "Asia/Bangkok")

    def test_scheduler_scan_cycle_log_mode_is_mtf(self):
        # The runtime scanner is MTF; this guards against the scheduler regressing
        # to the old M5-only mode label/metadata.
        self.assertNotEqual(scheduler_v11.ENGINE_VERSION, "12.1-M5-ONLY-REGIME-8-ENGINE-REENTRY")


if __name__ == "__main__":
    unittest.main()
