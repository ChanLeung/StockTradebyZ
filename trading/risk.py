from trading.schemas import RiskState


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
