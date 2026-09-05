from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class EngineResult:
    engine_id:str; name:str; gate_passed:bool|None; score:float; output:dict[str,Any]=field(default_factory=dict); reason_codes:tuple[str,...]=()

@dataclass(frozen=True)
class DecisionResult:
    symbol:str="UNKNOWN"; timeframe:str="M5"; decision:str="NO_TRADE"; gate_passed:bool=False; score:float=0.0; engines:tuple[EngineResult,...]|dict[str,EngineResult]=(); risk:dict[str,Any]=field(default_factory=dict); reason_codes:tuple[str,...]=(); state:str="ANALYSIS_COMPLETE_NO_TRADE"; blocked_by:Any=None; wait_bars:int=0; execution_state:dict[str,Any]=field(default_factory=lambda:{"state":"NOT_REQUESTED","order_id":None,"position_id":None,"error":None})

    def __post_init__(self)->None:
        normalized=tuple(v for v in self.engines.values() if isinstance(v,EngineResult)) if isinstance(self.engines,dict) else tuple(self.engines or ()); object.__setattr__(self,"engines",normalized)
        by_id={v.engine_id:v for v in normalized}; e9=by_id.get("E9"); e9o=e9.output if e9 else {}; e8=by_id.get("E8"); e8o=e8.output if e8 else {}
        if self.symbol=="UNKNOWN" and e9o.get("symbol"):object.__setattr__(self,"symbol",str(e9o["symbol"]))
        if self.timeframe=="M5" and e9o.get("timeframe"):object.__setattr__(self,"timeframe",str(e9o["timeframe"]))
        if self.score==0.0 and e9 is not None:object.__setattr__(self,"score",float(e9.score))
        if e9 is not None and e9.gate_passed is not None:object.__setattr__(self,"gate_passed",bool(e9.gate_passed))
        if not self.risk and isinstance(e8o,dict):object.__setattr__(self,"risk",dict(e8o))
        if self.reason_codes==() and e9 is not None:object.__setattr__(self,"reason_codes",tuple(e9.reason_codes))
        if self.decision=="TRADE":
            d=str(e9o.get("decision") or "").upper().strip(); object.__setattr__(self,"decision",d if d in {"BUY","SELL"} and self.gate_passed else "NO_TRADE")
        elif self.decision=="NO_TRADE" and self.gate_passed:
            d=str(e9o.get("decision") or "").upper().strip()
            if d in {"BUY","SELL"}:object.__setattr__(self,"decision",d)
        elif self.decision in {"BUY","SELL"} and not self.gate_passed:object.__setattr__(self,"decision","NO_TRADE")
        if self.decision in {"BUY","SELL"} and self.gate_passed and self.state in {"ANALYSIS_COMPLETE_NO_TRADE","",None}:object.__setattr__(self,"state","SIGNAL_READY")
        execution=dict(self.execution_state or {}); valid={"NOT_REQUESTED","ORDER_INTENT","ORDER_SUBMITTED","ACCEPTED","REJECTED","POSITION_OPEN","POSITION_CLOSED"}
        if execution.get("state") not in valid:execution={"state":"NOT_REQUESTED","order_id":None,"position_id":None,"error":"INVALID_EXECUTION_STATE"}
        if execution.get("state")=="NOT_REQUESTED" and self.decision in {"BUY","SELL"} and self.gate_passed:execution={"state":"ORDER_INTENT","order_id":None,"position_id":None,"error":None}
        object.__setattr__(self,"execution_state",execution)

    @property
    def legacy_runtime(self)->bool:return False
    @property
    def trade_plan(self)->dict[str,Any]:return dict(self.risk.get("trade_plan") or {})
    def as_dict(self)->dict[str,Any]:
        return {"system":"9-ENGINE","version":"production-v2","symbol":self.symbol,"timeframe":self.timeframe,"decision":self.decision,"state":self.state,"gate_passed":self.gate_passed,"score":self.score,"decision_authority":"E9","legacy_runtime":False,"execution_state":dict(self.execution_state),"engines":[{"id":e.engine_id,"name":e.name,"gate_passed":e.gate_passed,"score":e.score,"output":e.output,"reason_codes":list(e.reason_codes)} for e in self.engines],"risk":self.risk,"trade_plan":self.trade_plan,"reason_codes":list(self.reason_codes),"blocked_by":self.blocked_by,"wait_bars":self.wait_bars}