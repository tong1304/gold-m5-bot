from production_v2.e3_brain import analyze_e3
from production_v2.engines import run_engine, SUB_ENGINE_CODES


def _bars(n=80):
    bars=[]
    price=100.0
    for i in range(n):
        drift=0.30 if i < 60 else 0.75
        close=price+drift
        bars.append({"open":price,"high":close+0.25,"low":price-0.20,"close":close})
        price=close
    return bars


def test_e3_is_single_brain_and_subengines_are_parked():
    assert SUB_ENGINE_CODES["E3"] == []
    result=run_engine("E3", {"bars":_bars()})
    assert result.engine_id == "E3"
    assert result.output["specialists_active"] is False
    assert result.output["specialists_status"] == "PAUSED"
    assert result.output["trade_decision_authority"] is False
    assert result.output["gate"] is None


def test_e3_never_consumes_upstream_direction():
    bars=_bars()
    first=analyze_e3(bars)
    second=run_engine("E3", {"bars":bars, "E1_result":{"direction":"DOWN"}, "E2_result":{"direction":"DOWN"}})
    assert first["direction"] == second.output["direction"]
    assert second.output["upstream_direction_used"] is False


def test_e3_exposes_structural_evidence_contract():
    result=analyze_e3(_bars())
    for key in ("swing_map","internal_structure","external_structure","bos","failure","structure_strength","confidence","evidence"):
        assert key in result
    assert result["bos"]["event"] in {"NO_BOS","CONFIRMED_BOS"}
    assert result["failure"]["event"] in {"NO_FAILURE","FAILED_BOS"}
