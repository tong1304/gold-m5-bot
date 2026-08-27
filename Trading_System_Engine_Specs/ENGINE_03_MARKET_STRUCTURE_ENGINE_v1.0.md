# ENGINE 03 — MARKET STRUCTURE BRAIN v2.1

## PURPOSE
Read how price is structurally behaving and whether the structure supports, contradicts, or is neutral to the opportunity described by E1–E2. E3 is a single professional reasoning brain. It does not authorize or reject a trade.

## SUB-ENGINES
PARKED — 3A–3F are retained as future decomposition concepts only and are NOT separate runtime sub-engines. Current production runtime uses E3 as one integrated brain.

## INPUT
E1–E2 evidence, closed M5 candles, permitted M15/H1 structural context, and M5 price history available to the engine.

## PROCESSING
E3 independently reasons through meaningful swing detection, HH/HL/LH/LL classification, internal versus external structure, close-confirmed Break of Structure (BOS), structural failure/failed acceptance, structure strength, directional alignment, and conflicting evidence. Swing significance is volatility-normalized with ATR so insignificant noise is not promoted to market structure. A wick through a level alone is not a confirmed BOS; a confirmed break requires a candle close beyond a confirmed structural swing. Internal structure may disagree with external structure and that disagreement is preserved explicitly rather than hidden.

## OUTPUT
structure, structure_state, swing_map, internal_structure, external_structure, HH, HL, LH, LL, BOS, bos, BOS_type, bos_level, BOS_candle_index, structural_failure, failure_type, failure_level, strength, structure_strength, directional_bias, structural_bias, recent_high, recent_low, prior_high, prior_low, atr, evidence[], conflicts[], confidence, observations[], reasoning_trace.

## GATE
NONE. E3 never blocks E4–E9. Lack of alignment is information, not a gate failure. Insufficient history is reported as INCOMPLETE only when structure genuinely cannot be analyzed.

## SCORE
Confidence represents structural clarity and evidence strength only. It is NOT a trade score, probability of profit, or execution permission.

## TRACEABILITY
Record closed-candle count, pivot windows, ATR-normalization rule, swing references, structural levels, BOS event candle, failure event, internal/external states, upstream E1/E2 context, conflicts, and reasoning trace.

## RUNTIME DESIGN
The 3A–3F concepts are intentionally consolidated into `professional_e3_brain.py`. They are parked for later decomposition and must not become independent runtime gates or decision makers unless explicitly approved in a future change.

## DECISION BOUNDARY
Structure analysis only.
