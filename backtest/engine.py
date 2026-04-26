from __future__ import annotations

from dataclasses import dataclass, field

from trading.benchmark import build_position_benchmark_weights, compute_dynamic_benchmark_return
from trading.orders import calculate_buy_order_quantity, compute_trade_cash_effect, simulate_open_fill
from trading.portfolio import apply_risk_budget, apply_sell_decisions, plan_watch_replacements, select_buy_candidates
from trading.risk import evaluate_risk_state
from trading.schemas import BacktestDailySnapshot, Order, PortfolioState, Position, RiskState, TradeFill


@dataclass
class BacktestResult:
    initial_cash: float = 0.0
    daily_snapshots: list[BacktestDailySnapshot] = field(default_factory=list)
    trades: list[TradeFill] = field(default_factory=list)
    pending_orders: list[Order] = field(default_factory=list)
    signal_state: PortfolioState = field(default_factory=lambda: PortfolioState(cash=0.0))
    final_state: PortfolioState = field(default_factory=lambda: PortfolioState(cash=0.0))
    last_signal_date: str | None = None
    last_trade_date: str | None = None
    last_signal_prices: dict[str, float] = field(default_factory=dict)
    last_risk_state: RiskState = field(
        default_factory=lambda: RiskState(mode="normal", allow_new_entries=True, max_total_exposure=1.0)
    )
    last_risk_signals: dict[str, bool] = field(default_factory=dict)
    last_sell_reviews: dict[str, dict] = field(default_factory=dict)
    last_buy_rejections: dict[str, list[str]] = field(default_factory=dict)
    last_replaceable_watch_list: list[dict] = field(default_factory=list)
    last_cash_reserved_reason: str | None = None


