# 6C Setup Formation State Machine

## 1. INPUT
- Setup archetype plus chronological closed-candle evidence.

## 2. PROCESSING
- Track setup lifecycle states such as NOT_FORMED, FORMING, READY_FOR_CONFIRMATION, INVALIDATED.
- State transitions must be deterministic and time-ordered.

## 3. OUTPUT
- Current setup state, transition event, prior state and confidence.

## 4. GATE
- FAIL on impossible state transitions or missing required event history.

## 5. SCORE
- 0-100 formation-quality score based on state completeness and transition validity.

## 6. TRACEABILITY
- Record state history, transition rule/version, candle IDs, timestamp and reason codes.