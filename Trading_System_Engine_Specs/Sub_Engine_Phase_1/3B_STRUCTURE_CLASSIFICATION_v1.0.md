# 3B Structure Classification

## 1. INPUT
- Confirmed swing sequence from 3A and closed prices.

## 2. PROCESSING
- Classify structural sequence as HH/HL, LH/LL, mixed or neutral according to the locked structure rules.

## 3. OUTPUT
- Structure class, sequence evidence, strength and confidence.

## 4. GATE
- FAIL when confirmed swings are insufficient or internally inconsistent.

## 5. SCORE
- 0-100 structure-quality score based on sequence clarity and recency.

## 6. TRACEABILITY
- Store swing IDs, classification ruleset, timestamp, output, score and reason codes.