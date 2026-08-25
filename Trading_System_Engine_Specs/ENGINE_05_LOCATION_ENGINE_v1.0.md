# ENGINE 05 — LOCATION / VALUE ENGINE v1.0

## PURPOSE
Evaluate price location relative to value, structure, liquidity, extension, and available space.

## SUB-ENGINES
5A Equilibrium/Value · 5B Structural Location · 5C Liquidity Location · 5D Extension · 5E Available Space · 5F Location Quality

## INPUT
ENGINE 01–04 outputs, price data, value references, structural and liquidity levels.

## PROCESSING
Determine value relationship, structural/liquidity location, extension, available space, quality.

## OUTPUT
Location state, value relationship, extension/space measures, quality/confidence, reason codes.

## GATE
Block interpretation when reference levels are invalid, stale, or insufficient.

## SCORE
Location quality is evidence only and cannot authorize a trade or bypass a gate.

## TRACEABILITY
Record reference levels, source candles, upstream versions, timestamp, gate status, scores, confidence, reason codes.

## DECISION BOUNDARY
Location/value analysis only; no BUY/SELL decision.