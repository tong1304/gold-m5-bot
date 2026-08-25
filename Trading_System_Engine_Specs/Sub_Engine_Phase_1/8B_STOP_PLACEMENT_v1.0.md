# 8B Stop Placement

## 1. INPUT
- Invalidation model, current price, volatility normalization and execution constraints.

## 2. PROCESSING
- Convert invalidation logic into a stop location consistent with the risk contract and minimum/maximum policy when configured.

## 3. OUTPUT
- Stop reference/price, distance, method and confidence.

## 4. GATE
- FAIL if stop cannot represent the invalidation model or violates configured safety constraints.

## 5. SCORE
- 0-100 stop-quality score from invalidation fidelity and distance reliability.

## 6. TRACEABILITY
- Record invalidation ID, stop method/version, inputs, timestamp and reason codes.