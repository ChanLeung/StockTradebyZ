import pandas as pd
import pytest


@pytest.fixture
def price_frame():
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"]),
            "open": [10.0, 10.5, 10.8],
            "close": [10.4, 10.7, 11.0],
            "high": [10.6, 10.9, 11.2],
            "low": [9.9, 10.3, 10.6],
            "volume": [1000, 1200, 1500],
        }
    )
