# Professional E1 Test Matrix

## Purpose

E1 is the **Market-State Analyst**. It answers only:

> What is the market doing right now?

The matrix validates professional market-state reasoning independently of E2-E9. A passing E1 test means the classifier obeys its information boundaries and handles coherent regimes, uncertainty, volatility, and conflicts correctly. It does **not** mean future price direction is guaranteed.

## Acceptance matrix

| ID | Scenario | Input condition | Required E1 behavior | Critical assertion |
|---|---|---|---|---|
| E1-01 | Clean bullish trend | Persistent UP price, EMA alignment, coherent structure | TREND_UP | pressure=BULLISH, trend=UP, confirmed |
| E1-02 | Clean bearish trend | Persistent DOWN price, EMA alignment, coherent structure | TREND_DOWN | pressure=BEARISH, trend=DOWN, confirmed |
| E1-03 | Balanced range | Alternating price, low directional efficiency | RANGE | pressure=NEUTRAL |
| E1-04 | Compression | Very small alternating movement and low volatility | COMPRESSION | pressure=NEUTRAL |
| E1-05 | Expansion | Increasing recent volatility/displacement | Volatility state must reflect evidence | no trade state implied |
| E1-06 | Transition | Recent impulse conflicts with prior regime | TRANSITION | transition=PRESENT, trend not confirmed |
| E1-07 | EMA/price conflict | EMA direction disagrees with recent pressure | Conflict preserved | explicit conflict; no forced trend |
| E1-08 | Structure/pressure conflict | Structure disagrees with directional pressure | Conflict preserved | no false confirmed trend |
| E1-09 | Long-horizon conflict | Short-term pressure opposes persistent context | TRANSITION | LONG_HORIZON_CONTEXT_CONFLICT |
| E1-10 | Insufficient history | Fewer than minimum reliable candles | UNCLEAR / INCOMPLETE | confidence=0 |
| E1-11 | Bad OHLC | Invalid candle data | Data anomaly preserved | DATA_QUALITY_ANOMALIES |
| E1-12 | Closed vocabulary | All valid scenarios | Only approved states exported | no unknown public state |
| E1-13 | Ownership | Any valid scenario | E1 describes state only | no decision/entry/risk/execution |
| E1-14 | Determinism | Same input twice | Same output | exact result equality |

## Professional acceptance rules

1. **Data first.** Invalid or insufficient data cannot be treated as reliable market state.
2. **State before direction.** E1 classifies regime; it does not select a trade.
3. **Independent evidence.** EMA relationship, price pressure, structure, persistence, and volatility are evaluated before the final state.
4. **Conflict is information.** Conflicting horizons or dimensions produce explicit conflict/transition rather than forced certainty.
5. **Trend requires coherence.** A directional slope alone is not enough for an established trend.
6. **Transition is not reversal.** E1 must not turn a short impulse into a confirmed new trend.
7. **No setup leakage.** Liquidity, setup selection, entry confirmation, risk, target, position sizing, and execution remain outside E1.
8. **Closed vocabulary.** Public `market_state` must remain within `MARKET_STATES`.
9. **Deterministic reasoning.** Identical inputs must produce identical outputs.
10. **No trade authority.** E1 cannot emit or authorize BUY/SELL/ENTRY/STOP/TARGET/EXECUTE decisions.

## Pass standard

The matrix is a **contract test**, not a profitability test. E1 is accepted only when every matrix test passes and no test requires weakening a professional safety boundary merely to increase the number of classified trends.
