from __future__ import annotations
from statistics import mean
from typing import Any
from ...core.subengine import SubEngine as _Base


class ProfessionalE2Brain(_Base):
    """E2: independent professional opportunity/regime analyst.

    E2 observes the auction; it does not execute. E1 is only a diagnostic
    cross-check and can never override the E2 thesis. Closed candles only.
    """
    QUESTION = "What opportunity is the market offering right now?"
    MIN_BARS = 60

    @staticmethod
    def _norm_direction(v: Any) -> str:
        v = str(v or "NEUTRAL").upper().strip()
        return "UP" if v in {"UP", "BULLISH", "BUY", "LONG"} else "DOWN" if v in {"DOWN", "BEARISH", "SELL", "SHORT"} else "NEUTRAL"

    @staticmethod
    def _candle(o: float, h: float, l: float, c: float):
        span = max(h - l, 1e-12)
        return abs(c - o) / span, (c - l) / span

    @staticmethod
    def _clamp(x, lo=0.0, hi=1.0):
        return max(lo, min(hi, float(x)))

    def _e1(self, d):
        x = d.get("E1_result") or {}
        return x if isinstance(x, dict) else {}

    def _analyse(self, d):
        bs = self._bars(d)
        if len(bs) < self.MIN_BARS:
            out = {"state":"UNAVAILABLE","question":self.QUESTION,"thesis":"Insufficient closed-candle evidence.","regime":"UNRESOLVED","direction":"NEUTRAL","phase":"UNRESOLVED","opportunity":"NONE","opportunity_state":"UNPROVEN","quality":"UNPROVEN","opportunity_quality":"LOW","auction_phase":"TRANSITION","acceptance_quality":"UNPROVEN","alignment_with_e1":"INCONCLUSIVE","independence":"E2_FIRST_E1_CROSS_CHECK","auction_state":"UNKNOWN","location_context":"UNKNOWN","regime_confidence":0.0,"opportunity_score":0.0,"decision_factors":[],"observations":[],"evidence":[],"counter_evidence":["insufficient closed-candle history"],"missing_evidence":[f"{self.MIN_BARS} valid closed candles"],"evidence_map":{},"confidence":0.0,"decision":None,"entry":None,"trigger":None,"risk":None,"gate":None}
            return out, 0.0, ["INSUFFICIENT_MARKET_DATA"]

        h=[float(x["high"]) for x in bs]; l=[float(x["low"]) for x in bs]; c=[float(x["close"]) for x in bs]; o=[float(x["open"]) for x in bs]; last=c[-1]
        atr=max(self._atr(bs),1e-12)
        ema20,ema50=self._ema(c,20),self._ema(c,50); gap=(ema20-ema50)/atr
        slope3=(c[-1]-c[-4])/atr; slope8=(c[-1]-c[-9])/atr; slope21=(c[-1]-c[-22])/atr
        ranges=[max(h[i]-l[i],0.0) for i in range(len(bs))]; avg20=max(mean(ranges[-20:]),1e-12); recent6=mean(ranges[-6:]); vr=recent6/avg20
        body,cp=self._candle(o[-1],h[-1],l[-1],last); expansion=vr>=1.25 or (ranges[-1]>=1.35*avg20 and body>=.60); compression=vr<=.72
        eff12=abs(c[-1]-c[-13])/max(sum(ranges[-12:]),1e-12); eff24=abs(c[-1]-c[-25])/max(sum(ranges[-24:]),1e-12); efficiency=max(eff12,eff24)

        hi20,lo20=max(h[-21:-1]),min(l[-21:-1]); hi40,lo40=max(h[-41:-1]),min(l[-41:-1]); width=max(hi40-lo40,1e-12); pos=self._clamp((last-lo40)/width)
        location="EDGE_LOW" if pos<=.20 else "EDGE_HIGH" if pos>=.80 else "MID_RANGE"
        prev2,prev=c[-3],c[-2]
        up_closes=sum(x>hi20 for x in (prev2,prev,last)); down_closes=sum(x<lo20 for x in (prev2,prev,last))
        broke_up=last>hi20; broke_down=last<lo20
        accepted_up=(up_closes>=2 and cp>=.60) or (broke_up and expansion and body>=.55 and cp>=.68)
        accepted_down=(down_closes>=2 and cp<=.40) or (broke_down and expansion and body>=.55 and cp<=.32)
        sweep_up=h[-1]>hi20 and last<=hi20; sweep_down=l[-1]<lo20 and last>=lo20
        reject_up=sweep_up and cp<=.45; reject_down=sweep_down and cp>=.55
        fail_up=sweep_up and reject_up; fail_down=sweep_down and reject_down

        ph,pl=self._pivots(bs); hh=len(ph)>=2 and ph[-1]>ph[-2]; lh=len(ph)>=2 and ph[-1]<ph[-2]; hl=len(pl)>=2 and pl[-1]>pl[-2]; ll=len(pl)>=2 and pl[-1]<pl[-2]
        bull_struct=hh and hl; bear_struct=lh and ll
        up=sum((gap>.30,slope3>.15,slope8>.25,slope21>.45,bull_struct,eff12>=.28,cp>=.60)); down=sum((gap<-.30,slope3<-.15,slope8<-.25,slope21<-.45,bear_struct,eff12>=.28,cp<=.40))
        pressure="UP" if up>=5 and up>down else "DOWN" if down>=5 and down>up else "NEUTRAL"
        trend_up=up>=5 and bull_struct and eff24>=.22; trend_down=down>=5 and bear_struct and eff24>=.22
        balanced=(abs(gap)<.45 and abs(slope21)<.55 and efficiency<.25 and .15<pos<.85 and max(up,down)<=4 and not(accepted_up or accepted_down or fail_up or fail_down) and width/atr<9)

        if accepted_up and not accepted_down: regime,direction="BREAKOUT","UP"
        elif accepted_down and not accepted_up: regime,direction="BREAKOUT","DOWN"
        elif trend_up and not trend_down: regime,direction="TREND","UP"
        elif trend_down and not trend_up: regime,direction="TREND","DOWN"
        elif fail_down and not fail_up and pos<=.30: regime,direction="MEAN_REVERSION","UP"
        elif fail_up and not fail_down and pos>=.70: regime,direction="MEAN_REVERSION","DOWN"
        elif balanced: regime,direction="RANGE","NEUTRAL"
        else: regime,direction="TRANSITION","NEUTRAL"

        if regime=="BREAKOUT":
            auction_phase="ACCEPTANCE"; auction="ACCEPTING_UP" if direction=="UP" else "ACCEPTING_DOWN"; phase="EXPANSION" if expansion else "ACCEPTANCE_DEVELOPING"; acceptance="STRONG" if expansion and body>=.60 else "CONFIRMED"; opportunity="BREAKOUT_CONTINUATION"
        elif regime=="TREND":
            auction_phase="REPRICING"; auction="REPRICING_UP" if direction=="UP" else "REPRICING_DOWN"; phase="EXPANSION" if expansion and efficiency>=.30 else "PULLBACK_OR_BALANCE"; acceptance="CONFIRMED" if efficiency>=.30 else "DEVELOPING"; opportunity="TREND_CONTINUATION"
        elif regime=="MEAN_REVERSION":
            auction_phase="REJECTION"; auction="FAILED_AUCTION_DOWN" if direction=="UP" else "FAILED_AUCTION_UP"; phase="REJECTION"; acceptance="UNPROVEN"; opportunity="MEAN_REVERSION"
        elif regime=="RANGE":
            auction_phase="BALANCE"; auction="BALANCED"; phase="COMPRESSION" if compression else "BALANCED"; acceptance="UNPROVEN"; opportunity="WAIT_FOR_RANGE_EDGE"
        else:
            auction_phase="TRANSITION"; auction="REPRICING_UNRESOLVED"; phase="TRANSITION"; acceptance="UNPROVEN"; opportunity="WAIT_FOR_REPRICING"

        location_score=1.0 if location in {"EDGE_LOW","EDGE_HIGH"} else .45
        adverse_extension=(direction=="UP" and pos>=.85) or (direction=="DOWN" and pos<=.15)
        favorable_location=(direction=="UP" and pos<=.65) or (direction=="DOWN" and pos>=.35) or direction=="NEUTRAL"
        catalyst=accepted_up or accepted_down or fail_up or fail_down; structural=bull_struct if direction=="UP" else bear_struct if direction=="DOWN" else balanced
        momentum=self._clamp(efficiency/.50)*.65+body*.35; stability=self._clamp(1-abs(slope3-slope21)/3)
        score=.30*self._clamp(abs(up-down)/7*1.7)+.22*self._clamp(efficiency/.50)+.18*float(structural)+.15*location_score+.10*float(catalyst)+.05*momentum
        if adverse_extension: score-=.15
        if not favorable_location and direction!="NEUTRAL": score-=.05
        if regime=="TRANSITION": score*=.55
        if regime=="RANGE" and location=="MID_RANGE": score*=.45
        opportunity_score=self._clamp(score)

        missing=[]; counter=[]
        if regime=="BREAKOUT" and not expansion: missing.append("follow-through/volatility expansion after repricing")
        if regime=="TREND" and adverse_extension: counter.append("trend is extended into an unfavorable auction location"); missing.append("pullback or renewed acceptance from value")
        if regime=="MEAN_REVERSION" and not(fail_up or fail_down): missing.append("failed-auction rejection")
        if regime=="RANGE": missing.append("range edge plus rejection/acceptance before rotation")
        if regime=="TRANSITION": missing.append("stable directional or balanced regime commitment")
        if regime in {"BREAKOUT","MEAN_REVERSION"} and not catalyst: missing.append("observable auction event")
        e1=self._e1(d); e1dir=self._norm_direction(e1.get("directional_pressure") or e1.get("direction")); alignment="ALIGNED" if direction!="NEUTRAL" and direction==e1dir else "CONFLICT" if direction!="NEUTRAL" and e1dir!="NEUTRAL" else "INCONCLUSIVE"
        if alignment=="CONFLICT": counter.append(f"E1 cross-check conflicts with independent E2 direction={direction}")

        state="WAIT" if regime=="TRANSITION" or (regime=="RANGE" and location=="MID_RANGE") else "DEVELOPING" if missing or counter else "ACTIONABLE_CONTEXT" if opportunity_score>=.68 else "DEVELOPING"
        quality="LOW" if state=="WAIT" else "HIGH" if opportunity_score>=.72 and not counter else "MEDIUM" if opportunity_score>=.50 else "LOW"
        regime_conf={"BREAKOUT":.88,"TREND":.82,"MEAN_REVERSION":.72,"RANGE":.68,"TRANSITION":.35}[regime]
        confidence=self._clamp(.35*regime_conf+.30*opportunity_score+.20*momentum+.15*stability-(.08 if alignment=="CONFLICT" else 0))
        em={"directional_pressure":pressure,"up_pressure_score":f"{up}/7","down_pressure_score":f"{down}/7","structure":"BULLISH" if bull_struct else "BEARISH" if bear_struct else "MIXED","location":location,"position40":round(pos,4),"auction_phase":auction_phase,"acceptance_quality":acceptance,"efficiency12":round(eff12,4),"efficiency24":round(eff24,4),"volatility_ratio":round(vr,4),"expansion":expansion,"compression":compression,"breakout_up":broke_up,"breakout_down":broke_down,"accepted_up":accepted_up,"accepted_down":accepted_down,"failed_auction_up":fail_up,"failed_auction_down":fail_down,"e1_cross_check":alignment}
        evidence=[f"{k}={v}" for k,v in em.items()]; observations=[f"independent_regime={regime}",f"independent_direction={direction}",f"directional_pressure={pressure}",f"phase={phase}",f"auction_state={auction}",f"location_context={location}",f"opportunity={opportunity}",f"opportunity_state={state}",f"opportunity_quality={quality}",f"opportunity_score={opportunity_score:.3f}"]
        factors=[f"opportunity_score={opportunity_score:.3f}",f"regime={regime}",f"auction={auction}",f"location={location}"]
        if regime=="RANGE" and location=="MID_RANGE": factors.insert(0,"Range detected but price is in the middle; no rotation edge")
        thesis=f"E2 independently concludes {regime}/{direction}: {opportunity}; auction={auction_phase}, location={location}, state={state}."
        out={"state":"ANALYZED","question":self.QUESTION,"thesis":thesis,"regime":regime,"direction":direction,"phase":phase,"opportunity":opportunity,"opportunity_state":state,"quality":quality,"opportunity_quality":quality,"opportunity_score":opportunity_score,"alignment_with_e1":alignment,"independence":"E2_FIRST_E1_CROSS_CHECK","auction_phase":auction_phase,"auction_state":auction,"acceptance_quality":acceptance,"location_context":location,"regime_confidence":regime_conf,"decision_factors":factors,"observations":observations,"evidence":evidence,"counter_evidence":counter,"missing_evidence":missing,"evidence_map":em,"confidence":confidence,"decision":None,"entry":None,"trigger":None,"risk":None,"gate":None}
        return out,confidence,[]
