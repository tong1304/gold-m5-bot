# 9H Decision Logging

## 1. INPUT
- Complete Engine 9 decision package, upstream references, market snapshot and contract versions.

## 2. PROCESSING
- Serialize a deterministic audit record suitable for replay, debugging and statistical analysis.
- Do not alter the decision.

## 3. OUTPUT
- Immutable decision/audit record, event ID, schema version and reason-code set.

## 4. GATE
- FAIL only when mandatory audit fields cannot be persisted/validated.
- Logging failure must not silently rewrite decision content.

## 5. SCORE
- No decision-quality score. Optional logging-integrity score 0-100 may report completeness.

## 6. TRACEABILITY
- Record decision ID, symbol, timeframe, timestamp, all upstream versions, inputs/outputs, gates, scores and final state.