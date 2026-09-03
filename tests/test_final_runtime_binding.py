from types import SimpleNamespace

from production_v2.final_runtime_binding import install


def test_final_binding_reasserts_e6_e8_e9_before_each_run():
    calls = []

    def original_run(self, market_data, *, wait_bars=0, resume_state=None, historical_calibration=None):
        calls.append((pipeline.analyze_e6, pipeline.analyze_e8, pipeline.analyze_e9))
        return "ok"

    class Pipeline:
        run = original_run

    pipeline = SimpleNamespace(ProductionPipeline=Pipeline)
    e6 = SimpleNamespace(analyze_e6=lambda *_: "guarded-e6")
    e8 = SimpleNamespace(analyze_e8=lambda *_: "guarded-e8")
    e9 = SimpleNamespace(analyze_e9=lambda *_: "guarded-e9")

    install(pipeline, e6, e8, e9)

    # Simulate a later startup wrapper replacing the pipeline references.
    pipeline.analyze_e6 = lambda *_: "stale-e6"
    pipeline.analyze_e8 = lambda *_: "stale-e8"
    pipeline.analyze_e9 = lambda *_: "stale-e9"

    assert pipeline.ProductionPipeline().run({}) == "ok"
    assert calls == [(e6.analyze_e6, e8.analyze_e8, e9.analyze_e9)]
