# Production V2 MTF Nine-Engine Coherence Design

## Goal
Reduce contradictory vetoes and preserve valid developing opportunities without weakening risk controls or forcing trades.

## Architecture
M15 is the shared market-context timeframe for E1/E2. M5 is the shared setup/entry timeframe for E3/E4/E5/E7/E8. E6 consumes the M15 context plus M5 evidence and owns the causal trade thesis. E9 consumes the completed E1-E8 evidence and owns only final governance.

## Core Contracts
- One immutable closed-candle snapshot per symbol/evaluation cycle.
- M15 answers context/regime questions; M5 answers setup/entry questions.
- E1 owns regime; E2 owns contextual opportunity; neither owns entry permission.
- E3 owns structure, E4 owns liquidity/auction, E5 owns location/space.
- E6 owns thesis formation and persistence; it may output IDLE, OPPORTUNITY_WATCH, or a real setup thesis.
- E7 can confirm only a surviving E6 thesis and cannot create one.
- E8 evaluates economics only for a surviving E6 thesis.
- E9 vetoes only hard conflicts, invalid thesis/confirmation, or unacceptable economics/risk; it must not invent new blockers.
- WATCHING/WAITING is not equivalent to NO_OPPORTUNITY.
- A surviving thesis is evaluated again on the next closed M5 candle; it is invalidated only when its causal evidence is gone or explicitly contradicted.
- Small cross-engine disagreement is counter-evidence, not automatic veto. Hard directional conflict remains vetoable.
- No threshold relaxation, signal inflation, forced entries, or bootstrap probability presented as historical evidence.

## Lifecycle
IDLE -> WATCHING/WAITING -> READY -> EXECUTED, with INVALIDATED as a terminal branch. Opportunity identity persists across closed M5 candles while the thesis remains alive.

## Binding
Bootstrap surgery must not overwrite the final E6/E8/E9 boundary guards. Runtime installation order must be deterministic and the final pipeline references must point to the guarded analyzers.

## Observability
Every evaluation records the snapshot candle timestamp, source timeframe(s), thesis state, and the first blocking authority. Aggregate telemetry must distinguish E6 thesis loss, E7 confirmation wait, E8 economic rejection, and E9 hard governance veto.

## Safety
This architecture does not promise profitability. It is intended to prevent premature rejection and semantic contradictions while retaining risk gates.
