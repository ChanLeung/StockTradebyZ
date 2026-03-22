import pytest

from backtest.engine import BacktestResult
from backtest.reporting import (
    build_signal_sheet,
    build_signal_sheet_brief_markdown,
    build_signal_sheet_review_markdown,
    summarize_backtest,
)
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
    assert sheet["focus_review_list"][0]["priority_score"] == 310
    assert sheet["focus_review_list"][0]["category"] == "sell_review"
    assert sheet["focus_review_list"][1]["code"] == "000002"
    assert sheet["focus_review_list"][1]["action"] == "hold"
    assert sheet["focus_review_list"][1]["priority_score"] == 210
    assert sheet["focus_review_list"][1]["category"] == "hold_watch"
    assert sheet["focus_review_list"][2]["code"] == "600000"
    assert sheet["focus_review_list"][2]["action"] == "buy"
    assert sheet["focus_review_list"][2]["priority_score"] == 100
    assert sheet["focus_review_list"][2]["category"] == "new_buy"
    assert [group["category"] for group in sheet["focus_review_groups"]] == [
        "sell_review",
        "hold_watch",
        "new_buy",
    ]
    assert [group["title"] for group in sheet["focus_review_groups"]] == [
        "卖出复核",
        "持仓观察",
        "新开仓",
    ]
    assert sheet["focus_review_groups"][0]["items"][0]["code"] == "000001"
    assert sheet["focus_review_groups"][1]["items"][0]["code"] == "000002"
    assert sheet["focus_review_groups"][2]["items"][0]["code"] == "600000"


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


def test_build_signal_sheet_review_markdown_renders_grouped_sections():
    signal_sheet = {
        "signal_date": "2026-01-07",
        "trade_date": "2026-01-08",
        "risk_state": {
            "mode": "risk_off",
            "active_risk_tags": ["macro_risk", "manual_risk_off"],
        },
        "risk_brief": "当前风险状态：risk_off；激活标签：macro_risk, manual_risk_off。",
        "exposure_summary": {
            "current_total_weight": 1.5,
            "target_total_weight": 1.0,
            "planned_buy_weight": 0.0,
            "planned_sell_weight": 0.5,
        },
        "focus_review_groups": [
            {
                "category": "sell_review",
                "title": "卖出复核",
                "items": [
                    {
                        "code": "000001",
                        "action": "sell",
                        "reasoning": "趋势破坏。",
                        "risk_flags": ["trend_break"],
                        "priority_score": 310,
                        "category": "sell_review",
                    }
                ],
            },
            {
                "category": "hold_watch",
                "title": "持仓观察",
                "items": [
                    {
                        "code": "000002",
                        "action": "hold",
                        "reasoning": "波动加大，继续观察。",
                        "risk_flags": ["volatility"],
                        "priority_score": 210,
                        "category": "hold_watch",
                    }
                ],
            },
        ],
    }

    markdown = build_signal_sheet_review_markdown(signal_sheet)

    assert "# 次日执行复核摘要" in markdown
    assert "- 信号日期：2026-01-07" in markdown
    assert "- 执行日期：2026-01-08" in markdown
    assert "## 风险摘要" in markdown
    assert "当前风险状态：risk_off；激活标签：macro_risk, manual_risk_off。" in markdown
    assert "## 仓位摘要" in markdown
    assert "- 当前总仓位：1.5" in markdown
    assert "## 卖出复核" in markdown
    assert "## 持仓观察" in markdown
    assert "- `000001` `sell` 优先级 `310`" in markdown
    assert "- `000002` `hold` 优先级 `210`" in markdown
    assert "风险标签：trend_break" in markdown


def test_build_signal_sheet_brief_markdown_renders_three_action_sections():
    signal_sheet = {
        "signal_date": "2026-01-07",
        "trade_date": "2026-01-08",
        "risk_state": {
            "mode": "risk_off",
            "active_risk_tags": ["macro_risk"],
        },
        "risk_brief": "当前风险状态：risk_off；激活标签：macro_risk。",
        "exposure_summary": {
            "current_total_weight": 1.5,
            "target_total_weight": 1.0,
            "planned_buy_weight": 0.0,
            "planned_sell_weight": 0.5,
        },
        "focus_review_groups": [
            {
                "category": "sell_review",
                "title": "卖出复核",
                "items": [
                    {
                        "code": "000001",
                        "action": "sell",
                        "reasoning": "趋势破坏。",
                        "risk_flags": ["trend_break"],
                        "priority_score": 310,
                        "category": "sell_review",
                    }
                ],
            },
            {
                "category": "hold_watch",
                "title": "持仓观察",
                "items": [
                    {
                        "code": "000002",
                        "action": "hold",
                        "reasoning": "波动加大，继续观察。",
                        "risk_flags": ["volatility"],
                        "priority_score": 210,
                        "category": "hold_watch",
                    }
                ],
            },
        ],
    }

    markdown = build_signal_sheet_brief_markdown(signal_sheet)

    assert "# 盘前执行卡片" in markdown
    assert "- 风险模式：risk_off" in markdown
    assert "- 当前/目标仓位：1.5 -> 1.0" in markdown
    assert "## 卖出优先（1）" in markdown
    assert "## 持仓观察（1）" in markdown
    assert "## 新开仓（0）" in markdown
    assert "- `000001` 趋势破坏。" in markdown
    assert "- `000002` 波动加大，继续观察。" in markdown
    assert "- 无" in markdown
    assert "## 一句话摘要" in markdown
    assert "当前风险模式 risk_off；当前/目标仓位 1.5 -> 1.0；卖出优先 1 项，持仓观察 1 项，新开仓 0 项。" in markdown
    assert "## Top 5 重点动作" in markdown
    assert "1. [立即处理] [卖出优先] `000001` 趋势破坏。" in markdown
    assert "2. [开盘观察] [持仓观察] `000002` 波动加大，继续观察。" in markdown


