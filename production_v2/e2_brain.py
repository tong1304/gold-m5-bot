"""E2 opportunity brain: independent thesis, auction intent and conditional market paths."""
from __future__ import annotations
from typing import Any, Dict
import numpy as np
import pandas as pd


def _atr(df: pd.DataFrame, n: int = 14) -> float:
    h,l,c=[pd.to_numeric(df[x],errors="coerce") for x in ("high","low","close")]; p=c.shift(1)
    tr=pd.concat([(h-l),(h-p).abs(),(l-p).abs()],axis=1).max(axis=1); v=float(tr.rolling(n).mean().iloc[-1])
    return v if np.isfinite(v) and v>0 else 1.0

def _ema(s: pd.Series,n:int)->float:
    v=float(pd.to_numeric(s,errors="coerce").ewm(span=n,adjust=False).mean().iloc[-1]); return v if np.isfinite(v) else float(s.iloc[-1])

def _slope(s:pd.Series,n:int,atr:float)->float:
    return 0.0 if len(s)<=n else (float(s.iloc[-1])-float(s.iloc[-1-n]))/max(atr,1e-9)

def _auction(df,atr,up,down,pos):
    c=pd.to_numeric(df.close,errors="coerce"); o=pd.to_numeric(df.open,errors="coerce"); n=min(5,len(df))
    net=(float(c.iloc[-1])-float(c.iloc[-n]))/max(atr,1e-9); body=float((c.tail(n)-o.tail(n)).abs().mean())/max(atr,1e-9)
    uf=int((c.tail(3).diff()>0).sum()); dfw=int((c.tail(3).diff()<0).sum())
    if down>=5 and net<-.75 and dfw>=2:return "SELLER_CONTROL",["INITIATIVE_SELLING","DOWNWARD_DISPLACEMENT","FOLLOW_THROUGH_CONFIRMED"]
    if up>=5 and net>.75 and uf>=2:return "BUYER_CONTROL",["INITIATIVE_BUYING","UPWARD_DISPLACEMENT","FOLLOW_THROUGH_CONFIRMED"]
    if body>=.7 and abs(net)<.35:
        if pos>=.8 and dfw>=1:return "UP_AUCTION_FAILURE",["DISPLACEMENT_WITHOUT_FOLLOW_THROUGH","PREMIUM_REJECTION_RISK"]
        if pos<=.2 and uf>=1:return "DOWN_AUCTION_FAILURE",["DISPLACEMENT_WITHOUT_FOLLOW_THROUGH","DISCOUNT_REJECTION_RISK"]
    return "UNRESOLVED_AUCTION",["AUCTION_NOT_RESOLVED"]

