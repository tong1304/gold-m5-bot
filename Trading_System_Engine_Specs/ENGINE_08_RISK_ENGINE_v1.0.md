# ENGINE 08 — RISK / REWARD ENGINE v1.0

## PURPOSE
Evaluate invalidation, stop, target, R-multiple, position size, exposure, and risk constraints.

## SUB-ENGINES
8A Invalidation Model · 8B Stop Placement · 8C Target/Liquidity Objective · 8D R-Multiple · 8E Position Size · 8F Exposure Limits · 8G Risk Gate

## INPUT
Validated setup/confirmation evidence, structural/liquidity references, account/risk parameters, execution constraints.

## PROCESSING
Model invalidation, stop placement, target objectives, R-multiple, position size, exposure limits, hard risk constraints.

## OUTPUT
Invalidation level, stop/target model, R-multiple, position-size result, exposure status, risk gate result, reason codes.

## GATE
Block execution consideration when risk constraints fail, invalidation undefined, exposure excessive, or required inputs unavailable.

## SCORE
Risk quality may support evidence, but hard risk gates always take precedence.

## TRACEABILITY
Record risk configuration/version, assumptions, levels, calculations, gate status, scores, timestamp, reason codes.

## DECISION BOUNDARY
Risk/feasibility analysis only; no independent trade decision.