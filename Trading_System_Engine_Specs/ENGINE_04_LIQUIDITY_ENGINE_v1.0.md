# ENGINE 04 — LIQUIDITY BRAIN v2.0

## PURPOSE
Determine where liquidity is likely concentrated and how price interacted with it. Liquidity evidence informs the thesis; it does not create a trade signal.

## SUB-ENGINES
4A Liquidity Zone Detection · 4B Sweep Detection · 4C Reaction/Rejection · 4D Acceptance · 4E Reclaim/Failed Break · 4F Liquidity Strength/Quality

## INPUT
E1–E3 evidence, M5 candles, structural highs/lows, permitted higher-timeframe liquidity references.

## PROCESSING
Map liquidity pools and zones; identify sweeps, rejection, acceptance, reclaim and failed breaks; distinguish real interaction from ordinary volatility; assess whether liquidity behavior supports continuation or reversal.

## OUTPUT
liquidity_map, active_zones[], event, reaction, acceptance, reclaim_state, directional_implication, strength, evidence[], conflicts[], confidence, observations[], reasoning_trace.

## GATE
NONE. NO_EVENT is a valid conclusion. Ambiguous liquidity is preserved as uncertainty rather than treated as failure.

## SCORE
Confidence measures clarity and quality of liquidity evidence only.

## TRACEABILITY
Record zone sources, event candle, pre/post-event price behavior, upstream structure and all competing interpretations.

## DECISION BOUNDARY
Liquidity analysis only.
