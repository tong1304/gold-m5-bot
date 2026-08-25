# ENGINE 01 — MARKET STATE ENGINE v1.0

## PURPOSE
Classify current market state before downstream analysis.

## SUB-ENGINES
1A Data Quality · 1B Volatility State · 1C Trend State · 1D Range State · 1E Compression · 1F Expansion · 1G Transition

## INPUT
OHLCV candles, symbol, timeframe, timestamps, permitted data-quality metadata.

## PROCESSING
Evaluate data integrity and classify volatility, trend, range, compression, expansion, and transition states without issuing trade decisions.

## OUTPUT
Market-state classification, evidence, quality/confidence, reason codes, state metadata.

## GATE
Block downstream interpretation when required data is missing, stale, malformed, or inconsistent.

## SCORE
Quality scores are evidence only and cannot override hard gates or create a trade decision.

## TRACEABILITY
Record symbol, timeframe, candle-close timestamp, input/version identifiers, outputs, gate status, scores, confidence, reason codes.

## DECISION BOUNDARY
Classification only; no BUY/SELL, entry, position-size, or execution decision.