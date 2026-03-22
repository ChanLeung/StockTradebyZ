from __future__ import annotations

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
    for snapshot in result.daily_snapshots:
        cumulative_benchmark *= 1.0 + snapshot.benchmark_return

    return {
        "snapshot_count": snapshot_count,
        "trade_count": trade_count,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "avg_position_count": avg_position_count,
        "final_cash": result.daily_snapshots[-1].cash if result.daily_snapshots else 0.0,
        "cumulative_benchmark_return": round(cumulative_benchmark - 1.0, 6),
    }


def build_signal_sheet(result: BacktestResult) -> dict:
    buy_list = [order.code for order in result.pending_orders if order.side == "buy"]
    sell_list = [order.code for order in result.pending_orders if order.side == "sell"]

    return {
        "buy_list": buy_list,
        "sell_list": sell_list,
    }
