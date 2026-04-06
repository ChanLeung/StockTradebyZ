from collections import Counter
from datetime import date

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


def _candidate_score(candidate: Candidate) -> float:
    return candidate.buy_review_score if candidate.buy_review_score is not None else float("-inf")


def _count_bucket_exposure(positions: list[Position], mapping: dict[str, str] | None) -> Counter:
    counter: Counter = Counter()
    if not mapping:
        return counter
    for position in positions:
        bucket = mapping.get(position.code)
        if bucket:
            counter[bucket] += 1
    return counter


def select_buy_candidates(
    candidates: list[Candidate],
    *,
    max_positions: int,
    existing_positions: list[Position],
    excluded_codes: set[str] | None = None,
    stock_to_index: dict[str, str] | None = None,
    max_same_index: int | None = None,
    stock_to_industry: dict[str, str] | None = None,
    max_same_industry: int | None = None,
    min_buy_score: float = 4.0,
) -> tuple[list[Candidate], dict[str, list[str]]]:
    existing_codes = {position.code for position in existing_positions}
    excluded_codes = set(excluded_codes or set())
    index_counts = _count_bucket_exposure(existing_positions, stock_to_index)
    industry_counts = _count_bucket_exposure(existing_positions, stock_to_industry)
    available_slots = max(max_positions - len(existing_positions), 0)
    selected: list[Candidate] = []
    rejected = {
        "below_pass": [],
        "existing": [],
        "excluded": [],
        "index_limit": [],
        "industry_limit": [],
    }

    for candidate in sorted(candidates, key=_candidate_score, reverse=True):
        score = _candidate_score(candidate)
        if score < min_buy_score:
            rejected["below_pass"].append(candidate.code)
            continue
        if candidate.code in existing_codes:
            rejected["existing"].append(candidate.code)
            continue
        if candidate.code in excluded_codes:
            rejected["excluded"].append(candidate.code)
            continue

        index_name = (stock_to_index or {}).get(candidate.code)
        if max_same_index is not None and index_name and index_counts[index_name] >= max_same_index:
            rejected["index_limit"].append(candidate.code)
            continue

        industry_name = (stock_to_industry or {}).get(candidate.code)
        if max_same_industry is not None and industry_name and industry_counts[industry_name] >= max_same_industry:
            rejected["industry_limit"].append(candidate.code)
            continue

        selected.append(candidate)
        existing_codes.add(candidate.code)
        if index_name:
            index_counts[index_name] += 1
        if industry_name:
            industry_counts[industry_name] += 1

        if len(selected) >= available_slots:
            break

    return selected, rejected


def _compute_holding_days(entry_date: str, signal_date: str) -> int:
    return max((date.fromisoformat(signal_date) - date.fromisoformat(entry_date)).days, 0)


def plan_watch_replacements(
    candidates: list[Candidate],
    *,
    current_positions: list[Position],
    sell_reviews: dict[str, dict],
    signal_date: str,
    max_daily_replacements: int,
    max_positions: int,
    sold_today_codes: set[str] | None = None,
    stock_to_index: dict[str, str] | None = None,
    max_same_index: int | None = None,
    stock_to_industry: dict[str, str] | None = None,
    max_same_industry: int | None = None,
    min_buy_score: float = 4.0,
) -> list[dict]:
    if max_daily_replacements <= 0:
        return []

    replaceable = [
        position
        for position in current_positions
        if str(sell_reviews.get(position.code, {}).get("verdict", "")).upper() == "WATCH"
    ]
    replaceable = sorted(
        replaceable,
        key=lambda position: (
            -float(sell_reviews.get(position.code, {}).get("total_score", 0.0)),
            -len(sell_reviews.get(position.code, {}).get("risk_flags", [])),
            -_compute_holding_days(position.entry_date, signal_date),
            position.code,
        ),
    )

    planned: list[dict] = []
    virtual_positions = list(current_positions)
    reserved_new_codes: set[str] = set()
    all_current_codes = {position.code for position in current_positions}

    for position in replaceable:
        if len(planned) >= max_daily_replacements:
            break

        base_positions = [item for item in virtual_positions if item.code != position.code]
        selected_candidates, _ = select_buy_candidates(
            candidates,
            max_positions=max_positions,
            existing_positions=base_positions,
            excluded_codes=set(sold_today_codes or set()) | reserved_new_codes | all_current_codes,
            stock_to_index=stock_to_index,
            max_same_index=max_same_index,
            stock_to_industry=stock_to_industry,
            max_same_industry=max_same_industry,
            min_buy_score=min_buy_score,
        )
        if not selected_candidates:
            continue

        new_candidate = selected_candidates[0]
        planned.append(
            {
                "old_position": position,
                "new_candidate": new_candidate,
            }
        )
        reserved_new_codes.add(new_candidate.code)
        virtual_positions = [
            *base_positions,
            Position(
                code=new_candidate.code,
                entry_date=signal_date,
                entry_price=new_candidate.close,
                weight=0.0,
            ),
        ]

    return planned


def build_target_positions(
    candidates: list[Candidate],
    *,
    as_of_date: str,
    max_positions: int = 10,
) -> list[Position]:
    ranked, _ = select_buy_candidates(
        candidates,
        max_positions=max_positions,
        existing_positions=[],
    )

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
