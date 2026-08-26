from .professional_regime import ProfessionalE2Brain


class SubEngine(ProfessionalE2Brain):
    def _analyse(self, d):
        output, confidence, reasons = super()._analyse(d)
        output["specialist_role"] = "RANGE_REGIME"
        output["state"] = "RANGE" if output.get("regime") == "RANGE" else "NOT_RANGE"
        return output, confidence, reasons
