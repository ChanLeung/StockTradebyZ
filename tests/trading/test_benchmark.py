from pipeline.reference_io import pick_primary_index
from pipeline.fetch_reference_data import load_reference_series


def test_pick_primary_index_uses_priority_order():
    mapping = {"600000": ["CSI1000", "HS300"]}
    priority = ["HS300", "CSI500", "CSI1000", "CSI2000", "ALLA"]

    assert pick_primary_index("600000", mapping, priority) == "HS300"


def test_load_reference_series_returns_index_and_proxy_frames(tmp_path):
    result = load_reference_series(tmp_path)

    assert {"benchmarks", "risk_proxies"} <= set(result)
