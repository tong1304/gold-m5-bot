from .professional_regime import ProfessionalE2Brain


class SubEngine(ProfessionalE2Brain):
    def _analyse(self, d):
        output, confidence, reasons = super()._analyse(d)
        output["specialist_role"] = "TREND_REGIME"
        output["state"] = "TREND" if output.get("regime") == "TREND" else "NOT_TREND"
        return output, confidence, reasons
