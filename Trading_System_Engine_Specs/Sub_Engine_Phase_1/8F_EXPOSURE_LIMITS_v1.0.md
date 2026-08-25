# 8F — EXPOSURE LIMITS

## 1. INPUT
Proposed risk exposure, account limits, existing exposure metadata permitted by system.

## 2. PROCESSING
Evaluate aggregate exposure against configured limits without changing the proposed trade decision.

## 3. OUTPUT
Exposure state, utilization, violated limits, confidence, reasons.

## 4. GATE
FAIL when any mandatory exposure limit is exceeded.

## 5. SCORE
Exposure-quality/status score is evidence only; hard limits dominate.

## 6. TRACEABILITY
Record limit config/version, exposure inputs, utilization, timestamp, gate.

**DECISION BOUNDARY:** exposure control only.