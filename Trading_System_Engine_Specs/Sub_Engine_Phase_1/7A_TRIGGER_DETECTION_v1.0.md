# 7A — TRIGGER DETECTION

## 1. INPUT
Validated setup state, closed-candle evidence, versioned trigger definitions.

## 2. PROCESSING
Detect a defined trigger event only after setup prerequisites are valid.

## 3. OUTPUT
Trigger ID/state, trigger candle, evidence, confidence, reasons.

## 4. GATE
FAIL when setup is invalid or trigger evidence is absent/incomplete.

## 5. SCORE
Trigger quality 0–100; evidence only.

## 6. TRACEABILITY
Record setup/trigger versions, candle ID, evidence, timestamp, gate, score.

**DECISION BOUNDARY:** trigger detection only.