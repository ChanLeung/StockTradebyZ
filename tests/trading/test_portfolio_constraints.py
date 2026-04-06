from pipeline.schemas import Candidate
from trading.portfolio import select_buy_candidates
from trading.schemas import Position


def test_select_buy_candidates_keeps_only_pass_scored_candidates():
    candidates = [
        Candidate(code="600000", date="2026-01-06", strategy="b1", close=10.0, turnover_n=1000.0, buy_review_score=4.2),
        Candidate(code="000001", date="2026-01-06", strategy="b1", close=9.0, turnover_n=900.0, buy_review_score=3.9),
    ]

    selected, rejected = select_buy_candidates(
        candidates,
        max_positions=10,
        existing_positions=[],
    )

    assert [candidate.code for candidate in selected] == ["600000"]
    assert rejected["below_pass"] == ["000001"]


def test_select_buy_candidates_applies_index_limit():
    candidates = [
        Candidate(code=f"60000{idx}", date="2026-01-06", strategy="b1", close=10.0 + idx, turnover_n=1000.0, buy_review_score=4.9 - idx * 0.1)
        for idx in range(5)
    ]
    stock_to_index = {candidate.code: "CSI2000" for candidate in candidates}

    selected, rejected = select_buy_candidates(
        candidates,
        max_positions=10,
        existing_positions=[],
        stock_to_index=stock_to_index,
        max_same_index=4,
    )

    assert len(selected) == 4
    assert [candidate.code for candidate in selected] == [f"60000{idx}" for idx in range(4)]
    assert rejected["index_limit"] == ["600004"]


def test_select_buy_candidates_applies_industry_limit():
    candidates = [
        Candidate(code="600000", date="2026-01-06", strategy="b1", close=10.0, turnover_n=1000.0, buy_review_score=4.9),
        Candidate(code="600001", date="2026-01-06", strategy="b1", close=11.0, turnover_n=1000.0, buy_review_score=4.8),
        Candidate(code="600002", date="2026-01-06", strategy="b1", close=12.0, turnover_n=1000.0, buy_review_score=4.7),
    ]
    stock_to_industry = {candidate.code: "有色金属" for candidate in candidates}

    selected, rejected = select_buy_candidates(
        candidates,
        max_positions=10,
        existing_positions=[],
        stock_to_industry=stock_to_industry,
        max_same_industry=2,
    )

    assert [candidate.code for candidate in selected] == ["600000", "600001"]
    assert rejected["industry_limit"] == ["600002"]


def test_select_buy_candidates_allows_missing_industry_mapping():
    candidates = [
        Candidate(code="600000", date="2026-01-06", strategy="b1", close=10.0, turnover_n=1000.0, buy_review_score=4.9),
        Candidate(code="600001", date="2026-01-06", strategy="b1", close=11.0, turnover_n=1000.0, buy_review_score=4.8),
        Candidate(code="600002", date="2026-01-06", strategy="b1", close=12.0, turnover_n=1000.0, buy_review_score=4.7),
    ]

    selected, rejected = select_buy_candidates(
        candidates,
        max_positions=10,
        existing_positions=[
            Position(code="000001", entry_date="2026-01-05", entry_price=9.0, weight=0.1, quantity=100),
        ],
        stock_to_industry={"000001": "有色金属", "600000": "有色金属"},
        max_same_industry=1,
    )

    assert [candidate.code for candidate in selected] == ["600001", "600002"]
    assert rejected["industry_limit"] == ["600000"]
