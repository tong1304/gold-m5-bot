# V12 Validation

The production signal path is now fixed to the approved architecture:

```text
MARKET DATA
    ↓
REGIME ENGINE
    ↓
TREND / RANGE / TRANSITION
    ↓
E1-E5 / E6-E8 / E3-E4-E7
    ↓
SETUP SCORER
    ↓
ENTRY TRIGGER
    ↓
SETUP ID / STATE
    ↓
INITIAL / RE-ENTRY
    ↓
RISK ENGINE
    ↓
RR / TARGET
    ↓
FINAL SIGNAL
```

## Regime routing

- TREND: E1, E2, E3, E4, E5
- RANGE: E6, E7, E8
- TRANSITION: E3, E4, E7

Regime is a hard gate. A strategy outside its approved regime is never selected by `v11.engine.analyze`.

## Entry and risk gates

1. Closed M5/M15 data must pass data-quality validation.
2. Regime must be classified.
3. Only allowed engines are evaluated.
4. Setup must pass its own structural conditions.
5. Setup score must meet the configured threshold (70/100 by default).
6. A new M5 trigger is required.
7. Setup ID and trigger ID are checked for duplicate/re-entry control.
8. Risk is calculated from structure + ATR.
9. Minimum risk/reward remains 2R.
10. Otherwise the result is `NO_TRADE`.

## Re-entry

A second order for the same setup is allowed only when the setup ID remains compatible and a **new trigger ID** exists. The same setup + same trigger is suppressed. `MAX_REENTRIES_PER_SETUP` defaults to 2 and is configurable.

Live scanning allows a same-setup re-entry even when a prior order from that setup remains open. A different setup remains subject to the existing active-signal lock.

Replay applies the same setup-state and active-signal policy so replay and live share the same decision architecture.

## Performance validation

Win rate is not hard-coded. It must be measured from replay/backtest results with the same data, costs, and resolution policy. Optimize expectancy, drawdown, profit factor, and out-of-sample stability rather than win rate alone.

## Safety

`live_orders_allowed` remains `false`; this repository continues to produce alerts/signals rather than place broker orders automatically.
