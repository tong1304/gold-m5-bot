# ENGINE 05 — LOCATION / VALUE BRAIN v2.0

## PURPOSE
Determine whether current price is located where a proposed market idea has favorable asymmetry, using value, structure, liquidity, extension and available space.

## SUB-ENGINES
5A Equilibrium/Value · 5B Structural Location · 5C Liquidity Location · 5D Extension · 5E Available Space · 5F Location Quality

## INPUT
E1–E4 evidence, current price, structural levels, liquidity zones, value references, volatility/extension measures.

## PROCESSING
Evaluate premium/discount/equilibrium, proximity to structural and liquidity references, extension, room to target, and whether price is attractively positioned or already late/chased. Compare both long and short location when appropriate.

## OUTPUT
value_state, structural_location, liquidity_location, extension_state, available_space, long_location_quality, short_location_quality, preferred_location, evidence[], conflicts[], confidence, observations[], reasoning_trace.

## GATE
NONE. Poor location is an observation, not a gate. The engine must describe the location even when neither side is attractive.

## SCORE
Confidence describes certainty of the location assessment; location quality describes asymmetry and is evidence for E6–E9.

## TRACEABILITY
Record reference levels, distances, extension calculations, available-space calculations, upstream evidence and timestamp.

## DECISION BOUNDARY
Location/value analysis only.
