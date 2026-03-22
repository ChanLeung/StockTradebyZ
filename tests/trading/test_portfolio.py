from pipeline.schemas import Candidate
from trading.portfolio import apply_risk_budget, apply_sell_decisions, build_target_positions
from trading.schemas import PortfolioState, Position


def test_portfolio_state_tracks_positions_and_cash():
    state = PortfolioState(cash=100000, positions=[])

    assert state.cash == 100000
    assert state.positions == []


def test_candidate_keeps_buy_review_trace_fields():
    candidate = Candidate(
        code="600000",
        date="2026-01-06",
        strategy="b1",
        close=10.5,
        turnover_n=123456.0,
        buy_review_score=4.2,
        buy_review_date="2026-01-06",
        buy_prompt_version="buy-v1",
    )

    payload = candidate.to_dict()

    assert payload["buy_review_score"] == 4.2
    assert payload["buy_review_date"] == "2026-01-06"
    assert payload["buy_prompt_version"] == "buy-v1"


def test_position_to_dict_contains_entry_fields():
    position = Position(
        code="600000",
        entry_date="2026-01-07",
        entry_price=10.8,
        weight=0.1,
    )

    payload = position.to_dict()

    assert payload["code"] == "600000"
    assert payload["entry_price"] == 10.8


def test_select_top_candidates_assigns_equal_weights():
    candidates = [
        Candidate(
            code=f"{600000 + idx}",
            date="2026-01-06",
            strategy="b1",
            close=10.0 + idx,
            turnover_n=1000.0 + idx,
            buy_review_score=5.0 - idx * 0.1,
        )
        for idx in range(12)
    ]

    positions = build_target_positions(candidates, as_of_date="2026-01-07", max_positions=10)

    assert len(positions) == 10
    assert {position.weight for position in positions} == {0.1}
    assert positions[0].code == "600000"


def test_apply_sell_decisions_filters_out_sell_positions():
    positions = [
        Position(code="600000", entry_date="2026-01-07", entry_price=10.8, weight=0.5),
        Position(code="000001", entry_date="2026-01-07", entry_price=9.6, weight=0.5),
    ]

    remaining = apply_sell_decisions(
        positions,
        {"600000": "hold", "000001": "sell"},
    )

    assert [position.code for position in remaining] == ["600000"]


def test_apply_risk_budget_trims_positions_by_exposure():
    positions = [
        Position(code=f"{600000 + idx}", entry_date="2026-01-07", entry_price=10.0 + idx, weight=0.25)
        for idx in range(4)
    ]

    kept, trimmed = apply_risk_budget(positions, max_total_exposure=0.5, max_positions=4)

    assert [position.code for position in kept] == ["600000", "600001"]
    assert [position.code for position in trimmed] == ["600002", "600003"]
