# 1G — TRANSITION

## 1. INPUT
Outputs from 1B–1F plus validated price history.

## 2. PROCESSING
Identify changes between physical market states using persistence and state-change evidence; do not assign trading regime.

## 3. OUTPUT
State-transition status, from/to states, transition evidence, confidence, reason codes.

## 4. GATE
BLOCK when prior/current state evidence is unreliable.

## 5. SCORE
Transition quality 0–100; evidence only.

## 6. TRACEABILITY
Record prior/current states, timestamps, upstream versions, transition evidence, score, gate.

**DECISION BOUNDARY:** physical state transition only; regime ownership belongs to E2.