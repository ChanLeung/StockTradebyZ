import pytest

from trading.orders import calculate_buy_order_quantity, compute_trade_cash_effect, simulate_open_fill
from trading.schemas import Order, TradeFill


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


def test_compute_trade_cash_effect_applies_buy_side_costs():
    fill = TradeFill(code="600000", side="buy", quantity=100, fill_price=10.0)

    cash_effect = compute_trade_cash_effect(
        fill,
        {"commission_bps": 3, "stamp_duty_bps": 10, "slippage_bps": 2},
    )

    assert cash_effect == pytest.approx(-1000.5)


def test_compute_trade_cash_effect_applies_sell_side_stamp_duty():
    fill = TradeFill(code="600000", side="sell", quantity=100, fill_price=10.0)

    cash_effect = compute_trade_cash_effect(
        fill,
        {"commission_bps": 3, "stamp_duty_bps": 10, "slippage_bps": 2},
    )

    assert cash_effect == pytest.approx(998.5)


def test_calculate_buy_order_quantity_uses_one_tenth_total_budget_and_rounds_down_to_lot():
    quantity = calculate_buy_order_quantity(
        target_budget=10000.0,
        available_cash=100000.0,
        open_price=11.0,
        cost_config={},
    )

    assert quantity == 900


def test_calculate_buy_order_quantity_is_limited_by_available_cash():
    quantity = calculate_buy_order_quantity(
        target_budget=10000.0,
        available_cash=4500.0,
        open_price=10.0,
        cost_config={"commission_bps": 3, "slippage_bps": 2},
    )

    assert quantity == 400
