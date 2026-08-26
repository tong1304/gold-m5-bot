from .professional_regime import ProfessionalE2Brain


class SubEngine(ProfessionalE2Brain):
    def _analyse(self, d):
        output, confidence, reasons = super()._analyse(d)
        output["specialist_role"] = "MEAN_REVERSION_BEHAVIOR"
        output["state"] = "MEAN_REVERSION" if output.get("regime") == "MEAN_REVERSION" else "NOT_MEAN_REVERSION"
        return output, confidence, reasons
