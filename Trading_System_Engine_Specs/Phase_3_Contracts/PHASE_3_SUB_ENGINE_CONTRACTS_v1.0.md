# PHASE 3 — SUB-ENGINE DETAILED CONTRACTS v1.0

Status: Phase 3 Draft / Contract Definition
Scope: 58 Sub-Engines under ENGINE 01–09
Production Code: NOT IMPLEMENTED
Decision Authority: Sub-Engines are analytical modules only; they do not issue BUY/SELL decisions.

## Global Contract

Every Sub-Engine follows the same interface:

1. INPUT — only declared upstream/market data may be consumed.
2. PROCESSING — deterministic analysis of the declared inputs; no future data or hidden inputs.
3. OUTPUT — structured state/evidence/quality/confidence/reason codes for the parent Engine.
4. GATE — only module-local validity/safety gates; failure does not create an independent trade decision.
5. SCORE — optional quality score; never overrides a hard gate and never becomes a standalone trade score.
6. TRACEABILITY — symbol, timeframe, candle-close timestamp, spec version, input references, output, gate result, score and reason codes.

Global rules:
- No look-ahead.
- No direct BUY/SELL/SHORT/LONG decision.
- No bypass of the parent Engine.
- No duplicated ownership of another Sub-Engine's primary state.
- Parent Engines own cross-sub-engine synthesis.
- Thresholds requiring asset-specific calibration remain implementation/calibration work and are not hard-coded here.

---

# ENGINE 01 — MARKET STATE

## 1A — Data Quality
**INPUT:** OHLCV bars, timestamps, symbol, timeframe, provider metadata, required indicator availability.  
**PROCESSING:** Validate completeness, ordering, duplicates, stale bars, missing/invalid OHLCV and minimum history.  
**OUTPUT:** data_quality_state, completeness, freshness, invalid_fields, reason_codes.  
**GATE:** FAIL when required market data is missing, malformed, stale or non-monotonic.  
**SCORE:** Data quality score 0–100 representing reliability only.  
**TRACEABILITY:** bar range, source metadata, validation rules/version, failed checks.
**NON-RESPONSIBILITY:** Does not classify trend, regime or trade direction.

## 1B — Volatility State
**INPUT:** OHLC ranges, ATR/realized volatility inputs, historical volatility baseline from the same symbol/timeframe.  
**PROCESSING:** Measure current volatility relative to its historical baseline and classify volatility state.  
**OUTPUT:** volatility_state = NORMAL/LOW/HIGH or calibrated equivalent, volatility_metrics, confidence.  
**GATE:** FAIL only when volatility inputs are unavailable/invalid.  
**SCORE:** Volatility-state confidence/quality 0–100.  
**TRACEABILITY:** lookbacks, ATR/volatility values, baseline reference, timestamp.
**NON-RESPONSIBILITY:** Does not decide breakout, regime or trade direction.

## 1C — Trend State
**INPUT:** Price series, directional structure features, EMA/slope or equivalent trend evidence, volatility-normalized movement.  
**PROCESSING:** Classify directional state and strength from market-state evidence without applying regime policy.  
**OUTPUT:** trend_state = UP/DOWN/NEUTRAL, direction_strength, confidence, evidence.  
**GATE:** FAIL when required trend evidence is insufficient.  
**SCORE:** Trend evidence quality 0–100.  
**TRACEABILITY:** exact features/lookbacks and candle-close reference.
**NON-RESPONSIBILITY:** Does not label the behavioral regime or approve a setup.

## 1D — Range State
**INPUT:** Recent highs/lows, price dispersion, repeated boundary reactions and volatility context.  
**PROCESSING:** Detect whether price is behaving as a bounded state rather than merely measuring one range.  
**OUTPUT:** range_state = BOUNDED/NOT_BOUNDED/UNCERTAIN, boundaries, confidence.  
**GATE:** FAIL when insufficient observations prevent reliable boundary identification.  
**SCORE:** Range-quality score 0–100.  
**TRACEABILITY:** boundary calculations, lookback, reactions counted.
**NON-RESPONSIBILITY:** Does not create range-trading entries.

## 1E — Compression
**INPUT:** Range/ATR/realized-volatility contraction features.  
**PROCESSING:** Detect sustained contraction relative to the symbol/timeframe baseline.  
**OUTPUT:** compression_state, compression_intensity, duration, confidence.  
**GATE:** FAIL only on invalid inputs; absence of compression is a valid negative result, not an error.  
**SCORE:** Compression evidence quality 0–100.  
**TRACEABILITY:** contraction metrics, baseline and duration.
**NON-RESPONSIBILITY:** Does not predict breakout direction.

