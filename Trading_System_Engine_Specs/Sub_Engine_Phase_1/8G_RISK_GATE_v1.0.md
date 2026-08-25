# 8G — RISK GATE

## 1. INPUT
8A–8F risk outputs and configured hard risk constraints.

## 2. PROCESSING
Evaluate whether all mandatory risk prerequisites are satisfied and return a risk-feasibility state.

## 3. OUTPUT
PASS/FAIL risk gate, blocking reason(s), risk evidence summary.

## 4. GATE
FAIL on undefined invalidation, invalid stop/target, prohibited exposure, sizing failure, or configured hard-risk breach.

## 5. SCORE
Risk quality 0–100 may summarize evidence but can never override a hard failure.

## 6. TRACEABILITY
Record every risk sub-engine version/output, configuration, gate result, timestamp, reasons.

**DECISION BOUNDARY:** E8 feasibility gate only; E9 owns final decision.