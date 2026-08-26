from .subengine import SubEngine as Base, SubEngineResult

class ProfessionalSubEngine(Base):
    """Specialist contract: evidence and thesis first; E9 decides."""
    def run(self,data):
        r=super().run(data);o=dict(r.output or {});sid=r.sub_engine_id;state=str(o.get('state','UNRESOLVED'));obs=[]
        for k in ('direction','structure','trend_strength_atr','range_ratio','sweep_high','sweep_low','rejection','acceptance','position_in_range','archetype','displacement','trigger','follow_through','failure','min_rr','max_stop_atr'):
            if k in o:obs.append(f'{k}={o[k]}')
        if not obs:obs=[f'state={state}']
        c=self.confidence(sid,o,r.score);missing=[]
        if sid.startswith('6') and state not in ('MATURE','QUALITY_PASS'):missing=['setup confirmation']
        if sid.startswith('7') and state not in ('CONFIRMED','QUALITY_PASS','FOLLOW_THROUGH'):missing=['trigger/follow-through']
        if sid.startswith('8') and state not in ('RISK_GATE_READY','RR_OK','VALID','LIQUIDITY_TARGET'):missing=['complete trade economics']
        thesis=f'{sid}: {state}'
        o.update(evidence_type=f'{sid}_SPECIALIST_ANALYSIS',observations=obs,analysis=thesis,evidence=obs,counter_evidence=[],confidence=c,thesis=thesis,missing_evidence=missing,upstream_decisions_used=False,upstream_gates_used=False)
        s=round(c*100,1);return SubEngineResult(sid,o,r.gate_passed,s,{**r.trace,'spec_version':'production-v2.3.0-professional-subengine','evidence_first':True,'output':o,'score':s})
    @staticmethod
    def confidence(sid,o,fallback):
        st=str(o.get('state','')).upper()
        if sid.startswith('1') and 'TREND_' in st:return min(.98,max(.55,float(o.get('trend_strength_atr',.5))*.55+.45))
        if sid.startswith('3'):
            q=float(o.get('structure_strength',0) or 0);return min(.98,max(.45,q/100)) if q else (.9 if st in ('BULLISH','BEARISH','STRONG') else .6)
        if sid.startswith('4'):return min(.96,.50+.11*sum(bool(o.get(k)) for k in ('sweep_high','sweep_low','rejection','acceptance')))
        if sid.startswith('5'):return round(.55+.40*(1-abs(float(o.get('position_in_range',.5))-.5)*2),3)
        if sid.startswith('6'):return .91 if st in ('MATURE','QUALITY_PASS','CONTEXT_ALIGNED') else .56
        if sid.startswith('7'):return .94 if st in ('CONFIRMED','QUALITY_PASS','FOLLOW_THROUGH') else .45 if st=='NO_TRIGGER' else .58
        if sid.startswith('8'):return .92 if st in ('RISK_GATE_READY','RR_OK','VALID','LIQUIDITY_TARGET') else .55
        return min(.98,max(.40,float(fallback)/100 if fallback else .5))