## 1F — Expansion
**INPUT:** Current range/ATR/volatility and expansion relative to prior baseline.  
**PROCESSING:** Detect acceleration from a lower-volatility state into an expanded state.  
**OUTPUT:** expansion_state, magnitude, persistence, confidence.  
**GATE:** FAIL only on invalid/missing inputs.  
**SCORE:** Expansion evidence quality 0–100.  
**TRACEABILITY:** current vs baseline metrics and event candle.
**NON-RESPONSIBILITY:** Does not decide whether expansion is a valid trade breakout.

## 1G — Transition
**INPUT:** 1B–1F state outputs plus recent state history.  
**PROCESSING:** Detect change between market states and classify transition phase.  
**OUTPUT:** state_transition, from_state, to_state, transition_strength, confidence.  
**GATE:** FAIL when prior/current states are unavailable or contradictory.  
**SCORE:** Transition evidence quality 0–100.  
**TRACEABILITY:** previous/current states and transition timestamp.
**NON-RESPONSIBILITY:** Does not perform E2 behavioral regime classification; E2 owns regime interpretation.

---

# ENGINE 02 — MARKET REGIME

## 2A — Trend Regime
**INPUT:** E1 trend/volatility/state outputs, directional persistence and structure evidence.  
**PROCESSING:** Interpret market behavior as a trend regime, including persistence and tradability characteristics.  
**OUTPUT:** trend_regime_state, direction, persistence, confidence.  
**GATE:** FAIL when regime evidence is insufficient or internally contradictory.  
**SCORE:** Regime classification quality 0–100.  
**TRACEABILITY:** upstream E1 states, regime evidence and timestamp.
**NON-RESPONSIBILITY:** Does not recompute E1 trend state.

## 2B — Range Regime
**INPUT:** E1 range/volatility states, boundary behavior and persistence.  
**PROCESSING:** Determine whether bounded behavior constitutes a meaningful range regime.  
**OUTPUT:** range_regime_state, range_quality, boundaries_reference, confidence.  
**GATE:** FAIL when range evidence is insufficient.  
**SCORE:** Range-regime quality 0–100.  
**TRACEABILITY:** E1 references, boundary evidence and duration.
**NON-RESPONSIBILITY:** Does not create range entries.

## 2C — Mean-Reversion Behavior
**INPUT:** Distance from equilibrium/value references, reversion history, volatility and rejection behavior.  
**PROCESSING:** Measure tendency for price to revert toward value after extension.  
**OUTPUT:** mean_reversion_state, reversion_strength, equilibrium_reference, confidence.  
**GATE:** FAIL when equilibrium/reversion evidence is unavailable.  
**SCORE:** Behavioral evidence quality 0–100.  
**TRACEABILITY:** equilibrium method, distance, historical reversion observations.
**NON-RESPONSIBILITY:** Does not issue mean-reversion entries.

## 2D — Breakout Regime
**INPUT:** Compression/expansion states, boundary events, volatility expansion and acceptance evidence.  
**PROCESSING:** Classify whether the market is behaving as a breakout-capable regime.  
**OUTPUT:** breakout_regime_state, expansion_context, boundary_reference, confidence.  
**GATE:** FAIL when boundary/expansion inputs are insufficient.  
**SCORE:** Breakout-regime quality 0–100.  
**TRACEABILITY:** boundary, expansion and compression references.
**NON-RESPONSIBILITY:** Does not validate a specific breakout entry.

## 2E — Regime Phase
**INPUT:** 2A–2D regime states plus regime history.  
**PROCESSING:** Classify lifecycle phase such as emerging, mature, weakening or ending.  
**OUTPUT:** regime_phase, phase_strength, confidence.  
**GATE:** FAIL on missing/inconsistent regime history.  
**SCORE:** Phase-classification quality 0–100.  
**TRACEABILITY:** prior/current regime states and phase transition evidence.
**NON-RESPONSIBILITY:** Does not replace 1G physical-state transition detection.

