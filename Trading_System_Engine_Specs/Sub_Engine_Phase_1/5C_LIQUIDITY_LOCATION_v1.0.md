# 5C Liquidity Location

## 1. INPUT
- Current price and validated liquidity zones from Engine 4.

## 2. PROCESSING
- Determine whether price is near, inside, between or away from meaningful liquidity zones.

## 3. OUTPUT
- Liquidity-location state, nearest zones, distances and confidence.

## 4. GATE
- FAIL when zone data is invalid or stale under policy.

## 5. SCORE
- 0-100 location-quality score from zone quality, proximity and clarity.

## 6. TRACEABILITY
- Record zone IDs, distance method, timestamp, output, score and reason codes.