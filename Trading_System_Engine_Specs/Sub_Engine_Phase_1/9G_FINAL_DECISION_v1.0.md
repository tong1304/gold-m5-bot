# 9G — FINAL DECISION

## 1. INPUT
9A–9F validated gate states and permitted evidence summaries.

## 2. PROCESSING
Apply the locked decision hierarchy and produce the single system-level final decision state. No downstream module may override it.

## 3. OUTPUT
Final decision state, execution eligibility, block reason(s), evidence summary.

## 4. GATE
Mandatory gate failure results in a blocked final state.

## 5. SCORE
Final quality/confidence summarizes evidence only; hard gates always prevail.

## 6. TRACEABILITY
Record every upstream engine/sub-engine version/output, gate results, timestamp, symbol/timeframe, final state.

**DECISION BOUNDARY:** this is the only Sub-Engine permitted to emit the system-level final decision state, under E9 contract.