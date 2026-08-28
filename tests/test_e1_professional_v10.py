from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
E1_PATH = ROOT / "production_v2" / "e1_professional_layer_v10.py"


def _load_source() -> str:
    return E1_PATH.read_text(encoding="utf-8")


def _bars(closes: list[float]) -> list[dict[str, float]]:
    bars: list[dict[str, float]] = []
    for i, close in enumerate(closes):
        previous = closes[i - 1] if i else close
        open_price = previous
        high = max(open_price, close) + 0.25
        low = min(open_price, close) - 0.25
        bars.append({"open": open_price, "high": high, "low": low, "close": close})
    return bars


def test_v10_has_no_dependency_on_older_e1_layers() -> None:
    tree = ast.parse(_load_source())
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)

    assert not any("e1_professional_layer_v" in name for name in imported)
    assert "e1_brain" not in imported


def test_v10_is_market_state_only_and_exposes_professional_contract() -> None:
    from production_v2.e1_professional_layer_v10 import analyze_e1_professional_v10

    closes = [5000.0 - i * 2.0 for i in range(120)]
    result = analyze_e1_professional_v10(_bars(closes))

    assert result["analysis_status"] == "COMPLETE"
    assert result["market_state"] in {"TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"}
    assert result["dominant_direction"] in {"UP", "DOWN", "NEUTRAL"}
    assert result["e1_trade_authority"] is False
    assert result["trade_decision_authority"] is False
    assert "setup" not in result
    assert "entry" not in result
    assert "risk" not in result
    assert "decision" not in result
    assert result["e1_contract_version"] == "PROFESSIONAL_MARKET_STATE_V10"


def test_v10_does_not_turn_one_counter_candle_into_reversal() -> None:
    from production_v2.e1_professional_layer_v10 import analyze_e1_professional_v10

    closes = [5000.0 - i * 2.0 for i in range(119)]
    closes.append(closes[-1] + 1.0)
    result = analyze_e1_professional_v10(_bars(closes))

    assert result["dominant_direction"] == "DOWN"
    assert result["market_state"] == "TREND_DOWN"
    assert result["counter_pressure"] == "PULLBACK_WITHIN_TREND"
    assert result["transition_confirmed"] is False


def test_v10_withholds_classification_on_bad_data() -> None:
    from production_v2.e1_professional_layer_v10 import analyze_e1_professional_v10

    bars = _bars([5000.0 - i for i in range(80)])
    bars[20]["close"] = "not-a-number"
    result = analyze_e1_professional_v10(bars)

    assert result["analysis_status"] == "INCOMPLETE"
    assert result["market_state"] == "UNCLEAR"
    assert result["dominant_direction"] == "NEUTRAL"
    assert result["trade_decision_authority"] is False
