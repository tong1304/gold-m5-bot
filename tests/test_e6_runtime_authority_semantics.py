from types import SimpleNamespace

from production_v2.contracts import EngineResult
from production_v2 import e6_runtime_authority


def test_runtime_authority_rewrites_legacy_no_setup_finding_when_watch_is_preserved():
    legacy_watch = EngineResult(
        "E6",
        "E6",
        False,
        52.0,
        {
            "setup": "OPPORTUNITY_WATCH",
            "candidate_type": "OPPORTUNITY_CANDIDATE",
            "direction": "BUY",
            "stage": "FORMING",
            "watch_only": True,
            "trade_ready": False,
            "gate_passed": False,
            "finding": "No causal setup hypothesis survives current closed-candle evidence.",
            "missing_proof": ["E6_CAUSAL_SETUP_PROOF", "E7_CONFIRMATION"],
            "reason_codes": ["E2_OPPORTUNITY_CONFIRMATION"],
        },
        (),
    )
    fake_module = SimpleNamespace(
        analyze_e6=lambda market_data, upstream: legacy_watch,
    )

    e6_runtime_authority.install(fake_module)
    result = fake_module.analyze_e6({"bars": []}, {})

    assert result.output["setup"] == "OPPORTUNITY_WATCH"
    assert result.output["candidate_type"] == "OPPORTUNITY_CANDIDATE"
    assert result.output["watch_only"] is True
    assert "No causal setup hypothesis survives" not in result.output["finding"]
    assert "opportunity" in result.output["finding"].lower()
    assert "not yet proven" in result.output["finding"].lower()
