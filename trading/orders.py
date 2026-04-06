from trading.schemas import Order, TradeFill


def calculate_buy_order_quantity(
    *,
    target_budget: float,
    available_cash: float,
    open_price: float,
    cost_config: dict[str, float],
    lot_size: int = 100,
) -> int:
    if lot_size <= 0 or open_price <= 0:
        return 0

    budget_cap = min(float(target_budget), float(available_cash))
    if budget_cap <= 0:
        return 0

    commission_bps = float(cost_config.get("commission_bps", 0.0)) / 10000.0
    slippage_bps = float(cost_config.get("slippage_bps", 0.0)) / 10000.0
    effective_price = float(open_price) * (1.0 + slippage_bps) * (1.0 + commission_bps)
    if effective_price <= 0:
        return 0

    max_lots = int(budget_cap // (effective_price * lot_size))
    return max(max_lots, 0) * lot_size


def simulate_open_fill(
    order: Order,
    *,
    open_price: float,
    high: float,
    low: float,
    is_limit_up: bool = False,
    is_limit_down: bool = False,
) -> TradeFill | None:
    _ = (high, low)

    if order.side == "buy" and is_limit_up:
        return None
    if order.side == "sell" and is_limit_down:
        return None

    return TradeFill(
        code=order.code,
        side=order.side,
        quantity=order.quantity,
        fill_price=float(open_price),
    )


def compute_trade_cash_effect(fill: TradeFill, cost_config: dict[str, float]) -> float:
    commission_bps = float(cost_config.get("commission_bps", 0.0)) / 10000.0
    stamp_duty_bps = float(cost_config.get("stamp_duty_bps", 0.0)) / 10000.0
    slippage_bps = float(cost_config.get("slippage_bps", 0.0)) / 10000.0

    direction = 1.0 if fill.side == "buy" else -1.0
    slipped_price = fill.fill_price * (1.0 + direction * slippage_bps)
    gross_amount = slipped_price * fill.quantity
    commission = gross_amount * commission_bps
    stamp_duty = gross_amount * stamp_duty_bps if fill.side == "sell" else 0.0

    if fill.side == "buy":
        return -(gross_amount + commission + stamp_duty)
    return gross_amount - commission - stamp_duty