def run_backtest(config: dict, data_bundle: dict) -> BacktestResult:
    result = BacktestResult()
    max_positions = int(config.get("max_positions", 10))
    portfolio_config = config.get("portfolio", {})
    buy_rules = config.get("buy_rules", {})
    initial_state = data_bundle.get("initial_state")
    if isinstance(initial_state, PortfolioState):
        cash = float(initial_state.cash)
        current_positions = [
            Position(
                code=position.code,
                entry_date=position.entry_date,
                entry_price=position.entry_price,
                weight=position.weight,
                quantity=position.quantity,
            )
            for position in initial_state.positions
        ]
    else:
        cash = float(config.get("initial_cash", 1_000_000.0))
        current_positions = []
    result.initial_cash = cash + sum(
        position.entry_price * position.quantity
        for position in current_positions
    )
    cost_config = config.get("costs", {})
    stock_to_index = data_bundle.get("stock_to_index", {})
    stock_to_industry = data_bundle.get("stock_to_industry", {})
    min_buy_score = float(buy_rules.get("min_buy_score", 4.0))
    max_same_index = portfolio_config.get("max_same_index")
    max_same_industry = portfolio_config.get("max_same_industry")
    max_daily_replacements = int(portfolio_config.get("max_daily_replacements", 0))

    for signal_date in sorted(data_bundle.get("daily_candidates", {})):
        candidates = data_bundle["daily_candidates"][signal_date]
        trade_date = _next_trade_date(signal_date, data_bundle)
        open_prices = data_bundle["next_open_prices"][trade_date]
        pending_orders: list[Order] = []
        result.signal_state = PortfolioState(cash=cash, positions=list(current_positions))
        result.last_signal_prices = dict(
            data_bundle.get("signal_close_prices", {}).get(signal_date, {})
        )

        sell_decisions = data_bundle.get("sell_decisions", {}).get(signal_date, {})
        sell_reviews = data_bundle.get("sell_reviews", {}).get(signal_date, {})
        sold_codes: dict[str, str] = {}
        buy_rejections = _empty_buy_rejections()
        for position in current_positions:
            if sell_decisions.get(position.code) != "sell":
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
                sold_codes[position.code] = "sell"

        current_positions = apply_sell_decisions(current_positions, sold_codes)

        risk_signals = data_bundle.get("risk_signals", {}).get(signal_date, {})
        risk_state = evaluate_risk_state(risk_signals)
        result.last_signal_date = signal_date
        result.last_trade_date = trade_date
        result.last_risk_state = risk_state
        result.last_risk_signals = dict(risk_signals)
        result.last_sell_reviews = {
            code: dict(payload)
            for code, payload in sell_reviews.items()
        }
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

        replacement_plans = plan_watch_replacements(
            candidates,
            current_positions=current_positions,
            sell_reviews=sell_reviews,
            signal_date=signal_date,
            max_daily_replacements=max_daily_replacements,
            max_positions=max_positions,
            sold_today_codes=set(sold_codes),
            stock_to_index=stock_to_index,
            max_same_index=int(max_same_index) if max_same_index is not None else None,
            stock_to_industry=stock_to_industry,
            max_same_industry=int(max_same_industry) if max_same_industry is not None else None,
            min_buy_score=min_buy_score,
        )
        replaceable_watch_lookup = _build_replaceable_watch_lookup(
            current_positions,
            sell_reviews=sell_reviews,
            signal_date=signal_date,
        )
        successful_replacement_candidates = []
        replacement_code_to_watch_code: dict[str, str] = {}
        for plan in replacement_plans:
            position = plan["old_position"]
            new_candidate = plan["new_candidate"]
            if position.code not in open_prices:
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
                sold_codes[position.code] = "sell"
                successful_replacement_candidates.append(new_candidate)
                replacement_code_to_watch_code[new_candidate.code] = position.code
                if position.code in replaceable_watch_lookup:
                    replaceable_watch_lookup[position.code]["status"] = "replacement_sold"
                    replaceable_watch_lookup[position.code]["replacement_code"] = new_candidate.code
                    replaceable_watch_lookup[position.code]["replacement_score"] = (
                        new_candidate.buy_review_score
                    )

        current_positions = apply_sell_decisions(current_positions, sold_codes)
        sold_today_codes = set(sold_codes)
        available_slots = max(max_positions - len(current_positions), 0)
        buy_targets: list[Position] = []
        cash_shortfall_codes: list[str] = []
        if risk_state.allow_new_entries and available_slots > 0:
            prioritized_candidates = successful_replacement_candidates[:available_slots]
            placeholder_positions = [
                *current_positions,
                *[
                    Position(
                        code=candidate.code,
                        entry_date=trade_date,
                        entry_price=candidate.close,
                        weight=0.0,
                    )
                    for candidate in prioritized_candidates
                ],
            ]
            reserved_codes = {candidate.code for candidate in prioritized_candidates}
            selected_candidates, buy_rejections = select_buy_candidates(
                candidates,
                max_positions=max_positions,
                existing_positions=placeholder_positions,
                excluded_codes=sold_today_codes | reserved_codes,
                stock_to_index=stock_to_index,
                max_same_index=int(max_same_index) if max_same_index is not None else None,
                stock_to_industry=stock_to_industry,
                max_same_industry=int(max_same_industry) if max_same_industry is not None else None,
                min_buy_score=min_buy_score,
            )
            final_buy_candidates = [*prioritized_candidates, *selected_candidates]
            target_position_count = len(current_positions) + len(final_buy_candidates)
            weight = round(1.0 / target_position_count, 10) if target_position_count else 0.0
            buy_targets = [
                Position(
                    code=candidate.code,
                    entry_date=trade_date,
                    entry_price=candidate.close,
                    weight=weight,
                )
                for candidate in final_buy_candidates
            ]

        total_funds = cash + sum(
            float(open_prices.get(position.code, position.entry_price)) * position.quantity
            for position in current_positions
        )
        target_budget = total_funds / max_positions if max_positions > 0 else 0.0
        filled_buy_codes: set[str] = set()
        for position in buy_targets:
            quantity = calculate_buy_order_quantity(
                target_budget=target_budget,
                available_cash=cash,
                open_price=open_prices[position.code],
                cost_config=cost_config,
            )
            if quantity <= 0:
                cash_shortfall_codes.append(position.code)
                continue

            order = Order(code=position.code, side="buy", quantity=quantity)
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
                        quantity=quantity,
                    )
                )
                filled_buy_codes.add(position.code)

        for replacement_code, watch_code in replacement_code_to_watch_code.items():
            if watch_code not in replaceable_watch_lookup:
                continue
            if replacement_code in filled_buy_codes:
                replaceable_watch_lookup[watch_code]["status"] = "replaced"
            elif replaceable_watch_lookup[watch_code]["status"] == "replacement_sold":
                replaceable_watch_lookup[watch_code]["status"] = "sold_without_reentry"

        if current_positions:
            normalized_weight = round(1.0 / len(current_positions), 10)
            for position in current_positions:
                position.weight = normalized_weight

        result.pending_orders = pending_orders
        result.last_buy_rejections = {
            bucket: list(codes)
            for bucket, codes in buy_rejections.items()
        }
        result.last_replaceable_watch_list = list(replaceable_watch_lookup.values())
        result.last_cash_reserved_reason = _build_cash_reserved_reason(
            available_slots=available_slots,
            risk_state=risk_state,
            buy_rejections=buy_rejections,
            cash_shortfall_codes=cash_shortfall_codes,
            filled_buy_count=len(filled_buy_codes),
        )

        weights = build_position_benchmark_weights(current_positions, stock_to_index)
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


