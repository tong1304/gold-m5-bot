# ENGINE 03 — MARKET STRUCTURE BRAIN v2.0

## PURPOSE
Read how price is structurally behaving and whether the structure supports, contradicts, or is neutral to the opportunity described by E1–E2.

## SUB-ENGINES
3A Swing Detection · 3B Structure Classification · 3C Break of Structure · 3D Structural Failure · 3E Structure Strength · 3F Internal vs External Structure

## INPUT
E1–E2 evidence, closed M5 candles, permitted M15/H1 structural context, swing history.

## PROCESSING
Detect meaningful swings; classify HH/HL/LH/LL; distinguish internal/external structure; evaluate BOS, failed BOS and structural failure; estimate structural strength and directional alignment. Preserve mixed structure explicitly.

## OUTPUT
structure_state, swing_map, internal_structure, external_structure, BOS, structural_failure, strength, directional_bias, evidence[], conflicts[], confidence, observations[], reasoning_trace.

## GATE
NONE. Lack of alignment is information, not a gate failure. Insufficient history is reported as INCOMPLETE only when analysis genuinely cannot be performed.

## SCORE
Confidence represents structural clarity/strength, not permission to trade.

## TRACEABILITY
Record swing references, structural levels, event candles, lookbacks, upstream evidence and conflicting structural signals.

## DECISION BOUNDARY
Structure analysis only.
