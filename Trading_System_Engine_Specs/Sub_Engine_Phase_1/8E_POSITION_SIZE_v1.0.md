# 8E — POSITION SIZE

## 1. INPUT
Approved risk budget, stop distance, account parameters, instrument constraints.

## 2. PROCESSING
Calculate position size from configured risk model and instrument rules; no strategy selection.

## 3. OUTPUT
Position-size result, assumptions, constraint status, reasons.

## 4. GATE
BLOCK when account/risk inputs or instrument constraints are invalid.

## 5. SCORE
Calculation quality 0–100; hard constraints prevail.

## 6. TRACEABILITY
Record risk config/version, account-input identifiers, formula, timestamp, result.

**DECISION BOUNDARY:** sizing calculation only.