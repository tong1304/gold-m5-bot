# 1A — DATA QUALITY

## 1. INPUT
OHLCV candles, timestamps, symbol, timeframe, provider metadata.

## 2. PROCESSING
Validate completeness, ordering, freshness, OHLC consistency, duplicate/missing candles, and required fields. No future data.

## 3. OUTPUT
Data-quality state, defects, quality/confidence, reason codes, validation timestamp.

## 4. GATE
FAIL/BLOCK when required data is missing, stale, malformed, duplicated, or inconsistent.

## 5. SCORE
Quality score 0–100 is evidence only. It cannot override a hard gate or create a trade decision.

## 6. TRACEABILITY
Record symbol, timeframe, candle-close time, source/version, validation rules, defects, score, gate result, reason codes.

**DECISION BOUNDARY:** data validation only; no BUY/SELL or execution decision.