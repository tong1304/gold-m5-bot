# 6C — SETUP FORMATION STATE MACHINE

## 1. INPUT
6A context, 6B archetype, causal candle/event evidence.

## 2. PROCESSING
Track setup lifecycle states using explicit valid transitions; no final decision.

## 3. OUTPUT
Current setup state, prior state, transition event, confidence, reasons.

## 4. GATE
BLOCK when state transition evidence is invalid or contradictory.

## 5. SCORE
Formation quality 0–100; evidence only.

## 6. TRACEABILITY
Record setup ID, state history, event candles, definition/version, score, gate.

**DECISION BOUNDARY:** lifecycle state only.