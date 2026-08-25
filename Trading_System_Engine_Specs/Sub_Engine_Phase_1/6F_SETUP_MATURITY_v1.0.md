# 6F — SETUP MATURITY

## 1. INPUT
6C state history, setup events, elapsed closed candles.

## 2. PROCESSING
Classify setup maturity/progression without converting maturity into an entry decision.

## 3. OUTPUT
Maturity state, elapsed state evidence, confidence, reasons.

## 4. GATE
BLOCK when state history is incomplete or contradictory.

## 5. SCORE
Maturity quality 0–100; evidence only.

## 6. TRACEABILITY
Record setup ID, state history, candle references, version, score, gate.

**DECISION BOUNDARY:** maturity only.