def test_price_frame_fixture_has_required_columns(price_frame):
    assert list(price_frame.columns) == ["date", "open", "close", "high", "low", "volume"]