## 2F — Regime Transition
**INPUT:** E1 1G transition plus E2 current/prior regime states.  
**PROCESSING:** Translate state transition into behavioral-regime transition only after regime evidence changes.  
**OUTPUT:** regime_transition, from_regime, to_regime, transition_confidence.  
**GATE:** FAIL when transition cannot be distinguished from noise.  
**SCORE:** Regime-transition quality 0–100.  
**TRACEABILITY:** prior/current regime and E1 transition reference.
**NON-RESPONSIBILITY:** Does not redefine physical state transition.

---

# ENGINE 03 — MARKET STRUCTURE

## 3A — Swing Detection
**INPUT:** OHLC price sequence and structure lookback rules.  
**PROCESSING:** Identify confirmed swing highs/lows using causal, closed-candle rules.  
**OUTPUT:** swing_points, swing_type, strength, confirmation status.  
**GATE:** FAIL when insufficient bars exist for confirmation.  
**SCORE:** Swing-confirmation quality 0–100.  
**TRACEABILITY:** pivot window, source bars and confirmation candle.
**NON-RESPONSIBILITY:** Does not classify overall structure.

## 3B — Structure Classification
**INPUT:** Confirmed swings from 3A.  
**PROCESSING:** Classify HH/HL/LH/LL and structural directional pattern.  
**OUTPUT:** structure_state, sequence, direction, confidence.  
**GATE:** FAIL when confirmed swing sequence is insufficient.  
**SCORE:** Structure-quality score 0–100.  
**TRACEABILITY:** swing IDs and sequence used.
**NON-RESPONSIBILITY:** Does not detect liquidity sweeps.

## 3C — Break of Structure
**INPUT:** 3A/3B confirmed structural levels and closed-candle price.  
**PROCESSING:** Detect a confirmed break of a defined structural level.  
**OUTPUT:** BOS_event, direction, broken_level, confirmation_state.  
**GATE:** FAIL when level is unconfirmed or break is not confirmed.  
**SCORE:** BOS quality 0–100.  
**TRACEABILITY:** level ID, break candle and confirmation evidence.
**NON-RESPONSIBILITY:** Does not label a liquidity sweep.

## 3D — Structural Failure
**INPUT:** Active structure from 3B and subsequent confirmed price behavior.  
**PROCESSING:** Detect failure of previously established structural expectations.  
**OUTPUT:** structural_failure, failed_structure_id, direction, confidence.  
**GATE:** FAIL when no valid prior structure exists.  
**SCORE:** Failure evidence quality 0–100.  
**TRACEABILITY:** prior structure, failure event and confirmation.
**NON-RESPONSIBILITY:** Does not model trade-risk invalidation.

## 3E — Structure Strength
**INPUT:** Swing quality, persistence, displacement, retests and structural consistency.  
**PROCESSING:** Quantify strength of the current structural pattern.  
**OUTPUT:** structure_strength, supporting_factors, confidence.  
**GATE:** FAIL when insufficient structure exists.  
**SCORE:** Structure-strength score 0–100.  
**TRACEABILITY:** contributing structure features.
**NON-RESPONSIBILITY:** Does not create directional decisions.

## 3F — Internal vs External Structure
**INPUT:** Nested swing hierarchy and structure levels.  
**PROCESSING:** Separate internal/local structure from external/major structure.  
**OUTPUT:** structure_scope, internal_levels, external_levels, confidence.  
**GATE:** FAIL when hierarchy cannot be established.  
**SCORE:** Hierarchy quality 0–100.  
**TRACEABILITY:** level IDs and hierarchy rules.
**NON-RESPONSIBILITY:** Does not decide which structure should be traded.

---

# ENGINE 04 — LIQUIDITY

## 4A — Liquidity Zone Detection
**INPUT:** Confirmed highs/lows, equal/similar levels, obvious resting-order areas and structural references.  
**PROCESSING:** Identify candidate liquidity zones.  
**OUTPUT:** liquidity_zones, side, price bounds, strength, confidence.  
**GATE:** FAIL when no valid reference structure exists.  
**SCORE:** Zone-quality score 0–100.  
**TRACEABILITY:** source levels, clustering rule and timestamp.
**NON-RESPONSIBILITY:** Does not declare a sweep.

## 4B — Sweep Detection
**INPUT:** 4A zones and closed-candle excursion/reclaim behavior.  
**PROCESSING:** Detect price taking a liquidity zone and evaluate whether the event qualifies as a sweep.  
**OUTPUT:** sweep_event, zone_id, direction, excursion, reclaim_state.  
**GATE:** FAIL when zone is unconfirmed or event lacks required evidence.  
**SCORE:** Sweep quality 0–100.  
**TRACEABILITY:** zone, excursion candle and reclaim evidence.
**NON-RESPONSIBILITY:** Does not become a reversal trigger.

