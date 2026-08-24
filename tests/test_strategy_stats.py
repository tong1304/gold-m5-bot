def aggregate(candidates, final_results):
    stats = {}
    for c in candidates:
        name = c["strategy"]
        s = stats.setdefault(name, {"evaluated": 0, "pass": 0, "fail": 0, "final_selected": 0, "wins": 0, "losses": 0, "net_r": 0.0})
        s["evaluated"] += 1
        s[c["status"]] += 1
    for r in final_results:
        name = r["strategy"]
        s = stats.setdefault(name, {"evaluated": 0, "pass": 0, "fail": 0, "final_selected": 0, "wins": 0, "losses": 0, "net_r": 0.0})
        s["final_selected"] += 1
        if r["result"] == "WIN":
            s["wins"] += 1
            s["net_r"] += 2.0
        elif r["result"] == "LOSS":
            s["losses"] += 1
            s["net_r"] -= 1.0
    return stats


def test_pass_is_distinct_from_final_selected():
    stats = aggregate(
        [{"strategy":"TREND_PULLBACK","status":"pass"}, {"strategy":"BREAKOUT_RETEST","status":"pass"}],
        [{"strategy":"TREND_PULLBACK","result":"WIN"}],
    )
    assert stats["TREND_PULLBACK"]["pass"] == 1
    assert stats["BREAKOUT_RETEST"]["pass"] == 1
    assert stats["TREND_PULLBACK"]["final_selected"] == 1
    assert stats["BREAKOUT_RETEST"]["final_selected"] == 0
