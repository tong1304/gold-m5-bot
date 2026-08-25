# 8E Position Size

## 1. INPUT
- Account-risk budget supplied by the risk policy, stop distance and instrument sizing rules.

## 2. PROCESSING
- Calculate position size from approved risk-per-trade and instrument contract/tick specifications.

## 3. OUTPUT
- Position size, risk amount, sizing method and validation status.

## 4. GATE
- FAIL when sizing inputs/specifications are missing or calculated exposure exceeds the approved risk budget.

## 5. SCORE
- No trade-quality score; expose sizing-confidence 0-100 only for input completeness.

## 6. TRACEABILITY
- Record account-risk policy version, instrument specs, inputs, calculation and timestamp.