from trading.risk import evaluate_risk_state


def test_risk_off_blocks_new_positions_when_proxy_breaks():
    state = evaluate_risk_state(
        {
            "a_share_break": True,
            "macro_risk": False,
            "manual_risk_off": False,
        }
    )

    assert state.mode == "risk_off"
    assert state.allow_new_entries is False
    assert state.max_total_exposure == 0.5


def test_normal_risk_state_allows_new_positions():
    state = evaluate_risk_state(
        {
            "a_share_break": False,
            "macro_risk": False,
            "manual_risk_off": False,
        }
    )

    assert state.mode == "normal"
    assert state.allow_new_entries is True
    assert state.max_total_exposure == 1.0
