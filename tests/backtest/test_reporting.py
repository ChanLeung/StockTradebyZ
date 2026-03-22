import pytest

from backtest.engine import BacktestResult
from backtest.reporting import build_signal_sheet, summarize_backtest
from trading.schemas import BacktestDailySnapshot, Order, TradeFill


def test_build_signal_sheet_splits_buy_and_sell_actions():
    result = BacktestResult(
        daily_snapshots=[
            BacktestDailySnapshot(
                date="2026-01-07",
                cash=50000.0,
                position_count=2,
                benchmark_return=0.01,
            )
        ],
        trades=[
            TradeFill(code="600000", side="buy", quantity=100, fill_price=10.8),
            TradeFill(code="000001", side="sell", quantity=100, fill_price=9.6),
        ],
        pending_orders=[
            Order(code="600000", side="buy", quantity=100),
            Order(code="000001", side="sell", quantity=100),
        ],
    )

    sheet = build_signal_sheet(result)

    assert {"buy_list", "sell_list"} <= set(sheet)
    assert sheet["buy_list"] == ["600000"]
    assert sheet["sell_list"] == ["000001"]


def test_summarize_backtest_counts_days_trades_and_benchmark():
    result = BacktestResult(
        initial_cash=50000.0,
        daily_snapshots=[
            BacktestDailySnapshot(
                date="2026-01-07",
                cash=50000.0,
                position_count=2,
                benchmark_return=0.01,
                market_value=1000.0,
                equity=51000.0,
            ),
            BacktestDailySnapshot(
                date="2026-01-08",
                cash=48000.0,
                position_count=1,
                benchmark_return=-0.02,
                market_value=1500.0,
                equity=49500.0,
            ),
        ],
        trades=[
            TradeFill(code="600000", side="buy", quantity=100, fill_price=10.8),
            TradeFill(code="000001", side="sell", quantity=100, fill_price=9.6),
        ],
    )

    summary = summarize_backtest(result)

    assert summary["snapshot_count"] == 2
    assert summary["trade_count"] == 2
    assert summary["buy_count"] == 1
    assert summary["sell_count"] == 1
    assert summary["avg_position_count"] == 1.5
    assert summary["final_cash"] == 48000.0
    assert summary["ending_equity"] == 49500.0
    assert summary["total_return"] == -0.01
    assert summary["excess_return"] == pytest.approx(0.0002)
    assert summary["cumulative_benchmark_return"] == -0.0102
