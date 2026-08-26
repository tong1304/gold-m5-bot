# ENGINE 02 — MARKET REGIME / OPPORTUNITY BRAIN v2.0

## PURPOSE
Interpret E1 market state as market behavior and identify what type of opportunity the market is currently offering. It does not select an order.

## SUB-ENGINES
2A Trend Regime · 2B Range Regime · 2C Mean-Reversion Behavior · 2D Breakout Regime · 2E Regime Phase · 2F Regime Transition

## INPUT
E1 evidence, M5 price/volatility behavior, permitted M15/H1 context, regime history.

## PROCESSING
Assess continuation, range/reversion, breakout, expansion and transition behavior. Determine regime phase (early/mature/late/failed), opportunity direction(s), and uncertainty. Multiple playbooks may remain candidates when evidence conflicts.

## OUTPUT
regime, regime_phase, candidate_playbooks[], preferred_playbook, opportunity_bias, evidence[], conflicts[], confidence, observations[], reasoning_trace.

## GATE
NONE. E2 must always return its best interpretation of the available evidence, including WAIT/UNRESOLVED when the regime is ambiguous.

## SCORE
Confidence measures certainty of the regime interpretation, not trade profitability.

## TRACEABILITY
Record E1 inputs, sub-engine conclusions, regime transitions, phase evidence, competing interpretations and final synthesis.

## DECISION BOUNDARY
Opportunity/regime analysis only; no BUY/SELL authorization.
