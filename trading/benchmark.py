import pandas as pd

from trading.schemas import Position


def build_position_benchmark_weights(
    positions: list[Position], stock_to_index: dict[str, str]
) -> dict[str, float]:
    weights: dict[str, float] = {}
    for position in positions:
        index_name = stock_to_index[position.code]
        weights[index_name] = weights.get(index_name, 0.0) + position.weight
    return weights


def compute_dynamic_benchmark_return(
    benchmark_weights: dict[str, float],
    benchmark_returns: pd.DataFrame,
    date: str,
) -> float:
    row = benchmark_returns.loc[date]
    total = 0.0
    for index_name, weight in benchmark_weights.items():
        total += weight * float(row[index_name])
    return total
