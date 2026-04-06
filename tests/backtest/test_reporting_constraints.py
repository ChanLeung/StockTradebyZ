from backtest.engine import BacktestResult
from backtest.reporting import (
    build_signal_sheet,
    build_signal_sheet_action_rows,
    build_signal_sheet_brief_markdown,
    build_signal_sheet_review_markdown,
)
from trading.schemas import BacktestDailySnapshot, Order, PortfolioState, Position, RiskState


def test_build_signal_sheet_includes_constraint_and_cash_reason_fields():
    result = BacktestResult(
        signal_state=PortfolioState(
            cash=200000.0,
            positions=[
                Position(code="000002", entry_date="2026-01-05", entry_price=10.0, weight=0.5, quantity=1000),
            ],
        ),
        final_state=PortfolioState(
            cash=120000.0,
            positions=[
                Position(code="600000", entry_date="2026-01-08", entry_price=12.0, weight=1.0, quantity=800),
            ],
        ),
        last_signal_date="2026-01-07",
        last_trade_date="2026-01-08",
        last_risk_state=RiskState(mode="normal", allow_new_entries=True, max_total_exposure=1.0),
        last_buy_rejections={
            "index_limit": ["600010", "600011"],
            "industry_limit": ["000777"],
        },
        last_replaceable_watch_list=[
            {
                "code": "000002",
                "holding_days": 2,
                "sell_score": 3.5,
                "reasoning": "趋势转弱，进入可替换池。",
                "risk_flags": ["weakening"],
                "status": "replaced",
                "replacement_code": "600000",
                "replacement_score": 4.8,
            }
        ],
        last_cash_reserved_reason="当日仅有 1 只 PASS 候选满足分散化约束，剩余仓位保留现金。",
        last_sell_reviews={
            "000002": {
                "decision": "hold",
                "verdict": "WATCH",
                "reasoning": "趋势转弱，进入可替换池。",
                "risk_flags": ["weakening"],
                "total_score": 3.5,
            }
        },
        pending_orders=[
            Order(code="000002", side="sell", quantity=1000),
            Order(code="600000", side="buy", quantity=800),
        ],
        daily_snapshots=[
            BacktestDailySnapshot(
                date="2026-01-08",
                cash=120000.0,
                position_count=1,
                benchmark_return=0.0,
            )
        ],
    )

    sheet = build_signal_sheet(result)

    assert sheet["buy_candidates_rejected_by_index_limit"] == ["600010", "600011"]
    assert sheet["buy_candidates_rejected_by_industry_limit"] == ["000777"]
    assert sheet["replaceable_watch_list"][0]["code"] == "000002"
    assert sheet["replaceable_watch_list"][0]["replacement_code"] == "600000"
    assert sheet["cash_reserved_reason"] == "当日仅有 1 只 PASS 候选满足分散化约束，剩余仓位保留现金。"


def test_reporting_outputs_render_constraint_and_cash_reason_context():
    signal_sheet = {
        "signal_date": "2026-01-07",
        "trade_date": "2026-01-08",
        "risk_state": {"mode": "normal", "active_risk_tags": []},
        "risk_brief": "当前风险状态：normal；未触发额外风险标签。",
        "exposure_summary": {
            "current_total_weight": 0.5,
            "target_total_weight": 1.0,
            "planned_buy_weight": 0.5,
            "planned_sell_weight": 0.5,
        },
        "focus_review_groups": [
            {
                "category": "sell_review",
                "title": "卖出复核",
                "items": [
                    {
                        "code": "000002",
                        "action": "sell",
                        "reasoning": "趋势转弱，进入可替换池。",
                        "risk_flags": ["weakening"],
                        "priority_score": 310,
                        "category": "sell_review",
                    }
                ],
            },
            {
                "category": "new_buy",
                "title": "新开仓",
                "items": [
                    {
                        "code": "600000",
                        "action": "buy",
                        "reasoning": "次日开盘买入",
                        "risk_flags": [],
                        "priority_score": 100,
                        "category": "new_buy",
                    }
                ],
            },
        ],
        "buy_orders": [
            {
                "code": "600000",
                "instruction": "次日开盘买入",
                "target_weight": 1.0,
            }
        ],
        "sell_orders": [
            {
                "code": "000002",
                "instruction": "次日开盘卖出",
                "reasoning": "趋势转弱，进入可替换池。",
                "risk_flags": ["weakening"],
                "current_weight": 0.5,
                "target_weight": 0.0,
                "holding_days": 2,
            }
        ],
        "buy_candidates_rejected_by_index_limit": ["600010", "600011"],
        "buy_candidates_rejected_by_industry_limit": ["000777"],
        "replaceable_watch_list": [
            {
                "code": "000002",
                "holding_days": 2,
                "sell_score": 3.5,
                "reasoning": "趋势转弱，进入可替换池。",
                "risk_flags": ["weakening"],
                "status": "replaced",
                "replacement_code": "600000",
                "replacement_score": 4.8,
            }
        ],
        "cash_reserved_reason": "当日仅有 1 只 PASS 候选满足分散化约束，剩余仓位保留现金。",
    }

    review_markdown = build_signal_sheet_review_markdown(signal_sheet)
    brief_markdown = build_signal_sheet_brief_markdown(signal_sheet)
    rows = build_signal_sheet_action_rows(signal_sheet)

    assert "## 补仓约束与留现金说明" in review_markdown
    assert "指数约束拒绝：600010, 600011" in review_markdown
    assert "行业约束拒绝：000777" in review_markdown
    assert "留现金原因：当日仅有 1 只 PASS 候选满足分散化约束，剩余仓位保留现金。" in review_markdown
    assert "## 可替换持仓" in review_markdown
    assert "`000002` 当前状态 `replaced`" in review_markdown
    assert "替换目标：`600000`" in review_markdown

    assert "## 补仓说明" in brief_markdown
    assert "- 留现金原因：当日仅有 1 只 PASS 候选满足分散化约束，剩余仓位保留现金。" in brief_markdown
    assert "- 指数约束跳过：600010, 600011" in brief_markdown
    assert "- 行业约束跳过：000777" in brief_markdown

    assert rows[0]["rejected_by_index_limit"] == "600010|600011"
    assert rows[0]["rejected_by_industry_limit"] == "000777"
    assert rows[0]["replaceable_watch_list"] == "000002:replaced->600000"
    assert rows[0]["cash_reserved_reason"] == "当日仅有 1 只 PASS 候选满足分散化约束，剩余仓位保留现金。"
