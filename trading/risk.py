import pandas as pd

from trading.schemas import RiskState


def build_risk_signals(
    signal_dates: list[str],
    benchmarks: pd.DataFrame,
    risk_proxies: pd.DataFrame,
    thresholds: dict[str, float] | None = None,
    *,
    manual_risk_off: bool = False,
) -> dict[str, dict[str, bool]]:
    resolved = {
        "a_share_break_lte": -0.02,
        "macro_move_abs": 0.03,
        **(thresholds or {}),
    }
    signals: dict[str, dict[str, bool]] = {}

    for signal_date in signal_dates:
        a_share_value = 0.0
        if not benchmarks.empty and signal_date in benchmarks.index and "ALLA" in benchmarks.columns:
            a_share_value = float(benchmarks.loc[signal_date, "ALLA"])

        macro_risk = False
        if not risk_proxies.empty and signal_date in risk_proxies.index:
            row = risk_proxies.loc[signal_date]
            macro_risk = any(abs(float(value)) >= float(resolved["macro_move_abs"]) for value in row.to_dict().values())

        signals[signal_date] = {
            "a_share_break": a_share_value <= float(resolved["a_share_break_lte"]),
            "macro_risk": macro_risk,
            "manual_risk_off": manual_risk_off,
        }

    return signals


def evaluate_risk_state(signals: dict[str, bool]) -> RiskState:
    risk_off = any(
        [
            signals.get("a_share_break", False),
            signals.get("macro_risk", False),
            signals.get("manual_risk_off", False),
        ]
    )

    if risk_off:
        return RiskState(mode="risk_off", allow_new_entries=False, max_total_exposure=0.5)

    return RiskState(mode="normal", allow_new_entries=True, max_total_exposure=1.0)
