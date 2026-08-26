from production_v2.e1_brain import analyze_e1


def _bars(closes, spread=0.1):
    rows = []
    prev = closes[0]
    for i, close in enumerate(closes):
        rows.append({"open": prev, "high": max(prev, close) + spread, "low": min(prev, close) - spread, "close": close, "timestamp": i})
        prev = close
    return rows


def test_e1_exposes_independent_five_state_evidence_and_opportunity_environment():
    out = analyze_e1(_bars([100 + 0.25 * i for i in range(100)]))
    r = out["professional_reasoning"]
    assert set(r["evidence_dimensions"]) == {"trend", "range", "compression", "expansion", "transition"}
    assert "opportunity_environment" in r
    assert "uncertainties" in r


def test_e1_does_not_call_bullish_pressure_a_trend_when_ema_and_structure_conflict():
    # Strong recent bullish structure/pressure while EMA20 remains below EMA50.
    closes = [120 - 0.22 * i for i in range(65)] + [105 + 0.70 * (i - 64) for i in range(35)]
    out = analyze_e1(_bars(closes, spread=0.15))
    r = out["professional_reasoning"]
    assert r["conflict_matrix"]["ema_vs_structure"] is True
    assert r["trend_quality"] < 0.70
    assert out["market_state"] in {"TRANSITION", "UNCLEAR", "EXPANSION"}
    assert "ema_structure_disagreement" in r["uncertainties"]


def test_e1_requires_structural_progression_and_persistence_not_indicator_vote_count():
    # EMA/slope can be positive, but repeated structural progression is absent.
    closes = [100 + (0.45 if i % 2 == 0 else -0.10) for i in range(100)]
    out = analyze_e1(_bars(closes, spread=0.2))
    r = out["professional_reasoning"]
    assert r["trend_quality"] < 0.70
    assert out["trend_state"] == "NONE"
    assert out["market_state"] in {"RANGE", "UNCLEAR", "COMPRESSION", "TRANSITION"}


def test_e1_uses_optional_mtf_as_context_not_as_an_override():
    m5 = _bars([100 + 0.35 * i for i in range(100)])
    m15 = _bars([100 - 0.20 * i for i in range(100)])
    h1 = _bars([100 - 0.10 * i for i in range(100)])
    out = analyze_e1(m5, m15_bars=m15, h1_bars=h1)
    mtf = out["professional_reasoning"]["mtf_context"]
    assert mtf["available"] is True
    assert mtf["m5_primary"] is True
    assert mtf["override_m5"] is False
    assert mtf["conflict"] is True
    assert "mtf_context_conflict" in out["professional_reasoning"]["uncertainties"]


def test_e1_confidence_is_classification_confidence_and_is_penalized_by_unresolved_conflicts():
    clean = analyze_e1(_bars([100 + 0.25 * i for i in range(100)]))
    conflict = analyze_e1(
        _bars([120 - 0.22 * i for i in range(65)] + [105 + 0.70 * (i - 64) for i in range(35)], spread=0.15),
        m15_bars=_bars([100 - 0.20 * i for i in range(100)]),
        h1_bars=_bars([100 - 0.10 * i for i in range(100)]),
    )
    assert conflict["confidence"] < clean["confidence"]
    assert conflict["confidence"] <= 1.0
    assert conflict["professional_reasoning"]["confidence_meaning"] == "MARKET_STATE_CLASSIFICATION_ONLY"
