# 4B — SWEEP DETECTION

## 1. INPUT
4A zones, closed-candle OHLC, structure references.

## 2. PROCESSING
Detect price penetration through a liquidity zone followed by defined rejection/return evidence. Does not decide setup validity.

## 3. OUTPUT
Sweep event, zone ID, penetration/reclaim evidence, confidence, reasons.

## 4. GATE
BLOCK when target zone is unvalidated or event is incomplete.

## 5. SCORE
Sweep quality 0–100; evidence only.

## 6. TRACEABILITY
Record zone, event candle, prices, rules/version, score, gate.

**DECISION BOUNDARY:** liquidity event only.