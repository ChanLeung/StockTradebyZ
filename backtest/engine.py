from __future__ import annotations

from dataclasses import dataclass, field

from trading.benchmark import build_position_benchmark_weights, compute_dynamic_benchmark_return
from trading.orders import compute_trade_cash_effect, simulate_open_fill
from trading.portfolio import apply_risk_budget, apply_sell_decisions, build_target_positions
from trading.risk import evaluate_risk_state
from trading.schemas import BacktestDailySnapshot, Order, PortfolioState, Position, TradeFill


@dataclass
class BacktestResult:
    initial_cash: float = 0.0
    daily_snapshots: list[BacktestDailySnapshot] = field(default_factory=list)
    trades: list[TradeFill] = field(default_factory=list)
    pending_orders: list[Order] = field(default_factory=list)
    final_state: PortfolioState = field(default_factory=lambda: PortfolioState(cash=0.0))


def run_backtest(config: dict, data_bundle: dict) -> BacktestResult:
    result = BacktestResult()
    max_positions = int(config.get("max_positions", 10))
    cash = float(config.get("initial_cash", 1_000_000.0))
    result.initial_cash = cash
    cost_config = config.get("costs", {})
    current_positions: list[Position] = []

    for signal_date in sorted(data_bundle.get("daily_candidates", {})):
        candidates = data_bundle["daily_candidates"][signal_date]
        target_positions = build_target_positions(
            candidates,
            as_of_date=_next_trade_date(signal_date, data_bundle),
            max_positions=max_positions,
        )
        trade_date = _next_trade_date(signal_date, data_bundle)
        open_prices = data_bundle["next_open_prices"][trade_date]
        pending_orders: list[Order] = []

        sell_decisions = data_bundle.get("sell_decisions", {}).get(signal_date, {})
        sold_codes: dict[str, str] = {}
        for position in current_positions:
            if sell_decisions.get(position.code) != "sell":
                continue

            order = Order(code=position.code, side="sell", quantity=100)
            pending_orders.append(order)
            fill = simulate_open_fill(
                order,
                open_price=open_prices[position.code],
                high=open_prices[position.code],
                low=open_prices[position.code],
            )
            if fill is not None:
                result.trades.append(fill)
                cash += compute_trade_cash_effect(fill, cost_config)
                sold_codes[position.code] = "sell"

        current_positions = apply_sell_decisions(current_positions, sold_codes)

        risk_state = evaluate_risk_state(
            data_bundle.get("risk_signals", {}).get(signal_date, {})
        )
        kept_positions, trimmed_positions = apply_risk_budget(
            current_positions,
            max_total_exposure=risk_state.max_total_exposure,
            max_positions=max_positions,
        )
        current_positions = list(kept_positions)
        for position in trimmed_positions:
            if position.code not in open_prices:
                current_positions.append(position)
                continue
            order = Order(code=position.code, side="sell", quantity=position.quantity)
            pending_orders.append(order)
            fill = simulate_open_fill(
                order,
                open_price=open_prices[position.code],
                high=open_prices[position.code],
                low=open_prices[position.code],
            )
            if fill is not None:
                result.trades.append(fill)
                cash += compute_trade_cash_effect(fill, cost_config)
            else:
                current_positions.append(position)

        existing_codes = {position.code for position in current_positions}
        available_slots = max(max_positions - len(current_positions), 0)
        buy_targets: list[Position] = []
        if risk_state.allow_new_entries and available_slots > 0:
            for position in target_positions:
                if position.code in existing_codes:
                    continue
                buy_targets.append(position)
                if len(buy_targets) >= available_slots:
                    break

        for position in buy_targets:
            order = Order(code=position.code, side="buy", quantity=100)
            pending_orders.append(order)
            fill = simulate_open_fill(
                order,
                open_price=open_prices[position.code],
                high=open_prices[position.code],
                low=open_prices[position.code],
            )
            if fill is not None:
                result.trades.append(fill)
                cash += compute_trade_cash_effect(fill, cost_config)
                current_positions.append(
                    Position(
                        code=position.code,
                        entry_date=trade_date,
                        entry_price=fill.fill_price,
                        weight=position.weight,
                    )
                )

        result.pending_orders = pending_orders

        weights = build_position_benchmark_weights(current_positions, data_bundle["stock_to_index"])
        benchmark_return = compute_dynamic_benchmark_return(
            weights,
            data_bundle["benchmark_returns"],
            trade_date,
        )
        market_value = sum(
            float(open_prices.get(position.code, position.entry_price)) * position.quantity
            for position in current_positions
        )
        result.daily_snapshots.append(
            BacktestDailySnapshot(
                date=trade_date,
                cash=cash,
                position_count=len(current_positions),
                benchmark_return=benchmark_return,
                market_value=market_value,
                equity=cash + market_value,
            )
        )

    result.final_state = PortfolioState(cash=cash, positions=list(current_positions))
    return result


def _next_trade_date(signal_date: str, data_bundle: dict) -> str:
    available_dates = sorted(data_bundle.get("next_open_prices", {}).keys())
    for date in available_dates:
        if date > signal_date:
            return date
    raise ValueError(f"找不到 {signal_date} 之后的下一个交易日开盘数据")
