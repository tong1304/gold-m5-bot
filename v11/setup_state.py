from __future__ import annotations
from dataclasses import dataclass, field
import hashlib, json
from typing import Dict, List, Tuple

@dataclass
class SetupState:
    entries: Dict[str, List[str]] = field(default_factory=dict)
    def record(self, setup_id: str, trigger_id: str) -> None:
        self.entries.setdefault(str(setup_id), []).append(str(trigger_id))
    def triggers(self, setup_id: str) -> List[str]: return list(self.entries.get(str(setup_id), []))
    def reentry_count(self, setup_id: str) -> int: return max(0, len(self.triggers(setup_id))-1)

def build_setup_id(symbol, regime, engine, direction, anchor) -> str:
    try:anchor=f"{float(anchor):.8f}"
    except (TypeError,ValueError):anchor=str(anchor)
    raw=f"{str(symbol).upper()}|{str(regime).upper()}|{str(engine).upper()}|{str(direction).upper()}|{anchor}"
    return f"SETUP-{hashlib.sha1(raw.encode()).hexdigest()[:12]}"

def build_trigger_id(engine, direction, candle_time, trigger_signature) -> str:
    raw=f"{engine}|{direction}|{candle_time}|{trigger_signature}"
    return f"TRG-{hashlib.sha1(raw.encode()).hexdigest()[:12]}"

def can_emit_entry(state, setup_id, trigger_id, *, max_reentries=2) -> Tuple[bool,str]:
    triggers=state.triggers(setup_id)
    if trigger_id in triggers:return False,"DUPLICATE_TRIGGER"
    if not triggers:return True,"INITIAL"
    if len(triggers)-1>=max(0,int(max_reentries)):return False,"MAX_REENTRIES_REACHED"
    return True,"RE_ENTRY"

def state_from_history(rows) -> SetupState:
    state=SetupState()
    for row in rows or []:
        payload=row.get("payload_json") if isinstance(row,dict) else None
        try:data=json.loads(payload or "{}")
        except (TypeError,ValueError):data={}
        setup_id=data.get("setup_id") or row.get("setup_id")
        trigger_id=data.get("trigger_id")
        if setup_id and trigger_id and row.get("result") != "NO_TRADE":state.record(setup_id,trigger_id)
    return state
