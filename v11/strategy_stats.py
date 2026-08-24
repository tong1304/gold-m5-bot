def empty_strategy_stat():
    return {"evaluated": 0, "pass": 0, "fail": 0, "not_applicable": 0, "final_selected": 0, "wins": 0, "losses": 0, "open": 0, "ambiguous": 0, "no_trade": 0, "net_r": 0.0, "reasons": {}}


def aggregate_strategy_stats(candidates=None, final_results=None):
    stats = {}
    for candidate in candidates or []:
        name = str(candidate.get("strategy") or "UNKNOWN")
        s = stats.setdefault(name, empty_strategy_stat())
        s["evaluated"] += 1
        status = str(candidate.get("status") or "fail").lower()
        if status not in ("pass", "fail", "not_applicable"):
            status = "fail"
        s[status] += 1
        for reason in candidate.get("reason") or []:
            reason = str(reason)
            s["reasons"][reason] = s["reasons"].get(reason, 0) + 1

    for result in final_results or []:
        name = str(result.get("strategy") or "UNKNOWN")
        s = stats.setdefault(name, empty_strategy_stat())
        s["final_selected"] += 1
        outcome = str(result.get("result") or "NO_TRADE").upper()
        if outcome == "WIN":
            s["wins"] += 1
            s["net_r"] += 2.0
        elif outcome == "LOSS":
            s["losses"] += 1
            s["net_r"] -= 1.0
        elif outcome == "OPEN":
            s["open"] += 1
        elif outcome == "AMBIGUOUS":
            s["ambiguous"] += 1
        else:
            s["no_trade"] += 1
    return stats
