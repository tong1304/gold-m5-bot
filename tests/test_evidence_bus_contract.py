from production_v2.engines import EVIDENCE_INPUTS, _legacy_context, run_engine


def test_upstream_context_excludes_decisions_and_gates():
    context = _legacy_context({
        "E3": {
            "engine_id": "E3",
            "evidence": {
                "3B": {"output": {"state": "BULLISH"}, "decision": "BUY", "gate": True},
            },
            "decision": "BUY",
            "gate": True,
        }
    })
    item = context["E3_result"]["3B"]
    assert item["output"] == {"state": "BULLISH"}
    assert "decision" not in item
    assert "gate" not in item


def test_engine_reports_all_peer_evidence_contract():
    peers = {engine_id: {"engine_id": engine_id, "evidence": {}} for engine_id in EVIDENCE_INPUTS["E2"]}
    result = run_engine("E2", {"bars": _bars(60), "symbol": "XAU/USD", "timeframe": "M5"}, peers)
    report = result.output["evidence_dependency"]
    assert report["required"] == sorted(EVIDENCE_INPUTS["E2"])
    assert report["received"] == sorted(EVIDENCE_INPUTS["E2"])
    assert report["missing"] == []
    assert report["decisions_received"] is False
    assert report["gates_received"] is False
    assert result.gate_passed is None


def test_engine_reports_partial_peer_evidence_without_claiming_completion():
    result = run_engine("E5", {"bars": _bars(60), "symbol": "XAU/USD", "timeframe": "M5"}, {
        "E3": {"engine_id": "E3", "evidence": {}},
    })
    report = result.output["evidence_dependency"]
    assert report["required"] == sorted(EVIDENCE_INPUTS["E5"])
    assert report["received"] == ["E3"]
    assert "E3" in report["received"]
    assert set(report["missing"]) == set(report["required"]) - {"E3"}


def _bars(n):
    return [
        {"open": 100 + i * 0.1, "high": 100.5 + i * 0.1, "low": 99.5 + i * 0.1, "close": 100.2 + i * 0.1, "volume": 1000}
        for i in range(n)
    ]
