# 3C — BREAK OF STRUCTURE

## 1. INPUT
3A/3B confirmed swings and closed-candle price evidence.

## 2. PROCESSING
Detect causal breaks of validated structural levels; classify break event without treating it as liquidity sweep.

## 3. OUTPUT
BOS event, broken level, direction, confirmation status, confidence, reasons.

## 4. GATE
BLOCK when the broken reference is unconfirmed or current candle is not valid for confirmation.

## 5. SCORE
BOS quality 0–100; evidence only.

## 6. TRACEABILITY
Record reference swing, break candle, close, rules/version, score, gate.

**DECISION BOUNDARY:** structural event only.