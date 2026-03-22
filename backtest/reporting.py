from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

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
    current_holdings = [
        _build_current_holding_item(position, result)
        for position in result.signal_state.positions
    ]
    next_holdings = [
        _build_next_holding_item(position, result)
        for position in result.final_state.positions
    ]
    buy_orders = [
        _build_buy_order_item(order, result)
        for order in result.pending_orders
        if order.side == "buy"
    ]
    sell_orders = [
        _build_sell_order_item(order, result, current_positions, active_risk_tags)
        for order in result.pending_orders
        if order.side == "sell"
    ]

    return {
        "signal_date": result.last_signal_date,
        "trade_date": result.last_trade_date,
        "risk_state": risk_state,
        "risk_brief": _build_risk_brief(result.last_risk_state.mode, active_risk_tags),
        "cash": result.signal_state.cash,
        "current_holdings": current_holdings,
        "next_holdings": next_holdings,
        "exposure_summary": _build_exposure_summary(current_holdings, next_holdings, buy_orders, sell_orders),
        "focus_review_list": _build_focus_review_list(current_holdings, buy_orders, sell_orders),
        "buy_list": buy_list,
        "sell_list": sell_list,
        "buy_orders": buy_orders,
        "sell_orders": sell_orders,
    }


def _build_current_holding_item(position, result: BacktestResult) -> dict:
    payload = position.to_dict()
    review = result.last_sell_reviews.get(position.code, {})
    next_position = _find_position(result.final_state.positions, position.code)
    last_close = result.last_signal_prices.get(position.code)
    payload["holding_days"] = _compute_holding_days(position.entry_date, result.last_signal_date)
    payload["current_weight"] = position.weight
    payload["target_weight"] = next_position.weight if next_position is not None else 0.0
    payload["action"] = "hold" if next_position is not None else "sell"
    payload["action_text"] = "继续持有" if next_position is not None else "次日开盘卖出"
    payload["last_close"] = last_close
    payload["unrealized_pnl_amount"] = _compute_unrealized_pnl_amount(position, last_close)
    payload["unrealized_pnl_pct"] = _compute_unrealized_pnl_pct(position, last_close)
    payload["sell_decision"] = review.get("decision", "hold")
    payload["sell_reasoning"] = review.get("reasoning")
    payload["risk_flags"] = list(review.get("risk_flags", []))
    return payload


def _build_next_holding_item(position, result: BacktestResult) -> dict:
    payload = position.to_dict()
    current_position = _find_position(result.signal_state.positions, position.code)
    payload["action"] = "hold" if current_position is not None else "buy"
    payload["action_text"] = "继续持有" if current_position is not None else "次日开盘买入"
    return payload


def _build_buy_order_item(order, result: BacktestResult) -> dict:
    payload = order.to_dict()
    next_position = _find_position(result.final_state.positions, order.code)
    payload["target_weight"] = next_position.weight if next_position is not None else None
    payload["instruction"] = "次日开盘买入"
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
    payload["current_weight"] = current_position.weight if current_position is not None else None
    payload["target_weight"] = 0.0
    payload["reasoning"] = review.get("reasoning")
    payload["risk_flags"] = list(review.get("risk_flags", []))
    if payload["reasoning"] is None and result.last_risk_state.mode == "risk_off":
        payload["reasoning"] = "risk_off 主动降仓"
        if not payload["risk_flags"]:
            payload["risk_flags"] = list(active_risk_tags)
    payload["instruction"] = "次日开盘卖出"
    return payload


def _compute_holding_days(entry_date: str, signal_date: str | None) -> int:
    if signal_date is None:
        return 0
    entry = date.fromisoformat(entry_date)
    signal = date.fromisoformat(signal_date)
    return max((signal - entry).days, 0)


def _compute_unrealized_pnl_amount(position, last_close: float | None) -> float | None:
    if last_close is None:
        return None
    return round((float(last_close) - float(position.entry_price)) * int(position.quantity), 4)


def _compute_unrealized_pnl_pct(position, last_close: float | None) -> float | None:
    if last_close is None or not position.entry_price:
        return None
    return round(float(last_close) / float(position.entry_price) - 1.0, 6)


def _find_position(positions: list, code: str):
    for position in positions:
        if position.code == code:
            return position
    return None


def _build_exposure_summary(
    current_holdings: list[dict],
    next_holdings: list[dict],
    buy_orders: list[dict],
    sell_orders: list[dict],
) -> dict:
    return {
        "current_total_weight": round(sum(item.get("current_weight", item.get("weight", 0.0) or 0.0) for item in current_holdings), 6),
        "target_total_weight": round(sum(item.get("weight", 0.0) or 0.0 for item in next_holdings), 6),
        "planned_buy_weight": round(sum(item.get("target_weight", 0.0) or 0.0 for item in buy_orders), 6),
        "planned_sell_weight": round(sum(item.get("current_weight", 0.0) or 0.0 for item in sell_orders), 6),
    }


