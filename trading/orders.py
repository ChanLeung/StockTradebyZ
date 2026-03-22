from trading.schemas import Order, TradeFill


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
