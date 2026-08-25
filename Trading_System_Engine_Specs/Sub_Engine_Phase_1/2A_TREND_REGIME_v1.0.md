# 2A Trend Regime

## 1. INPUT
- Engine 1 trend/volatility state outputs and permitted closed-candle context.

## 2. PROCESSING
- Determine whether directional behavior is sufficiently persistent to classify a TREND regime.
- Separate directional regime from entry direction.

## 3. OUTPUT
- Regime state, supporting evidence, quality and confidence.

## 4. GATE
- FAIL when upstream state data is invalid or contradictory beyond the regime contract.

## 5. SCORE
- 0-100 regime-quality score from persistence, alignment and stability.

## 6. TRACEABILITY
- Record upstream versions, state inputs, timestamp, regime result and reason codes.