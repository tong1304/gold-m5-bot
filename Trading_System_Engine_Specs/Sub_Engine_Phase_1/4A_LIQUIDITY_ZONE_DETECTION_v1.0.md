# 4A Liquidity Zone Detection

## 1. INPUT
- Confirmed highs/lows, repeated equal/similar levels and permitted price history.

## 2. PROCESSING
- Detect candidate liquidity zones created by clustered or obvious reference levels.

## 3. OUTPUT
- Zone objects, boundaries, source events, quality and confidence.

## 4. GATE
- FAIL when source structure is insufficient or zone definition is invalid.
- Zone detection is not a trade signal.

## 5. SCORE
- 0-100 zone-quality score from clustering, recency and structural relevance.

## 6. TRACEABILITY
- Store source swing IDs, zone method/version, timestamp, score and reason codes.