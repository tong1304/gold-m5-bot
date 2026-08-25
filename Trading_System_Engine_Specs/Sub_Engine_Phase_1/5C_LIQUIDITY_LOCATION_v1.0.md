# 5C — LIQUIDITY LOCATION

## 1. INPUT
E4 liquidity zones/events and current price.

## 2. PROCESSING
Classify price proximity to relevant liquidity and whether liquidity is nearby/consumed/available.

## 3. OUTPUT
Liquidity-location state, references, distance, confidence, reasons.

## 4. GATE
BLOCK when relevant liquidity references are unavailable or stale.

## 5. SCORE
Location quality 0–100; evidence only.

## 6. TRACEABILITY
Record zone IDs, distances, event status, upstream versions, score, gate.

**DECISION BOUNDARY:** location only.