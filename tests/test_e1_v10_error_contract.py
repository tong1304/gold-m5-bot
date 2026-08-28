from production_v2.e1_professional_layer_v10 import _clean_v10_reasons


def test_v10_removes_stale_inherited_data_errors_from_completed_reasoning():
    reasons = [
        "COUNTER_PRESSURE_MONITORED_WITH_TREND_INTACT",
        "V10_DATA_ERROR:TypeError",
        "V9_STATE_CONSISTENCY_CONTRACT",
    ]

    assert _clean_v10_reasons(reasons) == [
        "COUNTER_PRESSURE_MONITORED_WITH_TREND_INTACT",
        "V9_STATE_CONSISTENCY_CONTRACT",
    ]
