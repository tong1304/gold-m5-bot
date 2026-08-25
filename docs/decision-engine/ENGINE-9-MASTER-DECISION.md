# ENGINE 9 — MASTER DECISION

Phase 3 — Sub-Engine Technical Specification v0.1
Status: Architecture/contract only; production thresholds are not frozen.

Engine 9 is a decision layer. It must not recreate Market State, Regime, Structure, Liquidity, Setup or Risk logic owned by Engines 1–8.

## 9A — DATA GATE
**INPUT**
- Data validity, data quality, required market data.
**PROCESSING**
- Verify data readiness for decision.
**OUTPUT**
- `DATA_PASS`, `DATA_FAIL`.
**GATE**
- `DATA_FAIL` => `NO_TRADE`.
**SCORE**
- Not required.
**FILTER**
- Invalid, stale or incomplete data.
**EVIDENCE**
- 1A.
**DEPENDENCY**
- 1A.
**CONSUMER**
- 9B.

## 9B — CONTEXT GATE
**INPUT**
- Market State, Market Regime, Structure, Location, Liquidity.
**PROCESSING**
- Verify context alignment and directional contradiction.
**OUTPUT**
- `CONTEXT_PASS`, `CONTEXT_FAIL`.
**GATE**
- Invalid context => `NO_TRADE`.
**SCORE**
- May consume upstream context scores; must not invent new context data.
**FILTER**
- Conflicting regime, bad location, insufficient space.
**EVIDENCE**
- Engines 1–5.
**DEPENDENCY**
- Engines 1–5.
**CONSUMER**
- 9C.

## 9C — SETUP GATE
**INPUT**
- Setup context, pattern, setup state, validity, setup quality.
**PROCESSING**
- Verify setup completeness, quality and invalidation state.
**OUTPUT**
- `SETUP_PASS`, `SETUP_FAIL`.
**GATE**
- Invalid/incomplete setup => `NO_TRADE`.
**SCORE**
- Consumes `SETUP_SCORE` from 6E.
**FILTER**
- Invalidated, expired, poor quality.
**EVIDENCE**
- Engine 6.
**DEPENDENCY**
- 6A–6E.
**CONSUMER**
- 9D.

## 9D — CONFIRMATION GATE
**INPUT**
- Trigger, candle quality, follow-through, execution quality, confirmation quality.
**PROCESSING**
- Verify confirmation completeness, direction and contradiction.
**OUTPUT**
- `CONFIRMATION_PASS`, `CONFIRMATION_FAIL`.
**GATE**
- Missing/invalid confirmation => `NO_TRADE`.
**SCORE**
- Consumes `CONFIRMATION_SCORE` from 7E.
**FILTER**
- Weak trigger, failed confirmation, bad execution.
**EVIDENCE**
- Engine 7.
**DEPENDENCY**
- 7A–7E.
**CONSUMER**
- 9E.

## 9E — RISK GATE
**INPUT**
- Invalidation, stop, target, R/R, position size, exposure.
**PROCESSING**
- Verify risk completeness, R/R, size and exposure.
**OUTPUT**
- `RISK_PASS`, `RISK_FAIL`.
**GATE**
- Any mandatory risk failure => `NO_TRADE`.
**SCORE**
- May consume risk quality/R-multiple as supporting evidence.
**FILTER**
- Invalid SL, poor R/R, excessive size, exposure violation.
**EVIDENCE**
- Engine 8.
**DEPENDENCY**
- 8A–8F.
**CONSUMER**
- 9F.

## 9F — EXECUTION GATE
**INPUT**
- Execution quality, spread, slippage, entry price, stop/target, current market state.
**PROCESSING**
- Verify execution feasibility and that the signal remains executable at decision time.
**OUTPUT**
- `EXECUTION_PASS`, `EXECUTION_FAIL`.
**GATE**
- Execution condition outside policy => `NO_TRADE`.
**SCORE**
- Consumes execution quality from 7D.
**FILTER**
- Excessive spread/slippage, price beyond valid entry, changed market condition.
**EVIDENCE**
- 7D and current execution data.
**DEPENDENCY**
- 7D, 8B–8D.
**CONSUMER**
- 9G.

## 9G — FINAL DECISION
**INPUT**
- 9A–9F gate results plus approved upstream evidence.
**PROCESSING**
- Require all mandatory gates, resolve direction, produce final confidence and decision payload.
**OUTPUT**
- `BUY`, `SELL`, `NO_TRADE`; plus direction, entry, SL, TP, R/R, position size, confidence, evidence and rejection reason.
**GATE**
- Any mandatory gate failure => `NO_TRADE`.
**SCORE**
- Integrates only approved upstream scores; it must not create duplicate scoring logic.
**FILTER**
- Data, context, setup, confirmation, risk or execution hard failure.
**EVIDENCE**
- Engines 1–8.
**DEPENDENCY**
- 9A–9F.
**CONSUMER**
- Final signal, Telegram, replay and statistics layers.

## GLOBAL ENGINE 9 RULE
Engine 9 integrates and decides. It does not redefine upstream facts or silently override a hard gate.