## 4C — Reaction / Rejection
**INPUT:** Liquidity event/zone, candle reaction, displacement and close location.  
**PROCESSING:** Measure reaction quality after interaction with liquidity.  
**OUTPUT:** reaction_state, rejection_strength, direction, confidence.  
**GATE:** FAIL when reaction evidence is incomplete.  
**SCORE:** Reaction quality 0–100.  
**TRACEABILITY:** zone/event reference and reaction bars.
**NON-RESPONSIBILITY:** Does not own entry trigger logic.

## 4D — Acceptance
**INPUT:** Liquidity-zone interaction, closes, persistence and post-event price behavior.  
**PROCESSING:** Determine whether price is accepted beyond/within the zone rather than merely wicking through it.  
**OUTPUT:** acceptance_state, accepted_area, persistence, confidence.  
**GATE:** FAIL when insufficient post-event observation exists.  
**SCORE:** Acceptance quality 0–100.  
**TRACEABILITY:** closes and persistence window.
**NON-RESPONSIBILITY:** Does not determine trade direction.

## 4E — Reclaim / Failed Break
**INPUT:** Broken level, subsequent closes, 4A/4B liquidity references.  
**PROCESSING:** Detect reclaim of a level or failure of an apparent break.  
**OUTPUT:** reclaim_state, failed_break_state, level_id, confidence.  
**GATE:** FAIL when prior level/break is unconfirmed.  
**SCORE:** Reclaim/failure quality 0–100.  
**TRACEABILITY:** level, break candle and reclaim/failure evidence.
**NON-RESPONSIBILITY:** Does not replace 3C BOS.

## 4F — Liquidity Strength / Quality
**INPUT:** Zone age, repeated reactions, clustering, proximity and event history.  
**PROCESSING:** Rank liquidity relevance and quality.  
**OUTPUT:** liquidity_quality, strength, supporting_features.  
**GATE:** FAIL when zone identity is invalid.  
**SCORE:** Liquidity-quality score 0–100.  
**TRACEABILITY:** zone ID and contributing factors.
**NON-RESPONSIBILITY:** Does not choose entry or target by itself.

---

# ENGINE 05 — LOCATION / VALUE

## 5A — Equilibrium / Value
**INPUT:** Price history and declared equilibrium/value model.  
**PROCESSING:** Calculate current value/equilibrium reference and price distance from it.  
**OUTPUT:** value_reference, distance, value_state, confidence.  
**GATE:** FAIL when value model inputs are invalid.  
**SCORE:** Value-location quality 0–100.  
**TRACEABILITY:** model version, inputs and reference price.
**NON-RESPONSIBILITY:** Does not decide mean-reversion entry.

## 5B — Structural Location
**INPUT:** E3 structure levels and current price.  
**PROCESSING:** Determine whether price is at/near structurally meaningful support, resistance or structural zone.  
**OUTPUT:** structural_location, zone_id, distance, confidence.  
**GATE:** FAIL when structure reference is unavailable.  
**SCORE:** Structural-location quality 0–100.  
**TRACEABILITY:** structure IDs and distance calculation.
**NON-RESPONSIBILITY:** Does not classify structure itself.

## 5C — Liquidity Location
**INPUT:** E4 liquidity zones and current price.  
**PROCESSING:** Determine proximity/location relative to relevant liquidity.  
**OUTPUT:** liquidity_location, nearest_zone, distance, side, confidence.  
**GATE:** FAIL when relevant liquidity reference is absent.  
**SCORE:** Liquidity-location quality 0–100.  
**TRACEABILITY:** zone ID, distance and timestamp.
**NON-RESPONSIBILITY:** Does not detect the liquidity event.

## 5D — Extension
**INPUT:** Current price, value/equilibrium and structural impulse reference.  
**PROCESSING:** Measure whether price is materially extended from its reference.  
**OUTPUT:** extension_state, magnitude, reference, confidence.  
**GATE:** FAIL when reference is invalid.  
**SCORE:** Extension-evidence quality 0–100.  
**TRACEABILITY:** reference and normalized distance.
**NON-RESPONSIBILITY:** Does not assume reversal because of extension.

