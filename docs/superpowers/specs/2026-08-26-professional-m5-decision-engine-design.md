# Professional M5 Decision Engine Design

## Goal
Replace the legacy strategy-driven execution path with one coherent professional short-term M5 decision architecture using the nine new engines and their sub-engines, with GOLD and BTC separated at the asset-policy layer and with profitability—not inactivity—as the optimization objective.

## Core principle
The system must behave like a disciplined short-term trader: identify market conditions, locate asymmetric opportunity, wait for a valid setup and confirmation, size risk rationally, and execute when the expected edge is sufficient. WAIT is a valid outcome but must not become the optimization target. Hard gates are reserved for conditions that invalidate the trade; evidence and quality factors contribute to an edge score.

## Canonical architecture

```text
Market Data
  -> E1 Market State
  -> E2 Market Regime
  -> E3 Market Structure
  -> E4 Liquidity
  -> E5 Location
  -> E6 Setup
  -> E7 Confirmation
  -> E8 Risk
  -> E9 Execution Decision
```

E9 is the sole execution authority. No legacy engine, legacy strategy dispatcher, or cross-asset strategy fallback may create or authorize an order.

## Engine responsibilities

### E1 Market State
Determine data quality, volatility state, directional state, range state, compression, expansion and transition. E1 may reject unusable or genuinely transitional market conditions, but a merely non-perfect directional state must not automatically suppress every trade opportunity.

### E2 Market Regime
Classify the current behavioral regime and phase. Regime determines which setup archetypes are appropriate; it does not directly issue BUY/SELL.

### E3 Market Structure
Detect swings, structure classification, BOS, structural failure, strength, and internal/external alignment. Structure provides directional context and invalidation logic.

### E4 Liquidity
Detect liquidity zones, sweeps, rejection/reaction, acceptance, reclaim/failed breaks, and liquidity quality. Liquidity is evidence, not an automatic entry trigger.

### E5 Location
Evaluate equilibrium/value, structural location, liquidity location, extension, available space, and location quality. Location should prevent chasing and poor reward geometry without requiring a perfect location.

### E6 Setup
Translate upstream evidence into a short-term setup archetype and formation state. The setup engine must recognize continuation, breakout, breakout-retest, rejection/reversal and mean-reversion opportunities when the regime supports them. Setup maturity is evidence and should not be made unnecessarily restrictive.

### E7 Confirmation
Detect trigger, trigger quality, follow-through, failure/invalidation, execution conditions and confirmation quality. A valid trigger should be sufficient to act when upstream edge is strong; confirmation must not require every optional signal simultaneously.

### E8 Risk
Build structural invalidation, stop, target, R multiple, position sizing, exposure limits and risk gate. E8 may reject invalid risk geometry, but it must not reject a trade merely because its risk is non-zero. Minimum RR is a hard constraint; target RR is a preferred objective.

### E9 Execution Decision
Combine hard gates, evidence scores, direction agreement, setup quality, confirmation, and risk into a final decision. E9 alone can return BUY, SELL, WAIT or NO_TRADE. The decision must include reason codes and an auditable evidence vector.

## Hard gate vs evidence policy

Hard gates are limited to:
- invalid/unusable market data;
- confirmed structural invalidation;
- setup invalidation;
- confirmation failure after a trigger has actually failed;
- invalid stop or target geometry;
- minimum RR violation;
- hard exposure/risk limits;
- execution/data integrity failures.

Evidence/score factors include:
- directional strength;
- regime quality;
- structure strength;
- liquidity quality;
- location quality;
- setup quality/maturity;
- trigger quality;
- follow-through;
- reward geometry above the minimum.

The system must not require all evidence factors to pass as independent hard gates.

## Profitability objective

Primary optimization target:
1. positive expectancy after realistic spread/slippage/fees;
2. sufficient trade frequency to capture opportunity;
3. acceptable win rate for the chosen RR;
4. positive profit factor;
5. controlled drawdown.

The system must not optimize for maximum win rate alone or maximum signal count alone.

## Asset separation

GOLD and BTC share the nine-engine reasoning framework and contract shapes, but do not share trade setups, thresholds, target models, volatility assumptions, or strategy fallbacks. Asset-specific policy modules provide parameters and allowed setup archetypes.

No GOLD setup may be executed for BTC and no BTC setup may be executed for GOLD.

## Legacy removal

The following must not remain on the production execution path:
- `v11/engine.py` as a decision dispatcher;
- G1/G2/G3 legacy GOLD strategy dispatch;
- B1/B2/B3 legacy BTC strategy dispatch;
- cross-asset fallback;
- legacy strategy scoring as final authority.

Legacy files may remain only as archived/reference code if no runtime import reaches them.

## Backtest and audit requirements

Production and backtest must use the same canonical pipeline and contracts. Every closed M5 candle must produce an auditable record containing:
- asset and candle timestamp;
- E1-E9 state;
- sub-engine outputs/scores;
- hard-gate reason codes;
- evidence score;
- final decision;
- trade plan when applicable;
- eventual outcome in R.

The validation report must measure both profitable opportunity and over-filtering:
- trades, wins, losses, win rate;
- average win/loss R;
- expectancy R/trade;
- profit factor;
- net R;
- max drawdown;
- trades/day;
- opportunity capture rate;
- block rate by engine/sub-engine;
- outcomes of trades blocked by each gate;
- GOLD/BTC results separately;
- regime-specific results separately.

A gate is considered useful only when its removal demonstrably worsens risk-adjusted expectancy or violates a hard risk constraint. A gate that mainly removes winners must be relaxed or converted to evidence scoring.

## Success criteria

The implementation is considered structurally complete only when:
- the production runtime imports the canonical nine-engine pipeline;
- no legacy dispatcher or cross-asset fallback is reachable from production;
- GOLD and BTC use isolated asset policies;
- all nine engines and their sub-engines execute through one contract;
- E9 is the sole decision authority;
- backtest and live use the same decision path;
- tests verify that profitable opportunities are not suppressed by optional evidence factors;
- the system produces a complete profitability/over-filtering report.

Profitability itself is not assumed by architecture; it must be demonstrated by realistic out-of-sample testing.
