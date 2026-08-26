from .professional_regime import ProfessionalE2Brain


class SubEngine(ProfessionalE2Brain):
    def _analyse(self, d):
        output, confidence, reasons = super()._analyse(d)
        output["specialist_role"] = "REGIME_PHASE"
        output["state"] = output.get("phase", "UNRESOLVED")
        return output, confidence, reasons