def _empty_buy_rejections() -> dict[str, list[str]]:
    return {
        "below_pass": [],
        "existing": [],
        "excluded": [],
        "index_limit": [],
        "industry_limit": [],
    }


def _build_replaceable_watch_lookup(
    positions: list[Position],
    *,
    sell_reviews: dict[str, dict],
    signal_date: str,
) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for position in positions:
        review = sell_reviews.get(position.code, {})
        if str(review.get("verdict", "")).upper() != "WATCH":
            continue
        lookup[position.code] = {
            "code": position.code,
            "holding_days": _compute_holding_days(position.entry_date, signal_date),
            "sell_score": float(review.get("total_score", 0.0) or 0.0),
            "reasoning": review.get("reasoning"),
            "risk_flags": list(review.get("risk_flags", [])),
            "status": "watch",
            "replacement_code": None,
            "replacement_score": None,
        }
    return lookup


def _compute_holding_days(entry_date: str, signal_date: str) -> int:
    from datetime import date

    return max((date.fromisoformat(signal_date) - date.fromisoformat(entry_date)).days, 0)


def _build_cash_reserved_reason(
    *,
    available_slots: int,
    risk_state: RiskState,
    buy_rejections: dict[str, list[str]],
    cash_shortfall_codes: list[str],
    filled_buy_count: int,
) -> str | None:
    if available_slots <= 0:
        return None
    if not risk_state.allow_new_entries:
        return "risk_off 已触发，当前禁止开新仓，剩余仓位保留现金。"
    if filled_buy_count >= available_slots:
        return None

    reasons: list[str] = []
    index_rejections = buy_rejections.get("index_limit", [])
    industry_rejections = buy_rejections.get("industry_limit", [])
    below_pass = buy_rejections.get("below_pass", [])
    if index_rejections:
        reasons.append(f"指数约束拒绝 {len(index_rejections)} 只")
    if industry_rejections:
        reasons.append(f"行业约束拒绝 {len(industry_rejections)} 只")
    if below_pass:
        reasons.append(f"未达到 PASS {len(below_pass)} 只")
    if cash_shortfall_codes:
        reasons.append("按当前总权益的 1/10 计算并按 100 股取整后，剩余现金不足以继续开仓")
    if not reasons:
        reasons.append("当日没有额外满足条件的新候选")
    return "；".join(reasons) + "，剩余仓位保留现金。"
