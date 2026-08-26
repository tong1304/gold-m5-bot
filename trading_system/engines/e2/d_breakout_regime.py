from .professional_regime import ProfessionalE2Brain


class SubEngine(ProfessionalE2Brain):
    def _analyse(self, d):
        output, confidence, reasons = super()._analyse(d)
        output["specialist_role"] = "BREAKOUT_REGIME"
        output["state"] = "BREAKOUT" if output.get("regime") == "BREAKOUT" else "NOT_BREAKOUT"
        return output, confidence, reasons
