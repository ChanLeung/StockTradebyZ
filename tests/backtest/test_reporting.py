import pytest

from backtest.engine import BacktestResult
from backtest.reporting import build_signal_sheet, summarize_backtest
from trading.schemas import BacktestDailySnapshot, Order, PortfolioState, Position, RiskState, TradeFill


def test_build_signal_sheet_splits_buy_and_sell_actions():
    result = BacktestResult(
        signal_state=PortfolioState(
            cash=50000.0,
            positions=[
                Position(code="000001", entry_date="2026-01-06", entry_price=9.5, weight=1.0),
            ],
        ),
        final_state=PortfolioState(
            cash=48000.0,
            positions=[
                Position(code="600000", entry_date="2026-01-07", entry_price=10.8, weight=0.5),
            ],
        ),
        last_signal_date="2026-01-07",
        last_trade_date="2026-01-08",
        last_risk_state=RiskState(mode="risk_off", allow_new_entries=False, max_total_exposure=0.5),
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
    assert sheet["signal_date"] == "2026-01-07"
    assert sheet["trade_date"] == "2026-01-08"
    assert sheet["risk_state"]["mode"] == "risk_off"
    assert sheet["cash"] == 50000.0
    assert sheet["current_holdings"][0]["code"] == "000001"
    assert sheet["next_holdings"][0]["code"] == "600000"


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
    assert summary["max_drawdown"] == pytest.approx(-0.029412, abs=1e-6)
    assert summary["cumulative_benchmark_return"] == -0.0102
