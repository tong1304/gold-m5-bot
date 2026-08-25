# 5B — STRUCTURAL LOCATION

## 1. INPUT
E3 structure levels/hierarchy and current price.

## 2. PROCESSING
Classify current price relative to validated structural levels without creating a trade thesis.

## 3. OUTPUT
Structural-location state, references, distance, confidence, reasons.

## 4. GATE
BLOCK when structural references are invalid/stale.

## 5. SCORE
Location quality 0–100; evidence only.

## 6. TRACEABILITY
Record level IDs, source candles, upstream versions, timestamp, score, gate.

**DECISION BOUNDARY:** location analysis only.