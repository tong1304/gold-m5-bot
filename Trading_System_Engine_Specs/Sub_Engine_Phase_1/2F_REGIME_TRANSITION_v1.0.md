# 2F Regime Transition

## 1. INPUT
- Current/prior regime states, Engine 1 transition output and recent volatility evidence.

## 2. PROCESSING
- Detect confirmed regime change versus temporary noise.

## 3. OUTPUT
- Transition state, from/to regimes, confirmation evidence and confidence.

## 4. GATE
- FAIL when state history is incomplete or invalid.
- Does not select a trade.

## 5. SCORE
- 0-100 transition-quality score based on persistence and independent supporting evidence.

## 6. TRACEABILITY
- Record from/to states, confirmation window, versions, timestamp and reason codes.