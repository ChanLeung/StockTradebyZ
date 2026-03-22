import pandas as pd

from trading.risk import build_risk_signals, evaluate_risk_state


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


def test_build_risk_signals_uses_thresholds_and_manual_switch():
    benchmarks = pd.DataFrame({"ALLA": [-0.03]}, index=["2026-01-06"])
    risk_proxies = pd.DataFrame({"US_EQ": [-0.04]}, index=["2026-01-06"])

    signals = build_risk_signals(
        ["2026-01-06"],
        benchmarks,
        risk_proxies,
        {"a_share_break_lte": -0.02, "macro_move_abs": 0.03},
        manual_risk_off=True,
    )

    assert signals["2026-01-06"]["a_share_break"] is True
    assert signals["2026-01-06"]["macro_risk"] is True
    assert signals["2026-01-06"]["manual_risk_off"] is True
