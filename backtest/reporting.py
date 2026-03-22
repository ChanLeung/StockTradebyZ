from __future__ import annotations

from datetime import date

from backtest.engine import BacktestResult


def summarize_backtest(result: BacktestResult) -> dict:
    snapshot_count = len(result.daily_snapshots)
    trade_count = len(result.trades)
    buy_count = sum(1 for trade in result.trades if trade.side == "buy")
    sell_count = sum(1 for trade in result.trades if trade.side == "sell")
    avg_position_count = (
        sum(snapshot.position_count for snapshot in result.daily_snapshots) / snapshot_count
        if snapshot_count
        else 0.0
    )

    cumulative_benchmark = 1.0
    peak_equity = 0.0
    max_drawdown = 0.0
    for snapshot in result.daily_snapshots:
        cumulative_benchmark *= 1.0 + snapshot.benchmark_return
        peak_equity = max(peak_equity, snapshot.equity)
        if peak_equity:
            drawdown = snapshot.equity / peak_equity - 1.0
            max_drawdown = min(max_drawdown, drawdown)
    cumulative_benchmark_return = round(cumulative_benchmark - 1.0, 6)
    ending_equity = result.daily_snapshots[-1].equity if result.daily_snapshots else 0.0
    total_return = (
        round((ending_equity / result.initial_cash) - 1.0, 6)
        if result.initial_cash
        else 0.0
    )

    return {
        "snapshot_count": snapshot_count,
        "trade_count": trade_count,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "avg_position_count": avg_position_count,
        "final_cash": result.daily_snapshots[-1].cash if result.daily_snapshots else 0.0,
        "ending_equity": ending_equity,
        "total_return": total_return,
        "cumulative_benchmark_return": cumulative_benchmark_return,
        "excess_return": round(total_return - cumulative_benchmark_return, 6),
        "max_drawdown": round(max_drawdown, 6),
    }


def build_signal_sheet(result: BacktestResult) -> dict:
    buy_list = [order.code for order in result.pending_orders if order.side == "buy"]
    sell_list = [order.code for order in result.pending_orders if order.side == "sell"]
    active_risk_tags = [
        tag
        for tag, enabled in result.last_risk_signals.items()
        if enabled
    ]
    risk_state = result.last_risk_state.to_dict()
    risk_state["active_risk_tags"] = active_risk_tags
    current_positions = {position.code: position for position in result.signal_state.positions}

    return {
        "signal_date": result.last_signal_date,
        "trade_date": result.last_trade_date,
        "risk_state": risk_state,
        "cash": result.signal_state.cash,
        "current_holdings": [
            _build_current_holding_item(position, result)
            for position in result.signal_state.positions
        ],
        "next_holdings": [position.to_dict() for position in result.final_state.positions],
        "buy_list": buy_list,
        "sell_list": sell_list,
        "buy_orders": [order.to_dict() for order in result.pending_orders if order.side == "buy"],
        "sell_orders": [
            _build_sell_order_item(order, result, current_positions, active_risk_tags)
            for order in result.pending_orders
            if order.side == "sell"
        ],
    }


def _build_current_holding_item(position, result: BacktestResult) -> dict:
    payload = position.to_dict()
    review = result.last_sell_reviews.get(position.code, {})
    payload["holding_days"] = _compute_holding_days(position.entry_date, result.last_signal_date)
    payload["sell_decision"] = review.get("decision", "hold")
    payload["sell_reasoning"] = review.get("reasoning")
    payload["risk_flags"] = list(review.get("risk_flags", []))
    return payload


def _build_sell_order_item(order, result: BacktestResult, current_positions: dict, active_risk_tags: list[str]) -> dict:
    payload = order.to_dict()
    review = result.last_sell_reviews.get(order.code, {})
    current_position = current_positions.get(order.code)
    payload["holding_days"] = (
        _compute_holding_days(current_position.entry_date, result.last_signal_date)
        if current_position is not None
        else None
    )
    payload["reasoning"] = review.get("reasoning")
    payload["risk_flags"] = list(review.get("risk_flags", []))
    if payload["reasoning"] is None and result.last_risk_state.mode == "risk_off":
        payload["reasoning"] = "risk_off 主动降仓"
        if not payload["risk_flags"]:
            payload["risk_flags"] = list(active_risk_tags)
    return payload


def _compute_holding_days(entry_date: str, signal_date: str | None) -> int:
    if signal_date is None:
        return 0
    entry = date.fromisoformat(entry_date)
    signal = date.fromisoformat(signal_date)
    return max((signal - entry).days, 0)
