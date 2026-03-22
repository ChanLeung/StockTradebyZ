from pipeline.schemas import Candidate
from trading.schemas import Position


def build_target_positions(
    candidates: list[Candidate],
    *,
    as_of_date: str,
    max_positions: int = 10,
) -> list[Position]:
    ranked = sorted(
        candidates,
        key=lambda candidate: candidate.buy_review_score if candidate.buy_review_score is not None else float("-inf"),
        reverse=True,
    )[:max_positions]

    if not ranked:
        return []

    weight = round(1.0 / len(ranked), 10)
    return [
        Position(
            code=candidate.code,
            entry_date=as_of_date,
            entry_price=candidate.close,
            weight=weight,
        )
        for candidate in ranked
    ]
