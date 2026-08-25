# ENGINE 6 — SETUP

Phase 3 — Sub-Engine Technical Specification v0.1
Status: Architecture/contract only; production thresholds are not frozen.

## 6A — SETUP CONTEXT
**INPUT**
- Market Regime, structure, liquidity, location, volatility.
**PROCESSING**
- Assess setup context, directional opportunity and alignment.
**OUTPUT**
- `CONTEXT_VALID`, `CONTEXT_INVALID`, `SETUP_DIRECTION`, `CONTEXT_QUALITY`.
**GATE**
- Invalid context => STOP.
**SCORE**
- Measures context alignment.
**FILTER**
- Conflicting regime, bad location, insufficient space.
**EVIDENCE**
- Engines 2–5.
**DEPENDENCY**
- Engines 2, 3, 4, 5.
**CONSUMER**
- 6B–6E.

## 6B — SETUP PATTERN
**INPUT**
- Context, structure, liquidity, location, price pattern.
**PROCESSING**
- Detect pattern, direction and completeness.
**OUTPUT**
- `SETUP_PATTERN`, `SETUP_DIRECTION`, `PATTERN_VALID`, `PATTERN_QUALITY`.
**GATE**
- Incomplete/invalid pattern => STOP.
**SCORE**
- Measures pattern quality.
**FILTER**
- Ambiguous pattern, counter-context pattern.
**EVIDENCE**
- Price structure, liquidity event, pattern geometry.
**DEPENDENCY**
- 6A, Engines 3–5.
**CONSUMER**
- 6C, 6E, Engine 7.

## 6C — SETUP STATE MACHINE
**INPUT**
- Setup pattern, trigger conditions, current price, candle/time sequence, invalidation.
**PROCESSING**
- Track lifecycle, state transitions, premature entry, expiry.
**OUTPUT**
- `FORMING`, `ARMED`, `TRIGGERED`, `INVALIDATED`, `EXPIRED`.
**GATE**
- `INVALIDATED` or `EXPIRED` => STOP.
**SCORE**
- State machine is primarily deterministic; optional state confidence may support diagnostics.
**FILTER**
- Repeated invalid setup, timeout, state regression.
**EVIDENCE**
- State history, setup conditions, price events.
**DEPENDENCY**
- 6A, 6B.
**CONSUMER**
- Engine 7, Engine 9.

## 6D — INVALIDATION
**INPUT**
- Setup definition, structure, liquidity, setup state, price.
**PROCESSING**
- Determine whether the setup premise remains valid; detect invalidation and expiry.
**OUTPUT**
- `SETUP_VALID`, `SETUP_INVALID`, `INVALIDATION_REASON`.
**GATE**
- `SETUP_INVALID` => STOP.
**SCORE**
- Measures remaining setup validity when useful.
**FILTER**
- Broken premise, opposite structural event, expired setup.
**EVIDENCE**
- Original premise, structural violation, price event.
**DEPENDENCY**
- Engine 3, Engine 4, 6A–6C.
**CONSUMER**
- 6C, Engine 7, Engine 9.

Boundary: 6D determines whether the setup premise remains valid; it does not define the monetary stop-loss.

## 6E — SETUP QUALITY
**INPUT**
- Context quality, pattern quality, setup state, location, structure, liquidity.
**PROCESSING**
- Combine quality factors, assess confluence and contradiction.
**OUTPUT**
- `SETUP_SCORE`, `SETUP_QUALITY`, `SETUP_CONFIDENCE`.
**GATE**
- Below policy minimum => STOP.
**SCORE**
- Measures overall setup quality.
**FILTER**
- Major contradiction, poor location, weak structure, low liquidity quality.
**EVIDENCE**
- 6A–6D and Engines 3–5.
**DEPENDENCY**
- 6A–6D.
**CONSUMER**
- Engine 7, Engine 9.
