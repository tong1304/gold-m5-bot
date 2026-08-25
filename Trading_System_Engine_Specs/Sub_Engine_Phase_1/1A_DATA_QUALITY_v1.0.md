# 1A Data Quality

## 1. INPUT
- Closed OHLCV candles, timestamp, symbol, timeframe, provider status.
- Upstream market-data metadata only.

## 2. PROCESSING
- Validate required fields, ordering, continuity, duplicates, stale timestamps and impossible OHLC relationships.
- Classify data as VALID, DEGRADED or INVALID.

## 3. OUTPUT
- `data_state`, validation flags, missing/duplicate counts, reason codes.

## 4. GATE
- FAIL when mandatory fields are missing, candle ordering is invalid, or data is stale beyond the configured policy.
- Gate only reports data usability; it never creates a trade decision.

## 5. SCORE
- Optional quality score 0-100 based on completeness, continuity and freshness.
- Score cannot override a hard invalid gate.

## 6. TRACEABILITY
- Record symbol, timeframe, candle timestamp, input version, validation ruleset, outputs and reason codes.