def analyze_e2(df:pd.DataFrame,e1:Dict[str,Any]|None=None)->Dict[str,Any]:
    if df is None or len(df)<60:return {"role":"OPPORTUNITY_REGIME_ANALYST","question":"What opportunity is the market offering right now?","finding":"INSUFFICIENT_DATA","observations":[],"reasons":["INSUFFICIENT_DATA"]}
    atr=_atr(df); c=pd.to_numeric(df.close,errors="coerce"); e20,e50=_ema(c,20),_ema(c,50); gap=(e20-e50)/atr; s5,s20=_slope(c,5,atr),_slope(c,20,atr)
    checks=[e20>e50,s20>0,s5>0,c.iloc[-1]>c.iloc[-2],c.iloc[-1]>df.open.iloc[-1],c.iloc[-1]>c.iloc[-5],c.iloc[-1]>c.iloc[-10]]; up=sum(map(int,checks)); down=7-up
    w=c.tail(40); hi,lo=float(w.max()),float(w.min()); pos=(float(c.iloc[-1])-lo)/max(hi-lo,1e-9); eff=abs(float(c.iloc[-1]-c.iloc[-13]))/max(float(c.tail(12).diff().abs().sum()),1e-9)
    direction="UP" if up-down>=2 else "DOWN" if down-up>=2 else "NEUTRAL"; regime="RANGE" if eff<.22 and abs(gap)<.75 else "TREND" if direction!="NEUTRAL" else "TRANSITION"
    intent,ireasons=_auction(df,atr,up,down,pos)
    opportunity,stage=("WAIT_FOR_RANGE_EDGE","BALANCED") if regime=="RANGE" else (("TREND_PULLBACK_CONTINUATION","DEVELOPING") if regime=="TREND" else ("WAIT_FOR_REPRICING","TRANSITION"))
    if intent.endswith("FAILURE"):opportunity,stage="LIQUIDITY_REVERSAL","CONDITIONAL"
    opposing=max(0,(hi-float(c.iloc[-1]))/atr) if direction=="UP" else max(0,(float(c.iloc[-1])-lo)/atr) if direction=="DOWN" else 0.0
    paths=( ["IF pullback holds and control resumes -> continuation strengthens","IF opposing structure wins -> thesis invalidated"] if regime=="TREND" else ["IF range edge rejects -> range rotation develops","IF range break plus acceptance -> breakout repricing develops"] if regime=="RANGE" else ["IF directional evidence converges -> thesis strengthens","IF counter-evidence dominates -> remain neutral"] )
    if intent.endswith("FAILURE"):paths.append("IF failed auction receives follow-through -> reversal opportunity strengthens")
    paths.append("IF opposing space remains absent -> opportunity vetoed" if opposing<.5 else "IF opposing space remains open -> asymmetric path remains viable")
    veto=[]
    if direction=="DOWN" and pos<=.12 and opposing<.5:veto.append("SHORT_CHASE_AT_DISCOUNT_WITH_NO_OPPOSING_SPACE")
    if direction=="UP" and pos>=.88 and opposing<.5:veto.append("LONG_CHASE_AT_PREMIUM_WITH_NO_OPPOSING_SPACE")
    if intent=="UNRESOLVED_AUCTION" and abs(up-down)<=2:veto.append("AUCTION_INTENT_UNRESOLVED")
    hierarchy={"primary":opportunity,"secondary":"LIQUIDITY_REVERSAL" if intent.endswith("FAILURE") else "ALTERNATIVE_RANGE_PATH","conditional_paths":paths,"invalidated_by":"opposing structure wins","no_trade_when":veto or ["downstream confirmation absent"]}
    reasons=(['HARD_VETO_PRESENT'] if veto else [])+ireasons+["CONDITIONAL_OPPORTUNITY_MAP"]+([] if veto else ["MISSING_OPPORTUNITY_CONFIRMATION"])
    return {"role":"OPPORTUNITY_REGIME_ANALYST","question":"What opportunity is the market offering right now?","finding":f"Independent E2 thesis: {regime}/{direction} creates {opportunity} at {stage}; thesis is conditional and requires downstream confirmation.","observations":[f"ema_gap_atr={gap:.3f}",f"ema20_slope_atr={_slope(c,20,atr):.3f}",f"ema50_slope_atr={_slope(c,50,atr):.3f}",f"slope5_atr={s5:.3f}",f"slope20_atr={s20:.3f}",f"efficiency12={eff:.3f}",f"up_evidence={up}/7",f"down_evidence={down}/7",f"position_40={pos:.3f}",f"opposing_space_atr={opposing:.3f}",f"auction_intent={intent}",f"auction_evidence={';'.join(ireasons)}",f"opportunity_hierarchy={hierarchy}",f"conditional_paths={paths}"],"reasons":reasons,"thesis":{"regime":regime,"direction":direction,"opportunity":opportunity,"stage":stage,"auction_intent":intent,"auction_intent_evidence":ireasons,"opposing_space_atr":opposing,"opportunity_hierarchy":hierarchy,"conditional_map":paths,"hard_veto":veto,"requires_downstream_confirmation":True,"entry":None,"final_decision":None}}
