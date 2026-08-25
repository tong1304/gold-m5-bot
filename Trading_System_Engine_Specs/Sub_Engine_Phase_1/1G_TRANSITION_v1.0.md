# 1G Transition

## 1. INPUT
- Recent outputs from volatility, trend, range, compression and expansion sub-engines.

## 2. PROCESSING
- Detect meaningful state changes and disagreement between current and prior market-state classifications.
- Classify STABLE, TRANSITION or UNCERTAIN.

## 3. OUTPUT
- Transition state, changed dimensions, direction-neutral evidence and confidence.

## 4. GATE
- FAIL only when required prior/current states are unavailable or inconsistent.
- Never creates an entry decision.

## 5. SCORE
- 0-100 transition-quality score based on persistence and evidence consistency.

## 6. TRACEABILITY
- Record prior/current states, timestamps, changed fields, score and reason codes.