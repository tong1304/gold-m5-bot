from __future__ import annotations
from statistics import mean
from typing import Any
from ...core.subengine import SubEngine as _Base

class ProfessionalE2Brain(_Base):
    """E2 professional opportunity/regime analyst; E9 remains decision authority."""
    def _e1_context(self, d: dict[str, Any]) -> dict[str, Any]:
        raw = d.get("E1_result") or {}
        return raw if isinstance(raw, dict) else {}

    def _analyse(self, d: dict[str, Any]):
        bs = self._bars(d)
        if len(bs) < 50:
            return ({"state":"UNAVAILABLE","thesis":"Insufficient closed-candle history.","regime":"UNRESOLVED","direction":"NEUTRAL","phase":"UNRESOLVED","opportunity":"NONE","quality":"UNPROVEN","observations":[],"evidence":[],"counter_evidence":["insufficient history"],"missing_evidence":["50 valid candles"],"confidence":0.0},0.0,["INSUFFICIENT_MARKET_DATA"])
        h=[float(b["high"]) for b in bs]; l=[float(b["low"]) for b in bs]; c=[float(b["close"]) for b in bs]; o=[float(b["open"]) for b in bs]
        last=c[-1]; atr=max(self._atr(bs),1e-12); ema20=self._ema(c,20); ema50=self._ema(c,50)
        slope5=(c[-1]-c[-6])/atr; slope20=(c[-1]-c[-21])/atr; ema_gap=(ema20-ema50)/atr
        ranges=[h[i]-l[i] for i in range(len(bs))]; avg20=max(mean(ranges[-20:]),1e-12); avg6=mean(ranges[-6:]); rr=avg6/avg20
        cr=max(h[-1]-l[-1],1e-12); body_ratio=abs(c[-1]-o[-1])/cr
        hi20=max(h[-21:-1]); lo20=min(l[-21:-1]); hi40=max(h[-41:-1]); lo40=min(l[-41:-1])
        broke_up=last>hi20; broke_down=last<lo20; false_up=h[-1]>hi20 and last<=hi20; false_down=l[-1]<lo20 and last>=lo20
        pos=max(0.0,min(1.0,(last-lo40)/max(hi40-lo40,1e-12)))
        travelled=max(sum(ranges[-12:]),1e-12); efficiency=abs(c[-1]-c[-13])/travelled
        ph,pl=self._pivots(bs); hh=len(ph)>1 and ph[-1]>ph[-2]; lh=len(ph)>1 and ph[-1]<ph[-2]; hl=len(pl)>1 and pl[-1]>pl[-2]; ll=len(pl)>1 and pl[-1]<pl[-2]
        bull_struct=hh and hl; bear_struct=lh and ll
        trend_up=ema_gap>0.35 and slope5>0.20 and slope20>0.50 and bull_struct
        trend_down=ema_gap<-0.35 and slope5<-0.20 and slope20<-0.50 and bear_struct
        compressed=rr<0.70; expansion=rr>1.30 or (cr>1.35*avg20 and body_ratio>=0.60)
        brk_up=broke_up and expansion and last>ema20; brk_down=broke_down and expansion and last<ema20
        extreme_low=pos<0.20; extreme_high=pos>0.80
        transition=not(trend_up or trend_down) and (compressed or false_up or false_down or abs(ema_gap)<0.35)
        if brk_up: regime,direction="BREAKOUT","UP"
        elif brk_down: regime,direction="BREAKOUT","DOWN"
        elif trend_up: regime,direction="TREND","UP"
        elif trend_down: regime,direction="TREND","DOWN"
        elif compressed and abs(slope20)<0.80: regime,direction="RANGE","NEUTRAL"
        elif (extreme_low or extreme_high) and (false_up or false_down): regime,direction="MEAN_REVERSION",("UP" if extreme_low and false_down else "DOWN" if extreme_high and false_up else "NEUTRAL")
        elif transition: regime,direction="TRANSITION","NEUTRAL"
        else: regime,direction=("RANGE" if abs(slope20)<0.80 else "TRANSITION"),"NEUTRAL"
        if regime=="TREND": phase="EXPANSION" if expansion and efficiency>=0.30 else "COMPRESSION" if compressed else "BALANCED"; opportunity="TREND_CONTINUATION"
        elif regime=="BREAKOUT": phase="EXPANSION" if expansion else "BREAKOUT_DEVELOPING"; opportunity="BREAKOUT_CONTINUATION"
        elif regime=="RANGE": phase="COMPRESSION" if compressed else "BALANCED"; opportunity="RANGE_ROTATION"
        elif regime=="MEAN_REVERSION": phase="REJECTION"; opportunity="MEAN_REVERSION"
        else: phase="TRANSITION"; opportunity="WAIT_FOR_REPRICING"
        e1=self._e1_context(d); e1d=str(e1.get("directional_pressure") or e1.get("direction") or "NEUTRAL").upper(); e1d="UP" if e1d in {"UP","BULLISH","BUY","LONG"} else "DOWN" if e1d in {"DOWN","BEARISH","SELL","SHORT"} else "NEUTRAL"
        alignment="ALIGNED" if direction==e1d and direction!="NEUTRAL" else "CONFLICT" if direction!="NEUTRAL" and e1d!="NEUTRAL" else "INCONCLUSIVE"
        counter=[]
        if regime=="TREND" and efficiency<0.25: counter.append("directional movement lacks efficiency")
        if regime=="TREND" and not (bull_struct if direction=="UP" else bear_struct): counter.append("structure does not fully confirm trend")
        if regime=="BREAKOUT" and not expansion: counter.append("breakout lacks volatility expansion")
        if regime=="RANGE" and not compressed: counter.append("range compression is weak")
        if alignment=="CONFLICT": counter.append(f"E1 conflicts with independent E2 direction={direction}")
        missing=[]
        if regime in {"TREND","BREAKOUT"} and efficiency<0.30: missing.append("clean directional follow-through")
        if regime=="BREAKOUT" and not expansion: missing.append("confirmed expansion")
        if regime=="TRANSITION": missing.append("stable regime commitment")
        n=2 if regime in {"TREND","BREAKOUT"} else 0; n+=int(efficiency>=0.30)+int(expansion and regime in {"TREND","BREAKOUT"})+int(alignment=="ALIGNED")-2*int(alignment=="CONFLICT")-min(2,len(counter))
        confidence=max(0.20,min(0.95,0.50+0.08*n)); quality="HIGH" if confidence>=0.78 and not counter else "MEDIUM" if confidence>=0.60 else "LOW"
        evidence=[f"ema_gap_atr={ema_gap:.3f}",f"slope5_atr={slope5:.3f}",f"slope20_atr={slope20:.3f}",f"range_ratio={rr:.3f}",f"efficiency={efficiency:.3f}",f"structure={'BULLISH' if bull_struct else 'BEARISH' if bear_struct else 'MIXED'}",f"position40={pos:.3f}",f"expansion={expansion}",f"breakout_up={brk_up}",f"breakout_down={brk_down}",f"e1_direction={e1d}",f"e1_e2_alignment={alignment}"]
        output={"state":f"{regime}_{direction}" if direction!="NEUTRAL" else regime,"thesis":f"Market offers {opportunity} in {regime}; direction={direction}; phase={phase}; evidence_quality={quality}.","regime":regime,"direction":direction,"phase":phase,"opportunity":opportunity,"quality":quality,"alignment_with_e1":alignment,"observations":[f"independent_regime={regime}",f"independent_direction={direction}",f"phase={phase}",f"opportunity={opportunity}",f"alignment_with_e1={alignment}"],"evidence":evidence,"counter_evidence":counter,"missing_evidence":missing,"confidence":confidence,"decision":None,"entry":None,"trigger":None,"risk":None,"gate":None}
        return output,confidence,()
