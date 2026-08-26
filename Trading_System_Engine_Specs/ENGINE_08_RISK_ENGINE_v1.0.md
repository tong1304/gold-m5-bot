# ENGINE 08 — RISK / REWARD / TRADE ECONOMICS BRAIN v2.0

## PURPOSE
Model the economics of the proposed trade: invalidation, stop, targets, available space, R-multiple, sizing, exposure and execution costs. It evaluates feasibility; it does not authorize the trade.

## SUB-ENGINES
8A Invalidation Model · 8B Stop Placement · 8C Target/Liquidity Objective · 8D R-Multiple · 8E Position Size · 8F Exposure Limits · 8G Risk Assessment

## INPUT
E1–E7 evidence, setup/confirmation state, structural and liquidity levels, account/risk parameters, spread/slippage/fee assumptions and execution constraints.

## PROCESSING
Construct invalidation thesis; derive technically meaningful stop; identify realistic target/liquidity objectives; calculate reward/risk and R-multiple; estimate position size and exposure; account for transaction costs and execution quality; describe attractive, marginal or poor economics.

## OUTPUT
invalidation_model, stop, target_candidates[], preferred_target, gross_RR, net_RR, expected_cost, position_size, exposure, risk_assessment, asymmetry, evidence[], conflicts[], confidence, observations[], reasoning_trace.

## GATE
NONE. E8 never blocks or authorizes a trade. Undefined risk, poor RR, excessive exposure or unfavorable costs are reported as trade-economic evidence for E9.

## SCORE
Risk quality is analytical evidence. E9 may require minimum economic quality as part of its final decision policy.

## TRACEABILITY
Record risk configuration/version, assumptions, formulas, levels, target rationale, cost model, sizing calculation and upstream evidence.

## DECISION BOUNDARY
Trade economics and risk analysis only; final authorization belongs exclusively to E9.