## 5E — Available Space
**INPUT:** Current price, nearby structural/liquidity obstacles and declared directional path.  
**PROCESSING:** Estimate usable price space before the next meaningful obstacle.  
**OUTPUT:** available_space, nearest_obstacle, space_ratio, confidence.  
**GATE:** FAIL when obstacle map is incomplete.  
**SCORE:** Space quality 0–100.  
**TRACEABILITY:** obstacle IDs and distance calculations.
**NON-RESPONSIBILITY:** Does not set the final target or RR.

## 5F — Location Quality
**INPUT:** 5A–5E outputs.  
**PROCESSING:** Synthesize location evidence into a location-quality assessment without making a trade decision.  
**OUTPUT:** location_quality, favorable/unfavorable factors, confidence.  
**GATE:** FAIL when required location components are unavailable.  
**SCORE:** Location-quality score 0–100.  
**TRACEABILITY:** component IDs and contributions.
**NON-RESPONSIBILITY:** Does not issue setup approval.

---

# ENGINE 06 — TRADE SETUP

## 6A — Setup Context
**INPUT:** E1–E5 states relevant to the setup family.  
**PROCESSING:** Define the contextual environment in which a setup may form.  
**OUTPUT:** setup_context, compatible/blocked archetypes, confidence.  
**GATE:** FAIL when required context is invalid.  
**SCORE:** Context quality 0–100.  
**TRACEABILITY:** upstream state references.
**NON-RESPONSIBILITY:** Does not trigger an entry.

## 6B — Setup Archetype
**INPUT:** Context, structure, liquidity, location and regime evidence.  
**PROCESSING:** Identify the applicable setup archetype from the declared library.  
**OUTPUT:** setup_archetype, direction_candidate, evidence, confidence.  
**GATE:** FAIL when no defined archetype matches the evidence.  
**SCORE:** Archetype-fit score 0–100.  
**TRACEABILITY:** archetype rule/version and evidence IDs.
**NON-RESPONSIBILITY:** Does not execute or approve a trade.

## 6C — Setup Formation State Machine
**INPUT:** Setup archetype and sequential setup observations.  
**PROCESSING:** Track setup lifecycle: absent → forming → mature/ready → invalid/expired, using causal transitions.  
**OUTPUT:** setup_state, state_age, transition_event, confidence.  
**GATE:** FAIL on invalid state transition.  
**SCORE:** Formation quality 0–100.  
**TRACEABILITY:** state history and transition timestamps.
**NON-RESPONSIBILITY:** Does not detect the final entry trigger.

## 6D — Setup Invalidation
**INPUT:** Setup definition, setup-specific invalidation conditions and current market evidence.  
**PROCESSING:** Determine whether the setup thesis remains structurally valid.  
**OUTPUT:** setup_validity, invalidation_reason, invalidation_level/reference.  
**GATE:** FAIL when setup-specific invalidation occurs.  
**SCORE:** Setup-integrity score 0–100.  
**TRACEABILITY:** setup ID, invalidation rule and event.
**NON-RESPONSIBILITY:** Does not calculate portfolio/trade risk invalidation; E8 owns risk model.

## 6E — Setup Quality
**INPUT:** 6A–6D evidence and supporting E1–E5 outputs.  
**PROCESSING:** Evaluate setup coherence, evidence completeness and quality.  
**OUTPUT:** setup_quality, strengths, weaknesses, confidence.  
**GATE:** FAIL when mandatory setup evidence is missing.  
**SCORE:** Setup-quality score 0–100.  
**TRACEABILITY:** component contributions and rule version.
**NON-RESPONSIBILITY:** Does not replace E9 final decision.

## 6F — Setup Maturity
**INPUT:** 6C state history, elapsed bars and required formation events.  
**PROCESSING:** Determine whether setup is premature, mature, stale or expired.  
**OUTPUT:** maturity_state, age, missing_events, confidence.  
**GATE:** FAIL when setup is expired or violates maturity rules.  
**SCORE:** Maturity quality 0–100.  
**TRACEABILITY:** formation timeline and required-event checklist.
**NON-RESPONSIBILITY:** Does not become an entry trigger.

---

# ENGINE 07 — ENTRY CONFIRMATION

