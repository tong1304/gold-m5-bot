from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Dict, List, Tuple


@dataclass
class SetupState:
    entries: Dict[str, List[str]] = field(default_factory=dict)

    def record(self, setup_id: str, trigger_id: str) -> None:
        self.entries.setdefault(str(setup_id), []).append(str(trigger_id))

    def triggers(self, setup_id: str) -> List[str]:
        return list(self.entries.get(str(setup_id), []))

    def reentry_count(self, setup_id: str) -> int:
        return max(0, len(self.triggers(setup_id)) - 1)


def build_setup_id(symbol: str, regime: str, engine: str, direction: str, anchor) -> str:
    raw = f"{str(symbol).upper()}|{str(regime).upper()}|{str(engine).upper()}|{str(direction).upper()}|{float(anchor):.8f}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"SETUP-{digest}"


def build_trigger_id(engine: str, direction: str, candle_time, trigger_signature) -> str:
    raw = f"{engine}|{direction}|{candle_time}|{trigger_signature}"
    return f"TRG-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]}"


def can_emit_entry(state: SetupState, setup_id: str, trigger_id: str, *, max_reentries: int = 2) -> Tuple[bool, str]:
    triggers = state.triggers(setup_id)
    if trigger_id in triggers:
        return False, "DUPLICATE_TRIGGER"
    if not triggers:
        return True, "INITIAL"
    if len(triggers) - 1 >= max(0, int(max_reentries)):
        return False, "MAX_REENTRIES_REACHED"
    return True, "RE_ENTRY"
