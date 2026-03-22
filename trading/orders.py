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
