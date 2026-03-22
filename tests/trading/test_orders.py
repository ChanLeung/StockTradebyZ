from trading.orders import simulate_open_fill
from trading.schemas import Order


def test_buy_order_skips_one_word_limit_up():
    order = Order(code="600000", side="buy", quantity=100)

    fill = simulate_open_fill(
        order,
        open_price=10.0,
        high=10.0,
        low=10.0,
        is_limit_up=True,
    )

    assert fill is None


def test_sell_order_rolls_when_one_word_limit_down():
    order = Order(code="600000", side="sell", quantity=100)

    fill = simulate_open_fill(
        order,
        open_price=8.0,
        high=8.0,
        low=8.0,
        is_limit_down=True,
    )

    assert fill is None


def test_normal_open_fill_returns_trade_fill():
    order = Order(code="600000", side="buy", quantity=100)

    fill = simulate_open_fill(
        order,
        open_price=10.2,
        high=10.5,
        low=10.0,
    )

    assert fill is not None
    assert fill.fill_price == 10.2
