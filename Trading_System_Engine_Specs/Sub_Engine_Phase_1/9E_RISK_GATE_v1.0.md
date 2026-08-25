# 9E — RISK GATE

## 1. INPUT
E8 risk outputs, especially 8G, plus mandatory risk metadata.

## 2. PROCESSING
Apply the master decision-layer risk contract to validated E8 results; do not recalculate E8 internals.

## 3. OUTPUT
PASS/FAIL master risk gate, blocking reason(s), risk summary.

## 4. GATE
FAIL if any mandatory E8 risk condition fails or required risk evidence is missing.

## 5. SCORE
Risk summary 0–100 is informational only.

## 6. TRACEABILITY
Record E8 versions/results, configuration version, timestamp, gate, reasons.

**DECISION BOUNDARY:** master gate; E9 only.