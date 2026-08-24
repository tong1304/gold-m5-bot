# V12 Regime Engine — 8 Strategies

## Approved production architecture

```text
MARKET DATA
    ↓
REGIME ENGINE
    ↓
TREND / RANGE / TRANSITION
    ↓
E1 E2 E3 E4 E5 / E6 E7 E8 / E3 E4 E7
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

## Engine definitions

- **E1 TREND:** EMA20/50/200 + structure + ADX/DMI.
- **E2 TREND PULLBACK:** Impulse → Pullback → Continuation.
- **E3 BREAKOUT:** Range → Break → Expansion.
- **E4 BREAKOUT RETEST:** Break → Retest → Continue.
- **E5 MOMENTUM:** Strong candle + volume + volatility expansion.
- **E6 MEAN REVERSION:** Extreme → rejection → return toward VWAP/mean.
- **E7 LIQUIDITY REVERSAL:** Sweep → rejection → reversal.
- **E8 RANGE:** Range high/low → rejection.

## Regime policy

TREND is reserved for E1-E5. RANGE is reserved for E6-E8. TRANSITION is reserved for E3/E4/E7. This prevents a range strategy from automatically fading a strong trend and prevents trend continuation strategies from being used without trend evidence.

## Scoring policy

The scorer evaluates quality only after the setup and trigger have passed. It is not a substitute for the hard regime or setup gates. A score of 70/100 is the default qualification threshold.

## Re-entry policy

A setup gets a stable Setup ID. Each valid M5 trigger gets a Trigger ID. The first accepted signal is `INITIAL`. A later signal with the same Setup ID but a new Trigger ID is `RE_ENTRY`, subject to `MAX_REENTRIES_PER_SETUP` (default 2). Same Setup ID + same Trigger ID is rejected as a duplicate.

Every re-entry receives a fresh entry, structural/ATR stop, target, and RR calculation.

## Research policy

Thresholds such as ADX 25, volume ratio 1.2/1.5, 1.5 ATR VWAP distance, and score 70 are deterministic starting hypotheses for replay validation. They are not claimed to guarantee a particular win rate. BTC and GOLD must be evaluated separately and out-of-sample.
