# ENGINE 4 — LIQUIDITY

Phase 3 — Sub-Engine Technical Specification v0.1
Status: Architecture/contract only; production thresholds are not frozen.

## 4A — LIQUIDITY ZONE
**INPUT**
- Swing levels, equal highs/lows, range boundaries, prior highs/lows, session levels.
**PROCESSING**
- Identify liquidity pools, classify buy-side/sell-side, assess significance.
**OUTPUT**
- `LIQUIDITY_ZONE`, `LIQUIDITY_TYPE`, `LIQUIDITY_STRENGTH`.
**GATE**
- Unclear level => no zone.
**SCORE**
- Measures liquidity-zone significance.
**FILTER**
- Weak isolated level, already-consumed liquidity.
**EVIDENCE**
- Repeated highs/lows, swing/session/range level.
**DEPENDENCY**
- Engine 3, 1D.
**CONSUMER**
- 4B–4E, 5C, 6, 8.

## 4B — SWEEP DETECTION
**INPUT**
- Liquidity zones, high/low, close, wick, volume when available.
**PROCESSING**
- Detect penetration of a liquidity zone and return/reclaim behavior.
**OUTPUT**
- `SWEEP_UP`, `SWEEP_DOWN`, `NO_SWEEP`, `SWEEP_STRENGTH`.
**GATE**
- No liquidity zone => no Sweep.
**SCORE**
- Measures sweep quality.
**FILTER**
- Deep continuation without reclaim, meaningless level.
**EVIDENCE**
- Zone penetration, wick, close back inside.
**DEPENDENCY**
- 4A, 1A.
**CONSUMER**
- 4C, 4E, 6, 7.

## 4C — REJECTION
**INPUT**
- Liquidity zone, sweep, candle OHLC, structure.
**PROCESSING**
- Detect rejection, strength and close location.
**OUTPUT**
- `REJECTION_UP`, `REJECTION_DOWN`, `NO_REJECTION`, `REJECTION_STRENGTH`.
**GATE**
- No meaningful rejection => no confirmation of rejection.
**SCORE**
- Measures rejection quality.
**FILTER**
- Weak wick, close continuing through zone.
**EVIDENCE**
- Wick, body, close, zone interaction.
**DEPENDENCY**
- 4A, 4B.
**CONSUMER**
- Engine 6, Engine 7.

## 4D — ACCEPTANCE
**INPUT**
- Liquidity zone, close, consecutive candles, structure, volume when available.
**PROCESSING**
- Detect acceptance and persistence beyond a level.
**OUTPUT**
- `ACCEPTED_ABOVE`, `ACCEPTED_BELOW`, `NO_ACCEPTANCE`, `ACCEPTANCE_STRENGTH`.
**GATE**
- No persistence => no Acceptance.
**SCORE**
- Measures acceptance strength.
**FILTER**
- Single-candle break, immediate reclaim.
**EVIDENCE**
- Closes beyond level, persistence, follow-through.
**DEPENDENCY**
- 4A, Engine 3C.
**CONSUMER**
- Engine 6, Engine 7.

## 4E — RECLAIM / FAILED BREAK
**INPUT**
- Liquidity zone, break event, close, rejection, structure.
**PROCESSING**
- Detect break, reclaim and failed-break behavior.
**OUTPUT**
- `RECLAIM`, `FAILED_BREAK`, `NO_RECLAIM`, `RECLAIM_STRENGTH`.
**GATE**
- No original level => invalid event.
**SCORE**
- Measures reclaim/failed-break quality.
**FILTER**
- Ambiguous level, no confirmation.
**EVIDENCE**
- Original level, break, reclaim close, follow-through.
**DEPENDENCY**
- 4A–4D, 3C/3D.
**CONSUMER**
- Engine 6, Engine 7, Engine 9.
