# LSE fresh-data guard

The live scanner pins BTC to the `crypto` dataset and GOLD to the `commodity` dataset. Historical candle requests are bounded to a recent UTC window and use descending order. The scanner rejects empty, malformed, future, or stale closed-candle data before the signal engine runs.

Expected logs include `LSE QUERY`, `LSE RAW DATA`, `DATA CHECK`, and `Latest closed M5 candle`.

A stale or unavailable recent feed is recorded as a data-invalid `NO_TRADE`; it is not treated as a valid market setup.
