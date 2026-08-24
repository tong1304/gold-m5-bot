# GOLD G9-G11 Strategy Design

Date: 2026-08-25
Status: Design approved in chat; implementation pending written-spec review

## Goal

Add three GOLD-only M5 strategy engines to the existing V12.2 MTF engine without changing BTC behavior:

- G9: Liquidity Sweep + CHoCH Reversal
- G10: Continuation FVG Pullback
- G11: Session Breakout + Retest

The engines must work in live analysis and Replay using only candles available as of the M5 trigger. No future bars may be used.

## Architecture

Keep the existing V12.2 orchestration in `v11/engine.py`: MTF alignment, regime classification, strategy evaluation, setup-state/re-entry control, risk calculation, and final decision payload remain the central flow.

Add GOLD-specific strategy implementations under `v11/strategies/gold/` and expose them through the existing strategy engine. Extend engine metadata, priority selection, and strategy-specific RR mapping. BTC continues to use E1-E8 only.

The new engines return the same candidate contract as existing engines: status, engine, strategy, direction, setup anchor, evidence, quality, trigger signature, and rejection reasons.

## G9 — Liquidity Sweep + CHoCH

### BUY
1. Find the lowest swing/reference low over the prior 20 M5 bars, excluding the trigger candle where appropriate to avoid self-reference.
2. Require trigger low below that level and trigger/confirmation close back above it.
3. Require a later M5 close above the latest relevant swing high (CHoCH).
4. Identify a bullish FVG (`low[0] > high[2]`) or the last bearish candle before the CHoCH impulse as bullish OB.
5. Record the zone and generate a pending-limit setup at the configured zone edge.
6. SL = sweep low - 1.5 pips; TP target = 1.5R or prior M5 high, whichever is valid under risk rules.

### SELL
Mirror BUY: sweep above 20-bar high, close back below, CHoCH below latest swing low, bearish FVG (`high[0] < low[2]`) or last bullish candle before the bearish impulse, pending sell-limit zone, SL = sweep high + 1.5 pips, TP = 1.5R or prior M5 low.

G9 uses an explicit `PENDING_LIMIT` setup state. Replay must mark a setup first and only mark it filled when price subsequently touches the entry zone.

## G10 — Continuation FVG Pullback

### BUY
- M15 EMA50 > EMA200.
- H1 close > EMA50.
- M5 body > average M5 body(20) * 1.8.
- Bullish FVG (`low[0] > high[2]`) with gap >= 150 points.
- After the FVG exists, wait for price to retest the zone.
- Require bullish engulfing or lower-wick pinbar on M5.
- Market BUY on confirmation.
- SL = FVG bottom - 1.0 pip.
- TP = 2R.

### SELL
Mirror BUY with M15 EMA50 < EMA200, H1 close < EMA50, bearish FVG, upper retest, bearish engulfing or upper-wick pinbar, SL above FVG top, and TP = 2R.

The 150-point threshold must be converted using the GOLD instrument's actual price precision/point size rather than assuming a universal decimal format.

## G11 — Session Breakout + Retest

Timezone: `Asia/Bangkok`.

Range build: 08:00 through 13:55 inclusive of closed M5 bars.

Trading windows: 14:00-17:00 and 19:00-22:00.

State machine:
`BUILD_RANGE -> BREAKOUT -> WAIT_RETEST -> RETEST_CONFIRMED -> ENTRY`.

### BUY
- M5 close > Asian High.
- Current volume > average volume(20).
- Later retest low <= Asian High.
- Retest candle closes back above Asian High.
- Market BUY.
- SL = Asian High - 0.35 * range height, with retest-wick alternative only when it produces a valid safer structural stop.
- TP = entry + range height.

### SELL
Mirror BUY around Asian Low. SL = Asian Low + 0.35 * range height. TP = entry - range height.

A setup is valid only inside the two trading windows and only after the range has been completely built. The range is calculated from historical candles available before the breakout/retest event.

## Priority

New GOLD priority:
1. G9
2. G10
3. G11
4. existing E7
5. E4
6. E1
7. E2
8. E5
9. E3
10. E6
11. E8

The priority gate prevents a lower-priority engine from replacing a higher-priority valid setup.

## Risk integration

Extend strategy RR rules:
- G9: minimum 1.5R
- G10: minimum 2.0R
- G11: minimum 1.0R (range-height target), subject to structural-risk validation

The existing `risk.py` remains the single risk calculation path, but it must accept engine evidence for explicit FVG/OB/session levels and explicit buffers. No duplicate risk engine will be introduced.

## Replay and Statistics

Each G9-G11 result must preserve:
- engine/strategy name
- direction
- trigger time
- setup/trigger IDs
- setup state
- entry type (`PENDING_LIMIT` for G9, `MARKET` for G10/G11)
- entry/SL/TP and RR
- evidence used by the engine
- exact rejection reason when no trade occurs

Replay must use chronological candles and must not use the future outcome candle to decide entry.

## Data-quality / error handling

The existing MTF validation remains a hard gate. Invalid LSE responses must not be silently converted into fabricated candles. GOLD H1/M15/M5 context must be validated before strategy evaluation.

The previously observed `LSE_INVALID_RESPONSE:GOLD:1h` issue is treated as a separate data-source normalization/validation issue and should not be masked by G9-G11.

## Testing

Add unit tests for:
- G9 BUY/SELL sweep + CHoCH + FVG/OB detection and rejection cases.
- G10 BUY/SELL trend filter, body threshold, FVG size, retest and confirmation.
- G11 range construction, London/NY windows, breakout volume, retest and expiry.
- Point-size conversion for GOLD.
- Priority ordering.
- Explicit RR/SL/TP calculations.
- Replay no-lookahead behavior and pending-limit fill behavior.
- BTC regression: E1-E8 behavior remains unchanged.

## Non-goals

- No live order execution is enabled; the current engine remains analysis/signal-only.
- No changes to BTC strategy definitions.
- No removal of existing E1-E8 engines.
- No bypass of H1/M15/M5 data-quality gates.
