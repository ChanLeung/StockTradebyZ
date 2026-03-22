import pandas as pd

from pipeline.reference_io import pick_primary_index
from pipeline.fetch_reference_data import load_reference_series
from trading.benchmark import build_position_benchmark_weights, compute_dynamic_benchmark_return
from trading.schemas import Position


def test_pick_primary_index_uses_priority_order():
    mapping = {"600000": ["CSI1000", "HS300"]}
    priority = ["HS300", "CSI500", "CSI1000", "CSI2000", "ALLA"]

    assert pick_primary_index("600000", mapping, priority) == "HS300"


def test_load_reference_series_returns_index_and_proxy_frames(tmp_path):
    result = load_reference_series(tmp_path)

    assert {"benchmarks", "risk_proxies"} <= set(result)


def test_dynamic_benchmark_uses_position_weights():
    positions = [
        Position(code="600000", entry_date="2026-01-06", entry_price=10.0, weight=0.6),
        Position(code="000001", entry_date="2026-01-06", entry_price=12.0, weight=0.4),
    ]
    stock_to_index = {"600000": "HS300", "000001": "CSI2000"}
    benchmark_returns = pd.DataFrame(
        {
            "HS300": [0.02],
            "CSI2000": [-0.005],
        },
        index=["2026-01-07"],
    )

    weights = build_position_benchmark_weights(positions, stock_to_index)
    result = compute_dynamic_benchmark_return(weights, benchmark_returns, "2026-01-07")

    assert result == 0.01
