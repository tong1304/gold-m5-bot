# 4D — ACCEPTANCE

## 1. INPUT
Liquidity zones and closed-candle price/volume evidence where permitted.

## 2. PROCESSING
Determine whether price remains accepted beyond/within a reference zone according to persistence rules.

## 3. OUTPUT
Acceptance state, persistence evidence, confidence, reasons.

## 4. GATE
BLOCK when reference zone or persistence history is insufficient.

## 5. SCORE
Acceptance quality 0–100; evidence only.

## 6. TRACEABILITY
Record reference, candles, persistence rules/version, score, gate, timestamp.

**DECISION BOUNDARY:** acceptance classification only.