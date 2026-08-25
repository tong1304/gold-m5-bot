# 5F Location Quality

## 1. INPUT
- Outputs from 5A-5E and validated structural/liquidity references.

## 2. PROCESSING
- Aggregate location evidence into a context-quality classification; preserve component evidence.

## 3. OUTPUT
- Location-quality state, component scores, confidence and reason codes.

## 4. GATE
- FAIL when mandatory location components are invalid or contradictory.

## 5. SCORE
- 0-100 aggregate location score; hard invalid inputs cannot be offset by other scores.

## 6. TRACEABILITY
- Store component versions, inputs, weights/ruleset, timestamp and final score.