## 7A — Trigger Detection
**INPUT:** Valid setup from E6, trigger definition, closed-candle price/volume/volatility evidence.  
**PROCESSING:** Detect whether the declared trigger event has occurred.  
**OUTPUT:** trigger_event, direction, trigger_timestamp, confidence.  
**GATE:** FAIL when no valid trigger or setup is invalid.  
**SCORE:** Trigger-quality score 0–100.  
**TRACEABILITY:** setup ID, trigger rule and candle evidence.
**NON-RESPONSIBILITY:** Does not select a setup archetype.

## 7B — Trigger Quality
**INPUT:** 7A trigger plus displacement, close quality, volatility and context.  
**PROCESSING:** Grade trigger strength and cleanliness.  
**OUTPUT:** trigger_quality, supporting_factors, confidence.  
**GATE:** FAIL when trigger is malformed or contradicts setup.  
**SCORE:** Trigger-quality score 0–100.  
**TRACEABILITY:** trigger metrics and contributing factors.
**NON-RESPONSIBILITY:** Does not independently create a setup.

## 7C — Follow-through
**INPUT:** Trigger event and subsequent closed-candle behavior within the declared confirmation window.  
**PROCESSING:** Measure continuation/follow-through after the trigger.  
**OUTPUT:** follow_through_state, persistence, strength, confidence.  
**GATE:** FAIL when required confirmation window is invalid or trigger has clearly failed.  
**SCORE:** Follow-through quality 0–100.  
**TRACEABILITY:** trigger ID and confirmation bars.
**NON-RESPONSIBILITY:** Does not create an independent entry signal.

## 7D — Failure / Invalidation
**INPUT:** Trigger/confirmation state and declared failure conditions.  
**PROCESSING:** Detect failure of the entry confirmation itself.  
**OUTPUT:** confirmation_failure, reason, failed_trigger_id, confidence.  
**GATE:** FAIL when confirmation is invalidated.  
**SCORE:** Failure-detection confidence 0–100.  
**TRACEABILITY:** trigger ID, failure event and candle.
**NON-RESPONSIBILITY:** Does not invalidate the entire setup unless the parent E6 contract says the event propagates.

## 7E — Execution Conditions
**INPUT:** Valid confirmation state, current price, spread/slippage/market-session data if available.  
**PROCESSING:** Evaluate whether technical execution conditions are currently usable.  
**OUTPUT:** execution_condition_state, blocking_factors, confidence.  
**GATE:** FAIL on declared execution-quality blockers.  
**SCORE:** Execution-condition quality 0–100.  
**TRACEABILITY:** market conditions and timestamp.
**NON-RESPONSIBILITY:** Does not perform order placement.

## 7F — Confirmation Quality
**INPUT:** 7A–7E outputs.  
**PROCESSING:** Synthesize confirmation evidence into a quality assessment.  
**OUTPUT:** confirmation_quality, evidence_summary, confidence.  
**GATE:** FAIL when mandatory confirmation components fail.  
**SCORE:** Confirmation-quality score 0–100.  
**TRACEABILITY:** component scores and gate states.
**NON-RESPONSIBILITY:** Does not make the master decision.

---

# ENGINE 08 — RISK / REWARD

## 8A — Invalidation Model
**INPUT:** Valid setup/confirmation, structural invalidation references and current market structure.  
**PROCESSING:** Define the trade-risk invalidation reference appropriate to the contemplated position.  
**OUTPUT:** risk_invalidation_model, invalidation_price/reference, rationale.  
**GATE:** FAIL when a defensible invalidation cannot be defined.  
**SCORE:** Invalidation-model quality 0–100.  
**TRACEABILITY:** structure/setup references and model version.
**NON-RESPONSIBILITY:** Does not decide whether the setup itself is valid; E6 owns that.

## 8B — Stop Placement
**INPUT:** 8A invalidation, entry reference, volatility and execution constraints.  
**PROCESSING:** Convert invalidation into a feasible stop placement without weakening the invalidation thesis.  
**OUTPUT:** stop_price, stop_distance, stop_method, confidence.  
**GATE:** FAIL when stop cannot satisfy risk/market constraints.  
**SCORE:** Stop-quality score 0–100.  
**TRACEABILITY:** invalidation ID, volatility input and placement method.
**NON-RESPONSIBILITY:** Does not choose position size.

