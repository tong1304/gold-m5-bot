# 7D — FAILURE / INVALIDATION

## 1. INPUT
7A–7C trigger/confirmation state and setup validity.

## 2. PROCESSING
Detect failure of the entry trigger/confirmation conditions; do not redefine setup invalidation.

## 3. OUTPUT
Confirmation failure state, failed condition, confidence, reasons.

## 4. GATE
FAIL confirmation when defined trigger/confirmation failure occurs.

## 5. SCORE
Failure evidence quality 0–100; evidence only.

## 6. TRACEABILITY
Record trigger ID, failure candle/condition, setup version, timestamp, gate.

**DECISION BOUNDARY:** trigger/confirmation failure only; 6D owns setup validity.