# 8G Risk Gate

## 1. INPUT
- Invalidation, stop, target/R, position-size and exposure-limit outputs from 8A-8F.

## 2. PROCESSING
- Verify that all risk components are internally consistent and satisfy the locked risk contract.

## 3. OUTPUT
- Risk state PASS/FAIL, component statuses, risk evidence and confidence.

## 4. GATE
- FAIL if any mandatory risk condition fails; no score can override a hard risk failure.

## 5. SCORE
- 0-100 risk-quality score for diagnostics only; hard gates dominate.

## 6. TRACEABILITY
- Record every component ID/version, timestamp, risk policy and blocking reason codes.