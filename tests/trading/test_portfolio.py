from pipeline.schemas import Candidate
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
