        f"probability_sample={probability.get('sample_size')}", f"expected_value_r={ev_r if ev_r is not None else 'UNAVAILABLE'}",
        f"economic_edge={economics.get('edge_class')}", f"asymmetry={economics.get('asymmetry')}", f"sensitivity={sensitivity.get('state')}",
        f"worst_sensitivity_ev_r={sensitivity.get('worst_ev_r')}", f"risk_budget_state={risk_budget.get('state')}",
        f"position_size={risk_budget.get('position_size')}", f"risk_lifecycle={lifecycle[f'{len(gate) + 1:02d}_FINAL_RISK_GATE']}",
    ]
    if counter: observations.append("vetoes=" + ",".join(counter))
    if missing: observations.append("missing=" + ",".join(missing))

    trade_plan = {
        "valid": bool(data_valid and direction in {"BUY", "SELL"}), "entry": entry, "direction": direction, "stop_loss": stop,
        "structural_stop": structural_stop, "invalidation_basis": stop_model.get("basis"), "invalidation_source": stop_model.get("source"),
        "stop_validity": "STRUCTURAL" if stop_model.get("structural") else "FALLBACK_LOWER_CONFIDENCE", "stop_quality": stop_model.get("quality", 0),
        "target": target.get("level"), "target_source": target.get("source"), "target_quality": target.get("quality", 0), "target_hierarchy_rank": target.get("hierarchy_rank"),
        "target_distance_atr": target.get("distance_atr", 0), "target_candidate_trace": target.get("candidate_trace", []), "target_rejection": target.get("rejection", []),
        "risk_distance": risk, "risk_distance_atr": stop_atr, "reward_distance": reward, "reward_distance_atr": reward / max(atr, 1e-9), "real_rr": real_rr,
        "effective_rr": effective_rr, "break_even_probability": be, "probability": probability.get("value"), "probability_percent": probability.get("percent"),
        "probability_source": probability.get("source"), "probability_quality": probability.get("quality"), "probability_sample_size": probability.get("sample_size"),
        "expected_value_r": ev_r, "expected_value_price": ev_price, "probability_edge": economics.get("probability_edge"), "economic_edge": economics.get("edge_class"),
        "asymmetry": economics.get("asymmetry"), "sensitivity": sensitivity, "risk_budget": risk_budget, "max_adverse_excursion_atr": survival.get("max_adverse_excursion_atr"),
        "p95_adverse_excursion_atr": survival.get("p95_adverse_excursion_atr"), "survival_margin_atr": survival.get("survival_margin_atr"), "survival_state": survival.get("state"),
        "opposing_liquidity": opposing_liquidity, "opposing_liquidity_r": opposing_liquidity_r,
    }
    causal = (f"ENTRY={entry:.6f}->CONFIRMATION={confirmation}->STRUCTURAL_STOP="
              f"{structural_stop if structural_stop is not None else 'NONE'}->STOP="
              f"{stop if stop is not None else 'NONE'}->TARGET="
              f"{target.get('level') if target.get('level') is not None else 'NONE'}->REAL_RR={real_rr:.3f}->"
              f"EFFECTIVE_RR={effective_rr:.3f}->P={p if p is not None else 'NA'}->EV_R="
              f"{ev_r if ev_r is not None else 'NA'}->SENSITIVITY={sensitivity.get('state')}->"
              f"RISK_BUDGET={risk_budget.get('state')}->POSITION_SIZE={risk_budget.get('position_size')}" )
    output = {
        **base, "state": state, "economic_state": state, "risk_gate": lifecycle[f"{len(gate) + 1:02d}_FINAL_RISK_GATE"], "direction": direction, "setup": setup,
        "confirmation": confirmation, "confirmation_trace": confirmation_trace, "trade_plan": trade_plan,
        "structural_evidence": {**levels, "structural_breach": structural_breach, "stop_model": stop_model}, "dynamic_target": target, "location_evidence": space,
        "risk_model": {"atr": atr, "atr_period": ATR_PERIOD, "volatility": volatility, "execution": execution, "stop_stability": stop_stability, "survival": survival},
        "probability_evidence": probability, "trade_economics": economics, "sensitivity_analysis": sensitivity, "risk_budget": risk_budget,
        "gate_matrix": gate, "lifecycle": lifecycle, "counter_evidence": counter, "missing_evidence": missing, "observations": observations,
        "professional_reasoning": {
            "causal_chain": causal,
            "structural_stop_reasoning": f"source={stop_model.get('source') or 'NONE'};quality={stop_model.get('quality', 0):.1f};structural={stop_model.get('structural', False)};fallback_never_counts_as_ready=True",
            "target_hierarchy_reasoning": f"selected={target.get('source') or 'NONE'};rank={target.get('hierarchy_rank')};selection_rule={target.get('selection_rule')};candidates={target.get('candidate_trace', [])}",
            "survival_reasoning": f"state={survival.get('state')};max_AE={survival.get('max_adverse_excursion_atr')};p95_AE={survival.get('p95_adverse_excursion_atr')};margin={survival.get('survival_margin_atr')}",
            "economic_reasoning": f"P={p if p is not None else 'UNAVAILABLE'}%;Effective_RR={effective_rr};BE_P={be};ProbabilityEdge={economics.get('probability_edge')};EV_R={ev_r};EV_price={ev_price};Asymmetry={economics.get('asymmetry')};SensitivityWorstEV={sensitivity.get('worst_ev_r')}",
            "risk_budget_reasoning": f"state={risk_budget.get('state')};budget={risk_budget.get('budget')};risk_distance={risk};point_value={risk_budget.get('point_value')};risk_per_unit={risk_budget.get('risk_per_unit')};position_size={risk_budget.get('position_size')}",
            "causal_risk_reasoning": ";".join(counter + missing) if (counter or missing) else "NO_RISK_VETO",
            "risk_veto": "PASS" if ready else "VETO: " + ";".join(counter + missing + ["ECONOMICS_NOT_READY"]),
        },
        "decision_path": "E8 validates economics, risk, survivability, probability quality, asymmetric payoff, sensitivity and risk-budget sizing only; E9 retains final trade authority.",