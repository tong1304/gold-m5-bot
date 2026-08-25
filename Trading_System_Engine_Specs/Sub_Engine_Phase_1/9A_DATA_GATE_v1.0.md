# 9A Data Gate

## 1. INPUT
- Data-quality and freshness outputs from upstream engines plus execution-data status.

## 2. PROCESSING
- Verify that all required data is valid, current and contract-compatible for final evaluation.

## 3. OUTPUT
- Data gate status, missing dependencies, freshness evidence and confidence.

## 4. GATE
- FAIL when required data is invalid, stale or unavailable.

## 5. SCORE
- 0-100 data-readiness score for diagnostics; it cannot override failure.

## 6. TRACEABILITY
- Record dependency IDs/versions, timestamp, data snapshot and reason codes.