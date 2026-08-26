from production_v2.e9_learning import DecisionRecord, OutcomeRecord
from production_v2.e9_replay_feedback import attach_outcome, calibration_table


def _record(asset="GOLD", outcome=None):
    return DecisionRecord(
        sample_id=f"sample-{asset}",
        asset=asset,
        decision_timestamp="2026-08-26T05:10:00Z",
        candle_timestamp="2026-08-26T05:10:00Z",
        entry=4650.0,
        direction="BUY",
        thesis_quality=82.0,
        evidence_signature="sig-a",
        outcome=outcome,
    )


def test_attach_outcome_only_adds_future_fields():
    record = _record()
    resolved = attach_outcome(record, OutcomeRecord("WIN", 2.0, 2.3, -0.4, 7), "2026-08-26T06:00:00Z")
    assert record.outcome is None
    assert resolved.outcome == "WIN"
    assert resolved.realized_r == 2.0
    assert resolved.bars_to_resolution == 7


def test_calibration_table_isolated_by_asset(tmp_path):
    path = tmp_path / "journal.jsonl"
    gold = _record("GOLD", "WIN")
    btc = _record("BTC", "LOSS")
    path.write_text("\n".join([
        '{"sample_id":"g","asset":"GOLD","direction":"BUY","evidence_signature":"sig-a","outcome":"WIN","realized_r":2,"mfe_r":2,"mae_r":-0.2}',
        '{"sample_id":"b","asset":"BTC","direction":"BUY","evidence_signature":"sig-a","outcome":"LOSS","realized_r":-1,"mfe_r":0,"mae_r":-1}',
    ]), encoding="utf-8")
    table = calibration_table(path, min_samples=1)
    assert table[("GOLD", "UNRESOLVED", "BUY", "sig-a")].expectancy_r == 2.0
    assert table[("BTC", "UNRESOLVED", "BUY", "sig-a")].expectancy_r == -1.0