def _build_risk_brief(mode: str, active_risk_tags: list[str]) -> str:
    if active_risk_tags:
        return f"当前风险状态：{mode}；激活标签：{', '.join(active_risk_tags)}。"
    return f"当前风险状态：{mode}；未触发额外风险标签。"


def _build_focus_review_list(
    current_holdings: list[dict],
    buy_orders: list[dict],
    sell_orders: list[dict],
) -> list[dict]:
    focus_items: list[dict] = []
    seen_codes: set[str] = set()

    for holding in current_holdings:
        if holding.get("action") != "sell" and not holding.get("risk_flags"):
            continue
        code = holding["code"]
        if code in seen_codes:
            continue
        focus_items.append(
            {
                "code": code,
                "action": holding.get("action"),
                "reasoning": holding.get("sell_reasoning"),
                "risk_flags": list(holding.get("risk_flags", [])),
                "priority_score": _compute_focus_priority_score(
                    action=holding.get("action"),
                    risk_flags=holding.get("risk_flags", []),
                ),
            }
        )
        seen_codes.add(code)

    for order in sell_orders:
        code = order["code"]
        if code in seen_codes:
            continue
        focus_items.append(
            {
                "code": code,
                "action": "sell",
                "reasoning": order.get("reasoning"),
                "risk_flags": list(order.get("risk_flags", [])),
                "priority_score": _compute_focus_priority_score(
                    action="sell",
                    risk_flags=order.get("risk_flags", []),
                ),
            }
        )
        seen_codes.add(code)

    for order in buy_orders:
        code = order["code"]
        if code in seen_codes:
            continue
        focus_items.append(
            {
                "code": code,
                "action": "buy",
                "reasoning": order.get("instruction"),
                "risk_flags": [],
                "priority_score": _compute_focus_priority_score(
                    action="buy",
                    risk_flags=[],
                ),
            }
        )
        seen_codes.add(code)

    return sorted(focus_items, key=_focus_review_priority)


def _focus_review_priority(item: dict) -> tuple[int, int, str]:
    action = str(item.get("action", "hold"))
    risk_count = len(item.get("risk_flags", []))
    return (
        -int(item.get("priority_score", _compute_focus_priority_score(action=action, risk_flags=item.get("risk_flags", [])))),
        -risk_count,
        str(item.get("code", "")),
    )


def _compute_focus_priority_score(action: str | None, risk_flags: list[str] | None) -> int:
    action_base = {
        "sell": 300,
        "hold": 200,
        "buy": 100,
    }
    return int(action_base.get(str(action or "hold"), 0) + len(risk_flags or []) * 10)


def write_signal_sheet_csv(path: str | Path, signal_sheet: dict) -> None:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "signal_date",
        "trade_date",
        "risk_mode",
        "code",
        "action",
        "instruction",
        "current_weight",
        "target_weight",
        "holding_days",
        "reasoning",
        "risk_flags",
    ]
    rows = build_signal_sheet_action_rows(signal_sheet)
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_signal_sheet_action_rows(signal_sheet: dict) -> list[dict]:
    rows: list[dict] = []
    signal_date = signal_sheet.get("signal_date")
    trade_date = signal_sheet.get("trade_date")
    risk_mode = signal_sheet.get("risk_state", {}).get("mode")

    for order in signal_sheet.get("sell_orders", []):
        rows.append(
            {
                "signal_date": signal_date,
                "trade_date": trade_date,
                "risk_mode": risk_mode,
                "code": order.get("code"),
                "action": "sell",
                "instruction": order.get("instruction"),
                "current_weight": order.get("current_weight"),
                "target_weight": order.get("target_weight"),
                "holding_days": order.get("holding_days"),
                "reasoning": order.get("reasoning"),
                "risk_flags": "|".join(order.get("risk_flags", [])),
            }
        )

    for order in signal_sheet.get("buy_orders", []):
        rows.append(
            {
                "signal_date": signal_date,
                "trade_date": trade_date,
                "risk_mode": risk_mode,
                "code": order.get("code"),
                "action": "buy",
                "instruction": order.get("instruction"),
                "current_weight": order.get("current_weight"),
                "target_weight": order.get("target_weight"),
                "holding_days": order.get("holding_days"),
                "reasoning": order.get("reasoning"),
                "risk_flags": "|".join(order.get("risk_flags", [])),
            }
        )

    return rows
