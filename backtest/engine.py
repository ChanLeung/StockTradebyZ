from __future__ import annotations

from dataclasses import dataclass, field

from trading.benchmark import build_position_benchmark_weights, compute_dynamic_benchmark_return
from trading.orders import simulate_open_fill
from trading.portfolio import build_target_positions
from trading.schemas import BacktestDailySnapshot, Order, TradeFill


@dataclass
class BacktestResult:
    daily_snapshots: list[BacktestDailySnapshot] = field(default_factory=list)
    trades: list[TradeFill] = field(default_factory=list)


def run_backtest(config: dict, data_bundle: dict) -> BacktestResult:
    result = BacktestResult()
    max_positions = int(config.get("max_positions", 10))

    for signal_date, candidates in data_bundle.get("daily_candidates", {}).items():
        target_positions = build_target_positions(
            candidates,
            as_of_date=_next_trade_date(signal_date, data_bundle),
            max_positions=max_positions,
        )
        trade_date = _next_trade_date(signal_date, data_bundle)
        open_prices = data_bundle["next_open_prices"][trade_date]

        for position in target_positions:
            fill = simulate_open_fill(
                Order(code=position.code, side="buy", quantity=100),
                open_price=open_prices[position.code],
                high=open_prices[position.code],
                low=open_prices[position.code],
            )
            if fill is not None:
                result.trades.append(fill)

        weights = build_position_benchmark_weights(target_positions, data_bundle["stock_to_index"])
        benchmark_return = compute_dynamic_benchmark_return(
            weights,
            data_bundle["benchmark_returns"],
            trade_date,
        )
        result.daily_snapshots.append(
            BacktestDailySnapshot(
                date=trade_date,
                cash=0.0,
                position_count=len(target_positions),
                benchmark_return=benchmark_return,
            )
        )

    return result


def _next_trade_date(signal_date: str, data_bundle: dict) -> str:
    available_dates = sorted(data_bundle.get("next_open_prices", {}).keys())
    for date in available_dates:
        if date > signal_date:
            return date
    raise ValueError(f"找不到 {signal_date} 之后的下一个交易日开盘数据")
