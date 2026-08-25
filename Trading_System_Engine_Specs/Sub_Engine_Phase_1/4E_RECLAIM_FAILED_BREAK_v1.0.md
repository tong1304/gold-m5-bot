# 4E — RECLAIM / FAILED BREAK

## 1. INPUT
4A zones, 4B/4D events, closed-candle evidence.

## 2. PROCESSING
Classify return/reclaim of a reference after a break and distinguish it from a completed sweep event.

## 3. OUTPUT
Reclaim/failed-break state, reference, evidence, confidence, reasons.

## 4. GATE
BLOCK when break/reference is not validated.

## 5. SCORE
Event quality 0–100; evidence only.

## 6. TRACEABILITY
Record reference ID, break/reclaim candles, rules/version, score, gate.

**DECISION BOUNDARY:** liquidity/price interaction only.