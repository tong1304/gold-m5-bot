# Opportunity Quality Without Signal Inflation

## Goal
Increase the probability quality of valid trades by improving evidence reconciliation across E1-E9, without lowering hard gates or deliberately increasing trade frequency.

## Current diagnosis
The production-v2 log shows a recurring pattern: E1/E3/E4 can produce a directional thesis while E2 remains unresolved; E6 can form a setup while explicitly marking it not trade-ready; E7 may prove a setup-specific confirmation while E8 still rejects the trade because geometry, target, stop quality, or real RR is invalid; E9 correctly blocks the trade. The main optimization target is therefore evidence reconciliation and trade-geometry discovery, not threshold relaxation.

## Design
1. E1 remains the market-state/context brain. Improve classification of transition/range versus directional state and expose evidence strength plus counter-evidence without forcing a direction.
2. E2 remains opportunity/regime analysis. Replace broad unresolved blocking semantics with explicit maturity and conditional paths: what is confirmed, what is supporting, what conflicts, and the exact next closed-candle event required. E2 never authorizes entry.
3. E3 distinguishes external structure from internal pullback structure. Internal counter-direction is treated as context when it is a retracement rather than automatically as a thesis conflict. Confirmed pivots and no-lookahead rules remain mandatory.
4. E4 keeps auction lifecycle stateful. Internal liquidity has lower weight than external liquidity, and pending acceptance is not converted into confirmation. Follow-through must be tied to the causal event.
5. E5 separates location quality from executable space. Direction-specific space, structural targets, extension, and value response are exposed explicitly. A favorable location cannot override inadequate space.
6. E6 forms and stages setup hypotheses using the upstream evidence ledger. It may mark a setup as FORMING/VALIDATING/MATURE, but never authorizes a trade. It should preserve valid theses when a weaker counter-signal is only a normal pullback.
7. E7 separates setup confirmation from entry trigger. A proven setup does not imply an entry unless the current closed candle supplies the setup-specific trigger.
8. E8 remains a hard economic/risk gate. Do not lower MIN_RR, probability, stop-quality, target-realism, or execution-cost gates merely to create trades. Improve geometry evaluation by testing defensible entry/stop/target alternatives derived from structural levels and available space, then choose the best valid geometry or explicitly reject it.
9. E9 remains the sole final authority. It must distinguish duplicated evidence from independent conflicts, preserve hard vetoes, and produce a transparent governance trace. No upstream evidence may be invented or upgraded from pending to confirmed.
10. professional_brain_audit remains non-authoritative but must measure opportunity quality more usefully: latent opportunity is a watch metric, not a profit forecast. It must never unlock execution.
11. pipeline.py remains the single sequential E1→E9 orchestration path. No parallel peer authority and no automatic trade-frequency expansion.

## Success criteria
- No hard risk gate is relaxed.
- No new path can create an order without E9 approval.
- A normal internal pullback does not create a false hard conflict against a stronger external thesis.
- Pending auction evidence remains pending until causal follow-through occurs.
- E8 rejects invalid geometry rather than forcing a trade, but evaluates structurally defensible alternatives before rejecting.
- E9's final decision is reproducible from the evidence ledger.
- Opportunity quality is measured independently from trade count.
- Existing closed-candle/no-lookahead behavior remains intact.

## Testing
Use focused unit tests for each changed brain plus pipeline integration tests. Include explicit regression cases from the supplied BTC logs: transition/range with bearish external structure and bullish internal structure; pending low acceptance; low short-space; E7 confirmation with E8 economic rejection; and duplicate-candle suppression. Run the full available pytest suite before deployment.
