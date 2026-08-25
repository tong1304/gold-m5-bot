# 9G Final Decision

## 1. INPUT
- PASS/FAIL results from 9A-9F plus their evidence and scores.

## 2. PROCESSING
- Apply the locked Engine 9 decision contract to combine gate outcomes and permitted quality evidence.
- This is the only Sub-Engine allowed to produce the parent engine's final decision state, but it must not invent criteria outside the contract.

## 3. OUTPUT
- Final decision state such as APPROVE, REJECT or NO_DECISION, with direction only when supplied by the established setup/confirmation contract.

## 4. GATE
- Any mandatory upstream FAIL blocks approval.

## 5. SCORE
- Aggregate diagnostic score 0-100 with explicit component provenance; score never overrides hard gates.

## 6. TRACEABILITY
- Record every gate result, component score, contract version, timestamp, decision and reason codes.