from pipeline.schemas import Candidate
from trading.schemas import Position


def apply_risk_budget(
    positions: list[Position],
    *,
    max_total_exposure: float,
    max_positions: int,
) -> tuple[list[Position], list[Position]]:
    allowed_positions = max(int(max_positions * max_total_exposure), 0)
    if len(positions) <= allowed_positions:
        return positions, []
    return positions[:allowed_positions], positions[allowed_positions:]


def apply_sell_decisions(
    positions: list[Position],
    sell_decisions: dict[str, str],
) -> list[Position]:
    return [
        position
        for position in positions
        if sell_decisions.get(position.code, "hold") != "sell"
    ]


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
