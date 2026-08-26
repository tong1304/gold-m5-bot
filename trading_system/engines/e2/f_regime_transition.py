from .professional_regime import ProfessionalE2Brain


class SubEngine(ProfessionalE2Brain):
    def _analyse(self, d):
        output, confidence, reasons = super()._analyse(d)
        output["specialist_role"] = "REGIME_TRANSITION"
        output["state"] = "TRANSITION" if output.get("regime") == "TRANSITION" else "STABLE_REGIME"
        return output, confidence, reasons
