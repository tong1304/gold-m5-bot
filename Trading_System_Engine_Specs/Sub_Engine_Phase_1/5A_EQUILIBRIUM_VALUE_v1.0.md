# 5A Equilibrium / Value

## 1. INPUT
- Closed price/volume data and only approved value references such as VWAP or defined equilibrium models.

## 2. PROCESSING
- Establish the current value/equilibrium reference and price displacement from it.

## 3. OUTPUT
- Value reference, displacement state, method metadata and confidence.

## 4. GATE
- FAIL when the value model lacks sufficient valid input.

## 5. SCORE
- 0-100 value-quality score based on sample sufficiency and reference stability.

## 6. TRACEABILITY
- Record value method/version, lookback, timestamp, reference and reason codes.