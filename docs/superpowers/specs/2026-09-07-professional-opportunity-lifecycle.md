# Professional Opportunity Lifecycle Redesign

## Goal
Make Production V2 detect causal market opportunities earlier, preserve them across closed M5 candles, arm only when thesis and economics mature, confirm with setup-specific evidence, and let E9 remain the sole execution authority.

## Design
- E4 is the causal event anchor; E1 is context/counter-evidence, not a universal veto.
- E6 owns the thesis and exposes `WATCH -> THESIS_FORMED -> ARMED` without authorizing execution.
- E7 confirms an existing thesis using setup-family-specific closed-candle proof.
- E8 supports a pre-economic pass and a final economic pass; poor space affects tradeability, not opportunity existence.
- E9 consumes structured lifecycle/economic state and remains the only execution authority.
- A canonical event clock is propagated to E4/E6/E7/E8/E9/lifecycle/alerts.
- Telegram is rendered from the same E9/lifecycle snapshot and explicitly distinguishes WATCH, ARMED, and NO_TRADE.

## Safety invariants
1. Closed M5 candles only; no lookahead.
2. No threshold relaxation solely to increase trade count.
3. E9 cannot authorize execution unless E6 thesis, E7 confirmation, E8 final economics, and execution gates all pass.
4. Structural space cannot erase a valid opportunity; it can block execution economics.
5. A new causal event supersedes an old event; stale event evidence cannot advance confirmation.