def test_build_signal_sheet_brief_markdown_limits_top_actions_to_five_items():
    signal_sheet = {
        "signal_date": "2026-01-07",
        "trade_date": "2026-01-08",
        "risk_state": {"mode": "normal", "active_risk_tags": []},
        "risk_brief": "当前风险状态：normal；未触发额外风险标签。",
        "exposure_summary": {
            "current_total_weight": 0.5,
            "target_total_weight": 1.0,
            "planned_buy_weight": 0.5,
            "planned_sell_weight": 0.0,
        },
        "focus_review_groups": [
            {
                "category": "sell_review",
                "title": "卖出复核",
                "items": [
                    {"code": "000001", "action": "sell", "reasoning": "卖出1", "risk_flags": [], "priority_score": 320, "category": "sell_review"},
                    {"code": "000002", "action": "sell", "reasoning": "卖出2", "risk_flags": [], "priority_score": 310, "category": "sell_review"},
                ],
            },
            {
                "category": "hold_watch",
                "title": "持仓观察",
                "items": [
                    {"code": "000003", "action": "hold", "reasoning": "观察1", "risk_flags": [], "priority_score": 210, "category": "hold_watch"},
                    {"code": "000004", "action": "hold", "reasoning": "观察2", "risk_flags": [], "priority_score": 205, "category": "hold_watch"},
                ],
            },
            {
                "category": "new_buy",
                "title": "新开仓",
                "items": [
                    {"code": "000005", "action": "buy", "reasoning": "买入1", "risk_flags": [], "priority_score": 110, "category": "new_buy"},
                    {"code": "000006", "action": "buy", "reasoning": "买入2", "risk_flags": [], "priority_score": 100, "category": "new_buy"},
                ],
            },
        ],
    }

    markdown = build_signal_sheet_brief_markdown(signal_sheet)
    top_section = markdown.split("## Top 5 重点动作\n", maxsplit=1)[1].split("\n## 卖出优先（2）", maxsplit=1)[0]

    assert "1. [立即处理] [卖出优先] `000001` 卖出1" in top_section
    assert "2. [立即处理] [卖出优先] `000002` 卖出2" in top_section
    assert "3. [开盘观察] [持仓观察] `000003` 观察1" in top_section
    assert "4. [开盘观察] [持仓观察] `000004` 观察2" in top_section
    assert "5. [可延后复核] [新开仓] `000005` 买入1" in top_section
    assert "`000006` 买入2" not in top_section


def test_build_signal_sheet_brief_markdown_supports_custom_execution_labels():
    signal_sheet = {
        "signal_date": "2026-01-07",
        "trade_date": "2026-01-08",
        "risk_state": {"mode": "normal", "active_risk_tags": []},
        "risk_brief": "当前风险状态：normal；未触发额外风险标签。",
        "exposure_summary": {
            "current_total_weight": 0.5,
            "target_total_weight": 1.0,
            "planned_buy_weight": 0.5,
            "planned_sell_weight": 0.0,
        },
        "focus_review_groups": [
            {
                "category": "sell_review",
                "title": "卖出复核",
                "items": [
                    {"code": "000001", "action": "sell", "reasoning": "卖出1", "risk_flags": [], "priority_score": 320, "category": "sell_review"},
                ],
            },
            {
                "category": "hold_watch",
                "title": "持仓观察",
                "items": [
                    {"code": "000003", "action": "hold", "reasoning": "观察1", "risk_flags": [], "priority_score": 210, "category": "hold_watch"},
                ],
            },
            {
                "category": "new_buy",
                "title": "新开仓",
                "items": [
                    {"code": "000005", "action": "buy", "reasoning": "买入1", "risk_flags": [], "priority_score": 110, "category": "new_buy"},
                ],
            },
        ],
    }

    markdown = build_signal_sheet_brief_markdown(
        signal_sheet,
        execution_labels={
            "sell_review": "立刻执行",
            "hold_watch": "盘中观察",
            "new_buy": "尾盘再看",
        },
    )

    assert "1. [立刻执行] [卖出优先] `000001` 卖出1" in markdown
    assert "2. [盘中观察] [持仓观察] `000003` 观察1" in markdown
    assert "3. [尾盘再看] [新开仓] `000005` 买入1" in markdown