## 8C — Target / Liquidity Objective
**INPUT:** Available space, structural/liquidity objectives, entry reference and direction candidate.  
**PROCESSING:** Identify defensible target/objective candidates from market structure and liquidity.  
**OUTPUT:** target_candidates, selected_objective_reference, distance, confidence.  
**GATE:** FAIL when no defensible objective exists.  
**SCORE:** Target-quality score 0–100.  
**TRACEABILITY:** obstacle/liquidity IDs and distance calculations.
**NON-RESPONSIBILITY:** Does not approve RR or final trade.

## 8D — R-Multiple
**INPUT:** Entry reference, stop from 8B and target/objective from 8C.  
**PROCESSING:** Calculate risk unit and expected reward multiple for each candidate objective.  
**OUTPUT:** R_multiple, risk_distance, reward_distance, candidate_id.  
**GATE:** FAIL when risk distance is zero/invalid or objective is invalid.  
**SCORE:** RR quality 0–100 based on declared calibration policy.  
**TRACEABILITY:** exact price references and formula version.
**NON-RESPONSIBILITY:** Does not override other risk gates.

## 8E — Position Size
**INPUT:** Account risk budget supplied by risk policy, stop distance and instrument contract specification.  
**PROCESSING:** Calculate position size consistent with allowed risk.  
**OUTPUT:** position_size, estimated_risk, sizing_method.  
**GATE:** FAIL when account/risk/instrument inputs are unavailable or size exceeds limits.  
**SCORE:** Sizing-validity score 0–100.  
**TRACEABILITY:** risk budget, stop distance, contract specs and calculation version.
**NON-RESPONSIBILITY:** Does not decide whether the trade is desirable.

## 8F — Exposure Limits
**INPUT:** Proposed position size, existing exposure, correlated exposure if explicitly provided, portfolio limits.  
**PROCESSING:** Evaluate aggregate exposure against declared limits.  
**OUTPUT:** exposure_state, current_exposure, proposed_exposure, limit_breaches.  
**GATE:** FAIL on hard exposure-limit breach.  
**SCORE:** Exposure-quality score 0–100.  
**TRACEABILITY:** exposure snapshot and limit policy version.
**NON-RESPONSIBILITY:** Does not generate directional signals.

## 8G — Risk Gate
**INPUT:** 8A–8F risk outputs.  
**PROCESSING:** Determine whether the proposed risk package is internally feasible and policy-compliant.  
**OUTPUT:** risk_gate_state, blocking_reasons, risk_summary.  
**GATE:** FAIL on any hard risk-policy violation.  
**SCORE:** Risk-package quality 0–100.  
**TRACEABILITY:** all risk component states and policy version.
**NON-RESPONSIBILITY:** Does not issue the system-level final decision; E9 owns that.

---

# ENGINE 09 — MASTER DECISION / EXECUTION

## 9A — Data Gate
**INPUT:** E1 data-quality state and required upstream freshness/completeness statuses.  
**PROCESSING:** Verify that the complete decision input set is trustworthy enough for master evaluation.  
**OUTPUT:** data_gate_state, missing/invalid dependencies.  
**GATE:** FAIL on required data-quality failure.  
**SCORE:** Data-readiness quality 0–100.  
**TRACEABILITY:** dependency list, timestamps and versions.
**NON-RESPONSIBILITY:** Does not recompute E1 data quality.

## 9B — Context Gate
**INPUT:** E1–E5 state/regime/structure/liquidity/location outputs.  
**PROCESSING:** Verify contextual compatibility and absence of hard contextual blockers.  
**OUTPUT:** context_gate_state, blockers, context_summary.  
**GATE:** FAIL on declared context incompatibility.  
**SCORE:** Context-readiness quality 0–100.  
**TRACEABILITY:** upstream component states and gate rules.
**NON-RESPONSIBILITY:** Does not replace E2–E5 analysis.

## 9C — Setup Gate
**INPUT:** E6 setup state, validity, quality and maturity.  
**PROCESSING:** Verify that a setup exists, is valid and satisfies master setup prerequisites.  
**OUTPUT:** setup_gate_state, setup_reference, blockers.  
**GATE:** FAIL when setup prerequisites are not satisfied.  
**SCORE:** Setup-readiness quality 0–100.  
**TRACEABILITY:** setup ID and E6 component states.
**NON-RESPONSIBILITY:** Does not create a setup.

