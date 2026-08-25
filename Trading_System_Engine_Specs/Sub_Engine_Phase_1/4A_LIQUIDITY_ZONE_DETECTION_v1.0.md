# 4A — LIQUIDITY ZONE DETECTION

## 1. INPUT
Validated structure, price history, permitted swing/equal-high-low evidence.

## 2. PROCESSING
Identify candidate liquidity pools/zones from observable price clustering and structural references.

## 3. OUTPUT
Zone IDs, type, price bounds, evidence, quality/confidence.

## 4. GATE
BLOCK when zone evidence is insufficient or stale.

## 5. SCORE
Zone quality 0–100; evidence only.

## 6. TRACEABILITY
Record source candles, zone rules/version, timestamp, score, gate.

**DECISION BOUNDARY:** liquidity location only.