# PHASE 4 — TRADING SYSTEM ENGINE SPECIFICATION v1.1

Status: Phase 4 Specification Lock
Scope: ENGINE 01–09 and 58 Sub-Engines
Production Code: NOT IMPLEMENTED / NOT ACTIVATED

## 1. Purpose
This specification consolidates Phase 1 Architecture, Phase 2 duplication/conflict audit, and Phase 3 Sub-Engine contracts into the v1.1 specification baseline.

## 2. Locked Architecture
Pipeline:
Market Data → E1 Market State → E2 Market Regime → E3 Market Structure → E4 Liquidity → E5 Location/Value → E6 Trade Setup → E7 Entry Confirmation → E8 Risk/Reward → E9 Master Decision/Execution.

Sub-Engines are analytical specialists. They provide evidence/state/quality/confidence and local validity information to their parent Engine. They do not issue independent BUY/SELL decisions and cannot bypass parent contracts.

## 3. Global Contract
Every Sub-Engine MUST define:
1. INPUT
2. PROCESSING
3. OUTPUT
4. GATE
5. SCORE
6. TRACEABILITY

Every Sub-Engine MUST also declare NON-RESPONSIBILITIES and primary ownership.

Global constraints:
- No look-ahead or future-bar information.
- Inputs are limited to declared market/upstream inputs.
- Hard GATE and SCORE are separate mechanisms.
- SCORE cannot override a failed hard GATE.
- Sub-Engine scores are quality/evidence scores, not standalone trade scores.
- Cross-Sub-Engine synthesis belongs to the Parent Engine.
- E9 owns system-level final decision.
- Numerical thresholds requiring asset-specific calibration are deferred to implementation/calibration and are not silently hard-coded into Phase 4.

## 4. Boundary Locks from Phase 2
### 4.1 Trend State vs Trend Regime
1C Trend State owns observable trend state. 2A Trend Regime owns behavioral regime interpretation. 2A must consume 1C evidence rather than independently redefining the same primary state.

### 4.2 State Transition vs Regime Transition
1G Transition detects market-state transition. 2F Regime Transition detects behavioral-regime transition. Neither may claim ownership of the other layer.

### 4.3 Range State vs Range Regime
1D Range State describes observable range conditions. 2B Range Regime interprets whether market behavior is range-dominant.

### 4.4 Compression/Expansion vs Breakout Regime
1E/1F classify volatility state. 2D evaluates breakout-regime behavior. Compression/expansion is evidence, not itself a breakout decision.

### 4.5 Structure vs Liquidity Events
3C BOS owns structural break classification. 4B Sweep owns liquidity sweep detection. 4E owns failed-break/reclaim behavior. A single price event may provide evidence to multiple modules but ownership must remain distinct.

### 4.6 Reaction/Rejection vs Entry Trigger
4C detects liquidity reaction/rejection. 7A determines whether a valid entry trigger is present using its declared confirmation inputs. 4C must not issue an entry decision.

### 4.7 Available Space vs Target
5E estimates tradable/structural space. 8C selects the risk/target objective within the risk engine. 5E does not set final TP.

### 4.8 Setup Invalidation vs Risk Invalidation
6D determines whether the setup remains structurally valid. 8A defines the trade risk invalidation model. 6D does not calculate position risk; 8A does not redefine setup formation.

### 4.9 Setup Maturity vs Trigger
6F describes setup development/maturity. 7A determines trigger occurrence. A mature setup is not automatically an entry.

### 4.10 Confirmation Failure vs Setup Invalidation
7D owns failure of the confirmation/trigger sequence. 6D owns setup invalidation. Failure of a trigger must not silently redefine setup invalidation criteria.

### 4.11 Risk Gate vs Master Risk Gate
8G is the Risk Engine's internal feasibility gate. 9E is the Master Decision Engine's risk gate that evaluates the complete upstream decision package. 8G cannot produce a final trade decision.

### 4.12 Execution Gate vs Final Decision
9F validates execution readiness. 9G owns the final system-level decision. 9H records the decision and evidence; it cannot modify the decision.

## 5. Decision Authority
Only ENGINE 09 may synthesize the complete upstream package into a system-level final decision state. Sub-Engines and Engines 01–08 must not independently bypass the E9 contract.

## 6. Asset Separation
The architecture is asset-agnostic at contract level. GOLD/XAU and BTC must not share hidden strategy assumptions or calibration values. Asset-specific thresholds, tolerances and calibration belong to a later implementation/calibration layer.

## 7. Execution Safety
The v1.1 specification is documentation only. It does not activate, modify, import, or replace existing production trading logic. Production integration requires a separate Phase 5 implementation and verification process.

## 8. Traceability Minimum
Every emitted Sub-Engine result must be traceable to symbol, timeframe, candle-close timestamp, specification version, declared input references, output state/evidence, gate result, score when applicable, and reason codes.

## 9. Phase 4 Acceptance Criteria
- 9 Main Engines defined.
- 58 Sub-Engines defined.
- Phase 2 duplication/conflict audit incorporated.
- 12 critical boundaries explicitly locked.
- Common six-part Sub-Engine contract enforced.
- No independent Sub-Engine BUY/SELL authority.
- No Production Code changes or activation.

## 10. Status
PHASE 4 SPECIFICATION v1.1 = LOCKED FOR PHASE 5 DESIGN.

Phase 5 must begin with implementation planning, interface/schema tests, and verification before any production integration.