## 9D — Confirmation Gate
**INPUT:** E7 trigger, quality, follow-through, failure and execution-condition states.  
**PROCESSING:** Verify confirmation prerequisites as a master gate.  
**OUTPUT:** confirmation_gate_state, trigger_reference, blockers.  
**GATE:** FAIL when mandatory confirmation fails.  
**SCORE:** Confirmation-readiness quality 0–100.  
**TRACEABILITY:** E7 component references.
**NON-RESPONSIBILITY:** Does not detect the trigger itself.

## 9E — Risk Gate
**INPUT:** E8 complete risk package and policy status.  
**PROCESSING:** Verify master-level risk acceptability and hard constraints.  
**OUTPUT:** master_risk_gate_state, blockers, risk_summary.  
**GATE:** FAIL on any master risk violation.  
**SCORE:** Risk-readiness quality 0–100.  
**TRACEABILITY:** E8 gate and component references.
**NON-RESPONSIBILITY:** Does not recalculate E8 risk models unless contract explicitly requires validation.

## 9F — Execution Gate
**INPUT:** Valid master context/setup/confirmation/risk states plus execution conditions.  
**PROCESSING:** Verify that order execution is operationally permissible at the decision timestamp.  
**OUTPUT:** execution_gate_state, execution_constraints, executable_reference.  
**GATE:** FAIL on operational/execution blocker.  
**SCORE:** Execution-readiness quality 0–100.  
**TRACEABILITY:** execution snapshot, timestamp and constraints.
**NON-RESPONSIBILITY:** Does not place the order itself.

## 9G — Final Decision
**INPUT:** 9A–9F gate states and required evidence.  
**PROCESSING:** Aggregate master gates into a system-level decision state. A positive decision is possible only when all required hard gates pass; otherwise the result is NO_TRADE/BLOCKED with reason codes.  
**OUTPUT:** final_decision, decision_state, direction_reference_if_already_supported, decision_reasons, decision_confidence.  
**GATE:** Master decision gate; any required hard-gate failure prevents an executable decision.  
**SCORE:** Final decision quality may summarize upstream quality but cannot override a hard gate.  
**TRACEABILITY:** complete gate chain, component versions, timestamp and decision hash/reference.
**NON-RESPONSIBILITY:** Does not invent missing evidence or bypass upstream gates.

## 9H — Decision Logging
**INPUT:** 9A–9G outputs and complete decision context.  
**PROCESSING:** Serialize the decision audit record for replay, debugging, statistics and compliance.  
**OUTPUT:** immutable decision_log_record, schema_version, event_id.  
**GATE:** FAIL logging validation if required fields are absent; logging failure must not silently change the decision.  
**SCORE:** Logging completeness/quality 0–100.  
**TRACEABILITY:** event ID, parent decision ID, timestamps, spec versions and serialized inputs/outputs.
**NON-RESPONSIBILITY:** Never changes the decision after 9G.

---

# Phase 2 Boundary Locks Carried Into Phase 3

1. 1C Trend State = physical/directional state; 2A Trend Regime = behavioral regime interpretation.
2. 1G Transition = physical market-state transition; 2F Regime Transition = behavioral-regime transition.
3. 1D Range State = bounded state; 2B Range Regime = behavior/tradability interpretation of a range.
4. 1E/1F Compression/Expansion = physical volatility states; 2D Breakout Regime = behavioral breakout context.
5. 3C BOS = structural break; 4B Sweep = liquidity-taking event; 4E = reclaim/failed-break behavior.
6. 4C Reaction/Rejection = post-liquidity reaction evidence; 7A = entry-trigger detection.
7. 5E Available Space = location/obstacle geometry; 8C = target/objective selection.
8. 6D Setup Invalidation = setup thesis validity; 8A = trade-risk invalidation model.
9. 6F Setup Maturity = setup lifecycle; 7A = trigger event.
10. 7D Confirmation Failure = entry-confirmation failure; 6D remains responsible for setup validity.
11. 8G Risk Gate = E8 internal risk-package feasibility; 9E = E9 master risk gate.
12. 9F Execution Gate = execution readiness; 9G = system-level final decision; 9H only logs.

# Phase 3 Exit Criteria

Phase 3 is complete only when every Sub-Engine has:
- declared input ownership;
- deterministic processing scope;
- explicit output contract;
- explicit local gate semantics;
- score semantics where applicable;
- traceability fields;
- explicit non-responsibilities;
- no ownership collision with another Sub-Engine;
- no direct BUY/SELL authority.

This document is a contract layer for Phase 3. It does not authorize production implementation and does not replace the Phase 1 architecture or the Phase 2 audit.
