# 2B Range Regime

## 1. INPUT
- Engine 1 range, volatility and trend-state outputs.

## 2. PROCESSING
- Confirm whether price behavior is bounded and directionally non-persistent enough for RANGE regime classification.

## 3. OUTPUT
- Range-regime state, evidence, quality and confidence.

## 4. GATE
- FAIL when mandatory upstream states are unavailable or invalid.
- Does not imply mean-reversion entry.

## 5. SCORE
- 0-100 regime-quality score based on containment and boundary stability.

## 6. TRACEABILITY
- Store upstream references, boundary evidence, timestamp, state and reason codes.