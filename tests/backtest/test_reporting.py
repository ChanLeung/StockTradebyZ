import pytest

from backtest.engine import BacktestResult
from backtest.reporting import build_signal_sheet, summarize_backtest
from trading.schemas import BacktestDailySnapshot, Order, PortfolioState, Position, RiskState, TradeFill


def test_build_signal_sheet_splits_buy_and_sell_actions():
    result = BacktestResult(
        signal_state=PortfolioState(
            cash=50000.0,
            positions=[
                Position(code="000002", entry_date="2026-01-05", entry_price=10.0, weight=0.5),
                Position(code="000001", entry_date="2026-01-06", entry_price=9.5, weight=1.0),
            ],
        ),
        final_state=PortfolioState(
            cash=48000.0,
            positions=[
                Position(code="600000", entry_date="2026-01-07", entry_price=10.8, weight=1.0),
                Position(code="000002", entry_date="2026-01-05", entry_price=10.0, weight=0.5),
            ],
        ),
        last_signal_date="2026-01-07",
        last_trade_date="2026-01-08",
        last_signal_prices={
            "000001": 9.8,
            "000002": 9.9,
        },
        last_risk_state=RiskState(mode="risk_off", allow_new_entries=False, max_total_exposure=0.5),
        last_risk_signals={
            "macro_risk": True,
            "manual_risk_off": True,
            "a_share_break": False,
        },
        last_sell_reviews={
            "000001": {
                "decision": "sell",
                "reasoning": "趋势破坏。",
                "risk_flags": ["trend_break"],
            },
            "000002": {
                "decision": "hold",
                "reasoning": "波动加大，继续观察。",
                "risk_flags": ["volatility"],
            }
        },
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
    assert set(sheet["risk_state"]["active_risk_tags"]) == {"macro_risk", "manual_risk_off"}
    assert sheet["cash"] == 50000.0
    sold_holding = next(item for item in sheet["current_holdings"] if item["code"] == "000001")
    assert sold_holding["holding_days"] == 1
    assert sold_holding["current_weight"] == 1.0
    assert sold_holding["target_weight"] == 0.0
    assert sold_holding["action"] == "sell"
    assert sold_holding["action_text"] == "次日开盘卖出"
    assert sold_holding["last_close"] == 9.8
    assert sold_holding["unrealized_pnl_amount"] == pytest.approx(30.0)
    assert sold_holding["unrealized_pnl_pct"] == pytest.approx(0.031579, abs=1e-6)
    assert sold_holding["sell_reasoning"] == "趋势破坏。"
    assert sold_holding["risk_flags"] == ["trend_break"]
    assert sheet["next_holdings"][0]["code"] == "600000"
    assert sheet["next_holdings"][0]["action"] == "buy"
    assert sheet["next_holdings"][0]["action_text"] == "次日开盘买入"
    assert sheet["sell_orders"][0]["reasoning"] == "趋势破坏。"
    assert sheet["sell_orders"][0]["risk_flags"] == ["trend_break"]
    assert sheet["buy_orders"][0]["target_weight"] == 1.0
    assert sheet["buy_orders"][0]["instruction"] == "次日开盘买入"
    assert sheet["sell_orders"][0]["current_weight"] == 1.0
    assert sheet["sell_orders"][0]["target_weight"] == 0.0
    assert sheet["sell_orders"][0]["instruction"] == "次日开盘卖出"
    assert sheet["exposure_summary"]["current_total_weight"] == 1.5
    assert sheet["exposure_summary"]["target_total_weight"] == 1.5
    assert sheet["exposure_summary"]["planned_buy_weight"] == 1.0
    assert sheet["exposure_summary"]["planned_sell_weight"] == 1.0
    assert "risk_off" in sheet["risk_brief"]
    assert "macro_risk" in sheet["risk_brief"]
    assert sheet["focus_review_list"][0]["code"] == "000001"
    assert sheet["focus_review_list"][0]["action"] == "sell"
    assert sheet["focus_review_list"][0]["reasoning"] == "趋势破坏。"
    assert sheet["focus_review_list"][1]["code"] == "000002"
    assert sheet["focus_review_list"][1]["action"] == "hold"
    assert sheet["focus_review_list"][2]["code"] == "600000"
    assert sheet["focus_review_list"][2]["action"] == "buy"


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
